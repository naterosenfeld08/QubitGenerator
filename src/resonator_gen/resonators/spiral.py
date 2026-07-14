"""Spiral readout resonator wrapping KQCircuits ``SpiralResonatorPolygon``."""

from __future__ import annotations

from typing import Any

from resonator_gen.calibration import Calibration
from resonator_gen.config import ConstraintsConfig, CpwConfig, ResonatorSpec
from resonator_gen.constraints import check_bend_radius, check_pitch
from resonator_gen.couplers import CapacitiveCoupler
from resonator_gen.cpw import CpwCrossSection
from resonator_gen.logging_config import get_logger
from resonator_gen.resonators.base import LengthBudget, ResonatorBuildResult, compute_length_budget

logger = get_logger(__name__)


class SpiralResonator:
    """Compact rectangular spiral resonator with a capacitive finger coupler."""

    def __init__(self, spec: ResonatorSpec) -> None:
        self.spec = spec
        self.coupler = CapacitiveCoupler.from_spec(spec.coupler)

    def _resolved_radius(self, cpw: CpwConfig) -> float:
        return self.spec.bend_radius_um if self.spec.bend_radius_um is not None else cpw.bend_radius_um

    def _resolved_pitch(self, cpw: CpwConfig) -> float:
        return self.spec.pitch_um if self.spec.pitch_um is not None else cpw.pitch_um

    def _enforce_constraints(self, cpw: CpwConfig, constraints: ConstraintsConfig | None) -> None:
        cfg = constraints or ConstraintsConfig()
        check_bend_radius(
            self._resolved_radius(cpw),
            cpw.width_um,
            cpw.gap_um,
            ratio_min=cfg.radius_ratio_min,
            hard_fail=cfg.hard_fail,
        )
        check_pitch(
            self._resolved_pitch(cpw),
            cpw.width_um,
            cpw.gap_um,
            ratio_min=cfg.pitch_ratio_min,
            hard_fail=cfg.hard_fail,
        )

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
        corridor_um: tuple[float, float] | None = None,
    ) -> ResonatorBuildResult:
        """Build spiral + coupler into a top-level group cell.

        Parameters
        ----------
        corridor_um :
            Optional ``(length, width)`` of the auto-placed corridor (µm).
            When given, the spiral polygon is sized to fit inside it; when
            None, legacy fixed spaces are used (manual mode).
        """
        import math

        from kqcircuits.elements.spiral_resonator_polygon import (
            SpiralResonatorPolygon,
            rectangular_parameters,
        )
        from kqcircuits.pya_resolver import pya
        from kqcircuits.util.geometry_helper import get_cell_path_length

        self._enforce_constraints(cpw, constraints)
        budget = self.length_budget(calibration)
        radius = self._resolved_radius(cpw)
        pitch = self._resolved_pitch(cpw)
        cross = CpwCrossSection.from_config(cpw, bend_radius_um=radius)
        place = self.spec.placement

        top = layout.create_cell(self.spec.name)
        coupler_cell = self.coupler.build(layout, cross)
        coupler_trans = pya.DCplxTrans(
            1.0,
            place.orientation_deg,
            False,
            pya.DVector(place.x_um, place.y_um),
        )
        top.insert(pya.DCellInstArray(coupler_cell.cell_index(), coupler_trans))

        kqc = cross.as_kqc_kwargs()
        footprint_um = cross.width_um + 2.0 * cross.gap_um
        if corridor_um is not None:
            corridor_length_um, corridor_width_um = corridor_um
            half = max(radius, corridor_width_um / 2.0 - footprint_um / 2.0)
            params = rectangular_parameters(
                above_space=half,
                below_space=half,
                right_space=max(2.0 * radius, corridor_length_um - footprint_um / 2.0),
                x_spacing=pitch,
                y_spacing=pitch,
                r=radius,
                length=float(budget.body_length_um),
                a=kqc["a"],
                b=kqc["b"],
            )
        else:
            params = rectangular_parameters(
                above_space=500,
                below_space=400,
                right_space=max(800.0, place.meander_span_um * 0.75),
                x_spacing=pitch,
                y_spacing=pitch,
                r=radius,
                length=float(budget.body_length_um),
                a=kqc["a"],
                b=kqc["b"],
            )
        spiral_cell = SpiralResonatorPolygon.create(layout, **params)
        lead_um = 100.0 + self.coupler.physical_length_um()
        angle_rad = math.radians(place.orientation_deg)
        spiral_trans = pya.DCplxTrans(
            1.0,
            place.orientation_deg,
            False,
            pya.DVector(
                place.x_um + lead_um * math.cos(angle_rad),
                place.y_um + lead_um * math.sin(angle_rad),
            ),
        )
        top.insert(pya.DCellInstArray(spiral_cell.cell_index(), spiral_trans))
        actual = get_cell_path_length(spiral_cell)
        logger.info(
            "%s spiral: target=%.3f µm body=%.3f µm actual=%.6f µm",
            self.spec.name,
            budget.target_length_um,
            budget.body_length_um,
            actual,
        )
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
        """Build into a layout or parent Element."""
        layout = parent if hasattr(parent, "create_cell") else parent.layout
        return self.build_standalone(layout, calibration, cpw, constraints=constraints)
