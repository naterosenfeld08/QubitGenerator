"""Meander readout resonator wrapping KQCircuits ``Meander``."""

from __future__ import annotations

import math
from typing import Any

from resonator_gen.calibration import Calibration
from resonator_gen.config import ConstraintsConfig, CpwConfig, ResonatorSpec
from resonator_gen.constraints import (
    check_bend_radius,
    check_pitch,
    effective_meander_pitch_um,
)
from resonator_gen.couplers import CapacitiveCoupler
from resonator_gen.cpw import CpwCrossSection
from resonator_gen.logging_config import get_logger
from resonator_gen.resonators.base import LengthBudget, ResonatorBuildResult, compute_length_budget

logger = get_logger(__name__)


class MeanderResonator:
    """λ/4 or λ/2 CPW meander resonator with a capacitive finger coupler."""

    def __init__(self, spec: ResonatorSpec) -> None:
        self.spec = spec
        self.coupler = CapacitiveCoupler.from_spec(spec.coupler)

    def _resolved_radius(self, cpw: CpwConfig) -> float:
        return self.spec.bend_radius_um if self.spec.bend_radius_um is not None else cpw.bend_radius_um

    def _resolved_pitch(self, cpw: CpwConfig) -> float:
        return self.spec.pitch_um if self.spec.pitch_um is not None else cpw.pitch_um

    def _enforce_constraints(self, cpw: CpwConfig, constraints: ConstraintsConfig | None) -> None:
        cfg = constraints or ConstraintsConfig()
        radius = self._resolved_radius(cpw)
        pitch = self._resolved_pitch(cpw)
        check_bend_radius(
            radius,
            cpw.width_um,
            cpw.gap_um,
            ratio_min=cfg.radius_ratio_min,
            hard_fail=cfg.hard_fail,
        )
        check_pitch(
            pitch,
            cpw.width_um,
            cpw.gap_um,
            ratio_min=cfg.pitch_ratio_min,
            hard_fail=cfg.hard_fail,
        )
        eff_pitch = effective_meander_pitch_um(radius)
        if eff_pitch + 1e-12 < pitch:
            msg = (
                f"KQC Meander effective fold pitch 2*r={eff_pitch:.3f} µm "
                f"is below requested pitch_um={pitch:.3f}; increase bend_radius_um"
            )
            if cfg.hard_fail:
                raise ValueError(msg)
            logger.warning(msg)

    def length_budget(self, calibration: Calibration) -> LengthBudget:
        """Return the length allocation for this resonator."""
        return compute_length_budget(self.spec, calibration, self.coupler)

    def build_standalone(
        self,
        layout: Any,
        calibration: Calibration,
        cpw: CpwConfig,
        *,
        constraints: ConstraintsConfig | None = None,
    ) -> ResonatorBuildResult:
        """Build coupler + meander into a top-level group cell (headless)."""
        from kqcircuits.elements.element import Element
        from kqcircuits.elements.meander import Meander
        from kqcircuits.pya_resolver import pya
        from kqcircuits.util.geometry_helper import get_cell_path_length

        self._enforce_constraints(cpw, constraints)
        budget = self.length_budget(calibration)
        radius = self._resolved_radius(cpw)
        cross = CpwCrossSection.from_config(cpw, bend_radius_um=radius)

        place = self.spec.placement
        span = place.meander_span_um
        if span < 4.0 * radius:
            raise ValueError(
                f"meander_span_um={span} must be >= 4*r={4.0 * radius} for {self.spec.name}"
            )
        if budget.body_length_um + 1e-6 < span:
            raise ValueError(
                f"body length {budget.body_length_um:.3f} µm < meander_span_um={span} "
                f"for {self.spec.name}; shorten the span or lower frequency correction"
            )

        # Local coordinates: coupler near origin, meander along +x.
        angle_rad = math.radians(place.orientation_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        def transform(x: float, y: float) -> tuple[float, float]:
            return (
                place.x_um + x * cos_a - y * sin_a,
                place.y_um + x * sin_a + y * cos_a,
            )

        top = layout.create_cell(self.spec.name)

        # Coupler at feed side (near x=0).
        coupler_cell = self.coupler.build(layout, cross)
        # FingerCapacitorSquare ports are along x; place with orientation.
        coupler_trans = pya.DCplxTrans(
            1.0,
            place.orientation_deg,
            False,
            pya.DVector(place.x_um, place.y_um),
        )
        top.insert(pya.DCellInstArray(coupler_cell.cell_index(), coupler_trans))

        # Meander starts after a short lead beyond the coupler.
        from resonator_gen.constants import COUPLER_LEAD_UM

        lead_um = COUPLER_LEAD_UM
        start_local = (lead_um + self.coupler.physical_length_um() + cross.width_um, 0.0)
        end_local = (start_local[0] + span, 0.0)
        start_xy = transform(*start_local)
        end_xy = transform(*end_local)

        term2 = 0.0 if self.spec.termination == "short" else (cross.width_um + 2.0 * cross.gap_um)

        meander_cell = Meander.create(
            layout,
            start_point=[start_xy[0], start_xy[1]],
            end_point=[end_xy[0], end_xy[1]],
            length=float(budget.body_length_um),
            meanders=int(self.spec.meanders),
            n_bridges=int(self.spec.n_bridges),
            **cross.as_kqc_kwargs(),
        )
        # Meander already transformed by absolute start/end points.
        top.insert(pya.DCellInstArray(meander_cell.cell_index(), pya.DTrans(0, False, 0, 0)))

        # Optional open termination tip as a tiny annotated path extension is
        # handled by WaveguideCoplanar term params; Meander does not expose them.
        # For open ends we append a short open stub waveguide.
        if term2 > 0.0:
            from kqcircuits.elements.waveguide_coplanar import WaveguideCoplanar

            tip_start = end_xy
            tip_end = transform(end_local[0] + term2, end_local[1])
            tip = WaveguideCoplanar.create(
                layout,
                path=[pya.DPoint(*tip_start), pya.DPoint(*tip_end)],
                term2=term2,
                **cross.as_kqc_kwargs(),
            )
            top.insert(pya.DCellInstArray(tip.cell_index(), pya.DTrans(0, False, 0, 0)))
            actual = get_cell_path_length(meander_cell) + get_cell_path_length(tip)
        else:
            actual = get_cell_path_length(meander_cell)

        logger.info(
            "%s: target=%.3f µm body=%.3f µm actual=%.6f µm",
            self.spec.name,
            budget.target_length_um,
            budget.body_length_um,
            actual,
        )
        # Silence unused Element import for type checkers using Protocol in GUI path
        _ = Element
        return ResonatorBuildResult(
            name=self.spec.name,
            frequency_hz=self.spec.frequency_hz,
            target_length_um=budget.target_length_um,
            actual_length_um=float(actual),
            body_length_um=budget.body_length_um,
            cell_instance=top,
        )

    def build(
        self,
        parent: Any,
        calibration: Calibration,
        cpw: CpwConfig,
        *,
        constraints: ConstraintsConfig | None = None,
    ) -> ResonatorBuildResult:
        """Build into a KQC parent Element via ``insert_cell`` when available."""
        if hasattr(parent, "insert_cell") and hasattr(parent, "layout"):
            return self._build_into_element(parent, calibration, cpw, constraints=constraints)
        layout = parent if hasattr(parent, "create_cell") else parent.layout()
        return self.build_standalone(layout, calibration, cpw, constraints=constraints)

    def _build_into_element(
        self,
        parent: Any,
        calibration: Calibration,
        cpw: CpwConfig,
        *,
        constraints: ConstraintsConfig | None = None,
    ) -> ResonatorBuildResult:
        from kqcircuits.elements.meander import Meander
        from kqcircuits.pya_resolver import pya
        from kqcircuits.util.geometry_helper import get_cell_path_length

        self._enforce_constraints(cpw, constraints)
        budget = self.length_budget(calibration)
        radius = self._resolved_radius(cpw)
        cross = CpwCrossSection.from_config(cpw, bend_radius_um=radius)
        place = self.spec.placement
        span = place.meander_span_um
        if span < 4.0 * radius:
            raise ValueError(
                f"meander_span_um={span} must be >= 4*r={4.0 * radius} for {self.spec.name}"
            )
        if budget.body_length_um + 1e-6 < span:
            raise ValueError(
                f"body length {budget.body_length_um:.3f} µm < meander_span_um={span}"
            )

        from resonator_gen.constants import COUPLER_LEAD_UM

        coupler_cell = self.coupler.build(parent.layout, cross)
        parent.insert_cell(
            coupler_cell,
            pya.DCplxTrans(1.0, place.orientation_deg, False, pya.DVector(place.x_um, place.y_um)),
            inst_name=f"{self.spec.name}_coupler",
        )

        angle_rad = math.radians(place.orientation_deg)
        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
        lead_um = COUPLER_LEAD_UM + self.coupler.physical_length_um() + cross.width_um

        def xf(x: float, y: float = 0.0) -> list[float]:
            return [
                place.x_um + x * cos_a - y * sin_a,
                place.y_um + x * sin_a + y * cos_a,
            ]

        start = xf(lead_um)
        end = xf(lead_um + span)
        _, meander_inst = parent.insert_cell(
            Meander,
            start_point=start,
            end_point=end,
            length=float(budget.body_length_um),
            meanders=int(self.spec.meanders),
            n_bridges=int(self.spec.n_bridges),
            inst_name=self.spec.name,
            **cross.as_kqc_kwargs(),
        )
        actual = get_cell_path_length(meander_inst.cell)
        return ResonatorBuildResult(
            name=self.spec.name,
            frequency_hz=self.spec.frequency_hz,
            target_length_um=budget.target_length_um,
            actual_length_um=float(actual),
            body_length_um=budget.body_length_um,
            cell_instance=meander_inst,
        )
