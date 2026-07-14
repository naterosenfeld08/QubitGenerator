"""Design-rule checks for bend radius and meander pitch."""

from __future__ import annotations

from dataclasses import dataclass

from resonator_gen.constants import DEFAULT_PITCH_RATIO_MIN, DEFAULT_RADIUS_RATIO_MIN
from resonator_gen.logging_config import get_logger

logger = get_logger(__name__)


class ConstraintError(ValueError):
    """Hard design-rule violation."""


@dataclass(frozen=True)
class ConstraintResult:
    """Outcome of a soft/hard design-rule check."""

    ok: bool
    messages: tuple[str, ...]


def footprint_um(width_um: float, gap_um: float) -> float:
    """Return ``w + 2·g`` in micrometres."""
    return width_um + 2.0 * gap_um


def check_bend_radius(
    bend_radius_um: float,
    width_um: float,
    gap_um: float,
    *,
    ratio_min: float = DEFAULT_RADIUS_RATIO_MIN,
    hard_fail: bool = False,
) -> ConstraintResult:
    """Validate bend radius against ``ratio_min * (w + 2g)``.

    Parameters
    ----------
    bend_radius_um :
        Intended bend radius.
    width_um, gap_um :
        CPW cross-section.
    ratio_min :
        Minimum allowed ``r / (w + 2g)``.
    hard_fail :
        If True, raise :class:`ConstraintError` on violation; else warn.
    """
    minimum_um = ratio_min * footprint_um(width_um, gap_um)
    if bend_radius_um + 1e-12 >= minimum_um:
        return ConstraintResult(ok=True, messages=())
    msg = (
        f"bend_radius_um={bend_radius_um:.3f} is below "
        f"ratio_min*footprint={minimum_um:.3f} µm "
        f"(ratio_min={ratio_min}, w={width_um}, g={gap_um})"
    )
    if hard_fail:
        raise ConstraintError(msg)
    logger.warning(msg)
    return ConstraintResult(ok=False, messages=(msg,))


def check_pitch(
    pitch_um: float,
    width_um: float,
    gap_um: float,
    *,
    ratio_min: float = DEFAULT_PITCH_RATIO_MIN,
    hard_fail: bool = False,
) -> ConstraintResult:
    """Validate meander/spiral pitch against ``ratio_min * (w + 2g)``."""
    minimum_um = ratio_min * footprint_um(width_um, gap_um)
    if pitch_um + 1e-12 >= minimum_um:
        return ConstraintResult(ok=True, messages=())
    msg = (
        f"pitch_um={pitch_um:.3f} is below "
        f"ratio_min*footprint={minimum_um:.3f} µm "
        f"(ratio_min={ratio_min}, w={width_um}, g={gap_um})"
    )
    if hard_fail:
        raise ConstraintError(msg)
    logger.warning(msg)
    return ConstraintResult(ok=False, messages=(msg,))


def effective_meander_pitch_um(bend_radius_um: float) -> float:
    """KQC ``Meander`` spaces successive folds by ``2 * r`` along the axis."""
    return 2.0 * bend_radius_um
