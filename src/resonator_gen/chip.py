"""Chip assembly: feedline + N resonators → GDS/OASIS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resonator_gen.calibration import Calibration
from resonator_gen.config import ChipConfig, ResonatorSpec
from resonator_gen.constants import (
    AVOIDANCE_LAYER,
    COUPLER_LEAD_UM,
    GAP_LAYER,
    KQC_PROTECTION_MARGIN_UM,
    SPIRAL_LENGTH_TOL_UM,
)
from resonator_gen.constraints import footprint_um as cpw_footprint_wg_um
from resonator_gen.cpw import CpwCrossSection
from resonator_gen.keepouts import (
    KeepoutSet,
    cell_region,
    feedline_footprint_region,
    keepout_entry_region,
    rect_region,
)
from resonator_gen.logging_config import get_logger
from resonator_gen.resonators.base import ResonatorBuildResult
from resonator_gen.resonators.meander import MeanderResonator
from resonator_gen.resonators.spiral import SpiralResonator
from resonator_gen.routing import PlacementInfeasibleError, PlacementResult, find_anchored_placement

logger = get_logger(__name__)


class Chip:
    """Assemble a feedline and readout resonators from a :class:`ChipConfig`."""

    def __init__(self, config: ChipConfig) -> None:
        self.config = config
        self._specs: list[ResonatorSpec] = list(config.resonators)
        self._layout: Any | None = None
        self._top_cell: Any | None = None
        self._results: list[ResonatorBuildResult] = []
        self._built = False

    def add_resonator(self, spec: ResonatorSpec) -> None:
        """Append a resonator specification before :meth:`build`."""
        if self._built:
            raise RuntimeError("Cannot add resonators after build()")
        self._specs.append(spec)

    @property
    def calibration(self) -> Calibration:
        """Runtime calibration object."""
        return self.config.calibration.to_calibration()

    def build(self) -> None:
        """Generate KLayout cells for the feedline and all resonators."""
        from kqcircuits.elements.waveguide_coplanar import WaveguideCoplanar
        from kqcircuits.pya_resolver import pya

        layout = pya.Layout()
        # Prefer KQC default layers when available.
        try:
            from kqcircuits import defaults as kqc_defaults

            _ = kqc_defaults  # layers registered on first Element.create
        except Exception:  # pragma: no cover - defensive
            pass

        top = layout.create_cell(self.config.name)
        cross = CpwCrossSection.from_config(self.config.cpw)
        path = [
            pya.DPoint(float(x), float(y)) for x, y in self.config.feedline.path_um
        ]
        feed = WaveguideCoplanar.create(layout, path=path, **cross.as_kqc_kwargs())
        top.insert(pya.DCellInstArray(feed.cell_index(), pya.DTrans(0, False, 0, 0)))

        keepout_set = self._initial_keepout_set(layout.dbu, cross)

        results: list[ResonatorBuildResult] = []
        for spec in self._specs:
            corridor_um: tuple[float, float] | None = None
            if spec.placement.mode == "auto":
                spec, placement = self._solve_auto_placement(spec, keepout_set, cross)
                if placement.geometry == "spiral":
                    corridor_um = (placement.length_um, placement.width_um)
                    self._verify_spiral_fit(spec, corridor_um)
            if spec.geometry == "meander":
                result = MeanderResonator(spec).build_standalone(
                    layout,
                    self.calibration,
                    self.config.cpw,
                    constraints=self.config.constraints,
                )
            elif spec.geometry == "spiral":
                result = SpiralResonator(spec).build_standalone(
                    layout,
                    self.calibration,
                    self.config.cpw,
                    constraints=self.config.constraints,
                    corridor_um=corridor_um,
                )
            else:
                raise ValueError(f"Unknown geometry {spec.geometry!r}")
            top.insert(pya.DCellInstArray(result.cell_instance.cell_index(), pya.DTrans(0, False, 0, 0)))
            results.append(result)
            if keepout_set is not None:
                shape = cell_region(result.cell_instance, GAP_LAYER)
                shape += cell_region(result.cell_instance, AVOIDANCE_LAYER)
                keepout_set.add(shape, spec.name)

        self._layout = layout
        self._top_cell = top
        self._results = results
        self._built = True
        logger.info("Built chip %s with %d resonators", self.config.name, len(results))

    def write_gds(self, path: str | Path) -> None:
        """Export the chip to GDSII."""
        self._require_built()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert self._layout is not None
        options = self._layout.get_info(0) if False else None  # keep for future
        _ = options
        self._layout.write(str(path))
        logger.info("Wrote GDS %s", path)

    def write_oas(self, path: str | Path) -> None:
        """Export the chip to OASIS."""
        self._require_built()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        assert self._layout is not None
        self._layout.write(str(path))
        logger.info("Wrote OASIS %s", path)

    def report(self) -> list[ResonatorBuildResult]:
        """Return build results and log target vs actual lengths."""
        self._require_built()
        for result in self._results:
            delta = result.actual_length_um - result.body_length_um
            logger.info(
                "%s f=%.3f GHz target=%.3f µm body=%.3f µm actual=%.6f µm Δbody=%.6f µm",
                result.name,
                result.frequency_hz / 1e9,
                result.target_length_um,
                result.body_length_um,
                result.actual_length_um,
                delta,
            )
        return list(self._results)

    def _require_built(self) -> None:
        if not self._built:
            raise RuntimeError("Call build() before export/report")

    # ------------------------------------------------------------------
    # Auto placement
    # ------------------------------------------------------------------

    def _initial_keepout_set(self, dbu: float, cross: CpwCrossSection) -> KeepoutSet | None:
        """Die-minus-margin keep-in plus feedline and YAML keepouts."""
        die = self.config.die
        if die is None:
            return None
        x0, y0 = die.origin_um
        m = die.edge_margin_um
        die_inner = rect_region(
            x0 + m, y0 + m, x0 + die.width_um - m, y0 + die.height_um - m, dbu
        )
        ks = KeepoutSet(die_inner, dbu)
        ks.add(
            feedline_footprint_region(
                self.config.feedline, cross.width_um / 2.0 + cross.gap_um, dbu
            ),
            "feedline",
        )
        for entry in self.config.keepouts:
            ks.add(keepout_entry_region(entry, dbu), entry.source)
        return ks

    def _clearance_um(self, spec: ResonatorSpec) -> float:
        if spec.placement.clearance_um is not None:
            return spec.placement.clearance_um
        return self.config.constraints.pitch_ratio_min * cpw_footprint_wg_um(
            self.config.cpw.width_um, self.config.cpw.gap_um
        )

    def _solve_auto_placement(
        self,
        spec: ResonatorSpec,
        keepout_set: KeepoutSet | None,
        cross: CpwCrossSection,
    ) -> tuple[ResonatorSpec, PlacementResult]:
        """Solve the anchored corridor and return an updated spec copy."""
        if keepout_set is None:
            raise ValueError(
                f"Resonator {spec.name} uses placement.mode: auto but no die is configured"
            )
        clearance_um = self._clearance_um(spec)
        keep_in = keepout_set.keep_in_region(clearance_um)
        radius = spec.bend_radius_um if spec.bend_radius_um is not None else self.config.cpw.bend_radius_um
        body_length_um = self.calibration.body_length_um(spec.frequency_hz, mode=spec.mode)
        coupler_length_um = spec.coupler.finger_length_um
        lead_um = COUPLER_LEAD_UM + coupler_length_um + cross.width_um
        footprint = (
            cross.width_um + 2.0 * cross.gap_um + 2.0 * KQC_PROTECTION_MARGIN_UM
        )
        placement = find_anchored_placement(
            keep_in,
            keepout_set.dbu,
            start_um=(spec.placement.x_um, spec.placement.y_um),
            direction_deg=spec.placement.orientation_deg,
            target_length_um=body_length_um,
            bend_radius_um=radius,
            cpw_footprint_um=footprint,
            lead_um=lead_um,
            clearance_um=clearance_um,
            preferred_geometry=spec.placement.preferred_geometry,
        )
        logger.info(
            "%s auto placement: geometry=%s span=%.3f µm width=%.3f µm",
            spec.name,
            placement.geometry,
            placement.length_um,
            placement.width_um,
        )
        updated = spec.model_copy(
            update={
                "geometry": placement.geometry,
                "placement": spec.placement.model_copy(
                    update={"meander_span_um": placement.length_um}
                ),
            }
        )
        return updated, placement

    def _verify_spiral_fit(self, spec: ResonatorSpec, corridor_um: tuple[float, float]) -> None:
        """Build the spiral in a scratch layout and verify realized length."""
        from kqcircuits.pya_resolver import pya

        scratch = pya.Layout()
        try:
            result = SpiralResonator(spec).build_standalone(
                scratch,
                self.calibration,
                self.config.cpw,
                constraints=self.config.constraints,
                corridor_um=corridor_um,
            )
        except Exception as exc:
            raise PlacementInfeasibleError(
                f"Spiral for {spec.name} failed to build in solved corridor "
                f"{corridor_um[0]:.1f} × {corridor_um[1]:.1f} µm: {exc}",
                target_length_um=self.calibration.body_length_um(spec.frequency_hz, mode=spec.mode),
                best_feasible_length_um=None,
                shortfall_um=None,
                geometries_tried=("spiral",),
                clearance_um=self._clearance_um(spec),
            ) from exc
        delta = abs(result.actual_length_um - result.body_length_um)
        if delta > SPIRAL_LENGTH_TOL_UM:
            raise PlacementInfeasibleError(
                f"Spiral for {spec.name} realized {result.actual_length_um:.3f} µm "
                f"vs target {result.body_length_um:.3f} µm (|Δ|={delta:.3f} µm)",
                target_length_um=result.body_length_um,
                best_feasible_length_um=result.actual_length_um,
                shortfall_um=max(0.0, result.body_length_um - result.actual_length_um),
                geometries_tried=("spiral",),
                clearance_um=self._clearance_um(spec),
            )
