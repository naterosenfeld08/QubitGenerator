"""CPW cross-section helpers mapped onto KQCircuits naming."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from resonator_gen.centerline import Centerline
from resonator_gen.config import CpwConfig


@dataclass(frozen=True)
class CpwCrossSection:
    """CPW dimensions using resonator_gen names and KQC ``a``/``b``/``r``."""

    width_um: float
    gap_um: float
    bend_radius_um: float

    @classmethod
    def from_config(cls, cpw: CpwConfig, bend_radius_um: float | None = None) -> CpwCrossSection:
        """Build a cross-section from a :class:`~resonator_gen.config.CpwConfig`."""
        return cls(
            width_um=cpw.width_um,
            gap_um=cpw.gap_um,
            bend_radius_um=cpw.bend_radius_um if bend_radius_um is None else bend_radius_um,
        )

    def as_kqc_kwargs(self) -> dict[str, float]:
        """Return kwargs accepted by KQC waveguide / meander elements."""
        return {"a": self.width_um, "b": self.gap_um, "r": self.bend_radius_um}


def waveguide_from_centerline(layout: Any, centerline: Centerline, cpw: CpwCrossSection, **extra: Any) -> Any:
    """Create a ``WaveguideCoplanar`` cell from a centerline corner path.

    Parameters
    ----------
    layout :
        KLayout ``Layout``.
    centerline :
        Analytic centerline.
    cpw :
        Cross-section.
    **extra :
        Extra KQC parameters (e.g. ``term1``, ``term2``).
    """
    from kqcircuits.elements.waveguide_coplanar import WaveguideCoplanar
    from kqcircuits.pya_resolver import pya

    points = [pya.DPoint(x, y) for x, y in centerline.to_corner_points_um()]
    return WaveguideCoplanar.create(layout, path=points, **cpw.as_kqc_kwargs(), **extra)
