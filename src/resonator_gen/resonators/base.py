"""Shared resonator interfaces and length budgeting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from resonator_gen.calibration import Calibration
from resonator_gen.config import CpwConfig, ResonatorSpec
from resonator_gen.couplers import CapacitiveCoupler


@dataclass(frozen=True)
class ResonatorBuildResult:
    """Outcome of building one resonator into a layout."""

    name: str
    frequency_hz: float
    target_length_um: float
    actual_length_um: float
    body_length_um: float
    cell_instance: Any


@dataclass(frozen=True)
class LengthBudget:
    """Split of target electrical length into coupler + body."""

    target_length_um: float
    coupler_effective_um: float
    body_length_um: float


def compute_length_budget(
    spec: ResonatorSpec,
    calibration: Calibration,
    coupler: CapacitiveCoupler,
) -> LengthBudget:
    """Allocate geometric body length from frequency and coupler loading.

    The meander/spiral is sized to ``body_length_um``. The calibrated coupler
    contribution (``coupler_dL_um``) is already removed inside
    ``Calibration.body_length_um``. The coupler physical length is *not*
    subtracted again from the body: KQC meanders are specified by their own
    waveguide length; the coupler sits in series and its EM effect is captured
    by ``coupler_dL_um``.
    """
    target = calibration.target_length_um(spec.frequency_hz, mode=spec.mode)
    coupler_eff = coupler.effective_length_um(calibration)
    # Body uses calibration correction only (physical finger length is layout,
    # not series waveguide length of the resonator line).
    body = calibration.body_length_um(spec.frequency_hz, mode=spec.mode)
    if body <= 0.0:
        raise ValueError(
            f"Body length for {spec.name} is non-positive ({body} µm); "
            "reduce coupler_dL_um or lower frequency"
        )
    return LengthBudget(
        target_length_um=target,
        coupler_effective_um=coupler_eff,
        body_length_um=body,
    )


class ResonatorBase(Protocol):
    """Protocol for geometry backends (meander / spiral)."""

    spec: ResonatorSpec

    def build(
        self,
        parent: Any,
        calibration: Calibration,
        cpw: CpwConfig,
        *,
        hard_fail: bool = False,
        radius_ratio_min: float = 3.0,
        pitch_ratio_min: float = 3.0,
    ) -> ResonatorBuildResult: ...
