"""Capacitive coupler primitives wrapping KQCircuits finger capacitors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from resonator_gen.calibration import Calibration
from resonator_gen.config import CouplerSpec
from resonator_gen.cpw import CpwCrossSection
from resonator_gen.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CapacitiveCoupler:
    """Finger (interdigital) capacitive coupler.

    Parameters
    ----------
    finger_number, finger_width_um, finger_gap_um, finger_length_um, ground_padding_um :
        Geometry passed through to ``FingerCapacitorSquare``.
    """

    finger_number: int = 5
    finger_width_um: float = 5.0
    finger_gap_um: float = 3.0
    finger_length_um: float = 20.0
    ground_padding_um: float = 20.0

    @classmethod
    def from_spec(cls, spec: CouplerSpec) -> CapacitiveCoupler:
        """Build from a :class:`~resonator_gen.config.CouplerSpec`."""
        if spec.topology != "finger":
            raise ValueError(f"Unsupported coupler topology {spec.topology!r} in v1")
        return cls(
            finger_number=spec.finger_number,
            finger_width_um=spec.finger_width_um,
            finger_gap_um=spec.finger_gap_um,
            finger_length_um=spec.finger_length_um,
            ground_padding_um=spec.ground_padding_um,
        )

    def physical_length_um(self) -> float:
        """Conservative geometric length contributed by the finger region.

        Notes
        -----
        Exact electrical loading is handled by ``Calibration.coupler_dL_um``.
        This returns the finger length as a geometric placeholder used when
        budgeting port-to-port placement, not as the EM dL itself.
        """
        return float(self.finger_length_um)

    def effective_length_um(self, calibration: Calibration) -> float:
        """Physical placeholder + calibrated coupler electrical length."""
        return self.physical_length_um() + calibration.coupler_dL_um

    def build(self, layout: Any, cpw: CpwCrossSection, **extra: Any) -> Any:
        """Create a ``FingerCapacitorSquare`` cell in ``layout``."""
        from kqcircuits.elements.finger_capacitor_square import FingerCapacitorSquare

        params = {
            **cpw.as_kqc_kwargs(),
            "finger_number": self.finger_number,
            "finger_width": self.finger_width_um,
            "finger_gap": self.finger_gap_um,
            "finger_length": self.finger_length_um,
            "ground_padding": self.ground_padding_um,
            **extra,
        }
        logger.debug("Building FingerCapacitorSquare with %s", params)
        return FingerCapacitorSquare.create(layout, **params)
