"""Anchored, keepout-aware placement search.

Mirrors the width-solving math of KQCircuits ``Meander`` (v4.9.x,
``kqcircuits/elements/meander.py``) as pure functions, then searches a
deterministic grid of corridor lengths for the minimum-footprint anchored
rectangle that fits the target resonator length.

All Region tests are exact integer-dbu booleans; no rasterization.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, pi, sqrt
from typing import Any, Literal

from scipy.optimize import brentq

from resonator_gen.constants import (
    PLACEMENT_GRID_STEP_RATIO,
    PLACEMENT_REFINE_POINTS,
    SPIRAL_ASPECT_RATIO_MAX,
)
from resonator_gen.keepouts import um_to_dbu
from resonator_gen.logging_config import get_logger

logger = get_logger(__name__)

GeometryName = Literal["meander", "spiral"]


@dataclass(frozen=True)
class PlacementResult:
    """Solved anchored corridor for one resonator."""

    start_um: tuple[float, float]
    direction_deg: float
    length_um: float
    width_um: float
    geometry: GeometryName
    n_meanders: int | None


class PlacementInfeasibleError(RuntimeError):
    """No anchored rectangle fits the target length for any geometry tried."""

    def __init__(
        self,
        message: str,
        *,
        target_length_um: float,
        best_feasible_length_um: float | None,
        shortfall_um: float | None,
        geometries_tried: tuple[str, ...],
        clearance_um: float,
    ) -> None:
        super().__init__(message)
        self.target_length_um = target_length_um
        self.best_feasible_length_um = best_feasible_length_um
        self.shortfall_um = shortfall_um
        self.geometries_tried = geometries_tried
        self.clearance_um = clearance_um


# ---------------------------------------------------------------------------
# Mirrored KQC Meander width math (kqcircuits/elements/meander.py, 4.9.x)
# ---------------------------------------------------------------------------


def bend_length_increment_um(w_um: float, r_um: float) -> float:
    """Length increment of one bend vs. straight, as a function of bend width."""
    if w_um >= r_um:
        return r_um * (pi / 2 - 2) + w_um
    h = w_um / r_um
    x = (1 - h) / (1 - h / 2)
    return r_um * (2 * atan(1 - x) + (x + h * (h - 1)) / sqrt(x**2 + h**2) - 1)


def meander_length_increment_um(w_um: float, r_um: float, n_meanders: int) -> float:
    """Total length increment of all meander bends for meander width ``w_um``."""
    l0 = bend_length_increment_um(w_um / 4, r_um)
    l1 = bend_length_increment_um(w_um / 2, r_um)
    return 4 * l0 + 2 * (n_meanders - 1) * l1


def auto_meander_count(span_um: float, r_um: float) -> int:
    """KQC's automatic meander count: ``floor(span / 2r) - 1``."""
    return int(span_um / (2 * r_um) - 1)


def meander_width_required_um(
    span_um: float,
    body_length_um: float,
    bend_radius_um: float,
    n_meanders: int,
) -> float:
    """Perpendicular meander extent required to hit ``body_length_um``.

    Parameters
    ----------
    span_um :
        Straight-line distance between meander start and end (``l_direct``).
    body_length_um :
        Target waveguide length.
    bend_radius_um :
        Bend radius ``r``.
    n_meanders :
        Number of meanders (must be ≥ 1).

    Returns
    -------
    float
        Meander width ``W`` (total perpendicular extent is ``W``, i.e. runs
        at ±W/2 around the axis). Zero when the target equals the span.

    Raises
    ------
    ValueError
        If the configuration cannot produce the target length.
    """
    if span_um < 4 * bend_radius_um:
        raise ValueError(f"span_um={span_um} must be >= 4*r={4 * bend_radius_um}")
    if n_meanders < 1:
        raise ValueError(f"n_meanders must be >= 1, got {n_meanders}")
    target_increment = body_length_um - span_um
    if target_increment < -1e-3:
        raise ValueError(
            f"body_length_um={body_length_um} shorter than span_um={span_um}"
        )
    if target_increment <= 1e-3:
        return 0.0
    r = bend_radius_um
    min_90deg_increment = meander_length_increment_um(4 * r, r, n_meanders)
    if target_increment >= min_90deg_increment:
        return 4 * r + (target_increment - min_90deg_increment) / n_meanders
    return float(
        brentq(
            lambda w: meander_length_increment_um(w, r, n_meanders) - target_increment,
            0.0,
            4 * r,
        )
    )


def min_span_um(bend_radius_um: float) -> float:
    """Minimum meander span accepted by KQC (``4·r``)."""
    return 4.0 * bend_radius_um


# ---------------------------------------------------------------------------
# Anchored rectangle search
# ---------------------------------------------------------------------------


def _pya() -> Any:
    from kqcircuits.pya_resolver import pya

    return pya


def _to_local_frame(keep_in_region: Any, start_um: tuple[float, float], direction_deg: float, dbu: float) -> Any:
    """Transform the keep-in region so the anchor is at origin, direction +x."""
    pya = _pya()
    # ICplxTrans applies rotation before displacement; we need translate-then-rotate.
    translate = pya.ICplxTrans(1.0, 0.0, False, -um_to_dbu(start_um[0], dbu), -um_to_dbu(start_um[1], dbu))
    rotate = pya.ICplxTrans(1.0, -direction_deg, False, 0, 0)
    local = keep_in_region.transformed(translate)
    return local.transformed(rotate)


def _rect_contained(keep_in_local: Any, x0_um: float, x1_um: float, half_w_um: float, dbu: float) -> bool:
    """True if the axis-aligned rectangle is fully inside the keep-in region."""
    pya = _pya()
    box = pya.Region(
        pya.Box(
            um_to_dbu(x0_um, dbu),
            um_to_dbu(-half_w_um, dbu),
            um_to_dbu(x1_um, dbu),
            um_to_dbu(half_w_um, dbu),
        )
    )
    return (box - keep_in_local).is_empty()


def _max_reach_um(keep_in_local: Any, dbu: float, limit_um: float, from_um: float = 0.0) -> float:
    """Furthest x such that a thin corridor [from_um, x] × ±1 dbu stays inside."""
    lo, hi = from_um, max(limit_um, from_um)
    thin_um = 2 * dbu
    if not _rect_contained(keep_in_local, from_um, from_um + dbu, thin_um, dbu):
        return from_um
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _rect_contained(keep_in_local, from_um, mid, thin_um, dbu):
            lo = mid
        else:
            hi = mid
    return lo


def _max_width_um(keep_in_local: Any, x0_um: float, x1_um: float, dbu: float, limit_um: float) -> float:
    """Largest half-width×2 (centered) such that the corridor stays inside."""
    lo, hi = 0.0, limit_um
    if not _rect_contained(keep_in_local, x0_um, x1_um, dbu, dbu):
        return 0.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _rect_contained(keep_in_local, x0_um, x1_um, mid / 2.0, dbu):
            lo = mid
        else:
            hi = mid
    return lo


@dataclass(frozen=True)
class _Candidate:
    span_um: float
    corridor_width_um: float
    n_meanders: int
    area: float


def _meander_candidate(
    keep_in_local: Any,
    dbu: float,
    span_um: float,
    lead_um: float,
    target_length_um: float,
    bend_radius_um: float,
    cpw_footprint_um: float,
) -> _Candidate | None:
    """Evaluate feasibility of one corridor length; None if infeasible."""
    n = auto_meander_count(span_um, bend_radius_um)
    if n < 1 or target_length_um < span_um:
        return None
    try:
        w_meander = meander_width_required_um(span_um, target_length_um, bend_radius_um, n)
    except ValueError:
        return None
    corridor_w = w_meander + cpw_footprint_um
    # Corridor covers the meander body only; the coupler + lead segment
    # (x < lead_um) is fixed pre-existing geometry at the tap.
    if not _rect_contained(
        keep_in_local, lead_um, lead_um + span_um + cpw_footprint_um / 2.0, corridor_w / 2.0, dbu
    ):
        return None
    return _Candidate(
        span_um=span_um,
        corridor_width_um=corridor_w,
        n_meanders=n,
        area=span_um * corridor_w,
    )


def find_anchored_placement(
    keep_in_region: Any,
    dbu: float,
    start_um: tuple[float, float],
    direction_deg: float,
    target_length_um: float,
    bend_radius_um: float,
    cpw_footprint_um: float,
    *,
    lead_um: float = 0.0,
    clearance_um: float = 0.0,
    preferred_geometry: Literal["auto", "meander", "spiral"] = "auto",
) -> PlacementResult:
    """Find the minimum-footprint anchored corridor fitting the target length.

    Parameters
    ----------
    keep_in_region :
        Exact keep-in Region (die minus grown keepouts), in dbu.
    dbu :
        Database unit in micrometres.
    start_um, direction_deg :
        Fixed coupler tap anchor and direction (no direction search).
    target_length_um :
        Waveguide body length the meander must realize.
    bend_radius_um :
        Minimum bend radius.
    cpw_footprint_um :
        Full transverse CPW footprint including protection margin
        (``a + 2b + 2·margin``).
    lead_um :
        Straight lead length between anchor and meander start (occupies
        corridor length but not meander span).
    clearance_um :
        Clearance used (diagnostics only; region is already grown).
    preferred_geometry :
        Restrict to one geometry, or ``auto`` to try meander then spiral.

    Raises
    ------
    PlacementInfeasibleError
        With diagnostics when nothing fits.
    """
    local = _to_local_frame(keep_in_region, start_um, direction_deg, dbu)
    bbox = local.bbox()
    if bbox.empty():
        raise PlacementInfeasibleError(
            "Keep-in region is empty",
            target_length_um=target_length_um,
            best_feasible_length_um=None,
            shortfall_um=target_length_um,
            geometries_tried=(),
            clearance_um=clearance_um,
        )
    limit_um = (bbox.width() + bbox.height()) * dbu
    reach_um = _max_reach_um(local, dbu, limit_um, from_um=lead_um)
    geometries_tried: list[str] = []

    r = bend_radius_um
    step_um = PLACEMENT_GRID_STEP_RATIO * r
    span_min = min_span_um(r)
    span_max = reach_um - lead_um - cpw_footprint_um / 2.0

    best: _Candidate | None = None
    best_feasible_length: float | None = None

    if preferred_geometry in ("auto", "meander"):
        geometries_tried.append("meander")
        # Deterministic grid scan.
        n_steps = max(0, int((span_max - span_min) / step_um) + 1)
        for i in range(n_steps):
            span = span_min + i * step_um
            if span > span_max:
                break
            cand = _meander_candidate(
                local, dbu, span, lead_um, target_length_um, r, cpw_footprint_um
            )
            if cand is not None and (best is None or cand.area < best.area):
                best = cand
        # Track best feasible length for diagnostics even if target infeasible.
        if best is None and n_steps > 0:
            for i in range(n_steps):
                span = span_min + i * step_um
                if span > span_max:
                    break
                n = auto_meander_count(span, r)
                if n < 1:
                    continue
                w_avail = _max_width_um(
                    local, lead_um, lead_um + span + cpw_footprint_um / 2.0, dbu, limit_um
                )
                w_meander = max(0.0, w_avail - cpw_footprint_um)
                if w_meander <= 0.0:
                    continue
                capacity = span + meander_length_increment_um(w_meander, r, n)
                if best_feasible_length is None or capacity > best_feasible_length:
                    best_feasible_length = capacity
        # Local refinement around the best candidate.
        if best is not None:
            lo = max(span_min, best.span_um - step_um)
            hi = min(span_max, best.span_um + step_um)
            for j in range(PLACEMENT_REFINE_POINTS):
                span = lo + (hi - lo) * j / (PLACEMENT_REFINE_POINTS - 1)
                cand = _meander_candidate(
                    local, dbu, span, lead_um, target_length_um, r, cpw_footprint_um
                )
                if cand is not None and cand.area < best.area:
                    best = cand
            logger.info(
                "Anchored meander placement: span=%.3f µm width=%.3f µm n=%d area=%.0f µm²",
                best.span_um,
                best.corridor_width_um,
                best.n_meanders,
                best.area,
            )
            return PlacementResult(
                start_um=start_um,
                direction_deg=direction_deg,
                length_um=best.span_um,
                width_um=best.corridor_width_um,
                geometry="meander",
                n_meanders=best.n_meanders,
            )

    if preferred_geometry in ("auto", "spiral"):
        geometries_tried.append("spiral")
        result = _spiral_placement(
            local,
            dbu,
            start_um,
            direction_deg,
            target_length_um,
            r,
            cpw_footprint_um,
            lead_um=lead_um,
            reach_um=reach_um,
            limit_um=limit_um,
        )
        if result is not None:
            return result

    shortfall = (
        None
        if best_feasible_length is None
        else max(0.0, target_length_um - best_feasible_length)
    )
    raise PlacementInfeasibleError(
        f"No anchored placement fits target length {target_length_um:.1f} µm "
        f"(best feasible ≈ {best_feasible_length!r} µm, clearance {clearance_um:.1f} µm, "
        f"tried: {', '.join(geometries_tried) or 'none'})",
        target_length_um=target_length_um,
        best_feasible_length_um=best_feasible_length,
        shortfall_um=shortfall,
        geometries_tried=tuple(geometries_tried),
        clearance_um=clearance_um,
    )


def _spiral_placement(
    keep_in_local: Any,
    dbu: float,
    start_um: tuple[float, float],
    direction_deg: float,
    target_length_um: float,
    bend_radius_um: float,
    cpw_footprint_um: float,
    *,
    lead_um: float,
    reach_um: float,
    limit_um: float,
) -> PlacementResult | None:
    """Best anchored rectangle for a spiral (roughly square footprint).

    Uses an analytic capacity estimate ``area / pitch`` with the corridor
    aspect capped at :data:`SPIRAL_ASPECT_RATIO_MAX`; the actual spiral build
    (existing ``SpiralResonator``) will still verify realized length exactly.
    """
    r = bend_radius_um
    step_um = PLACEMENT_GRID_STEP_RATIO * r
    best_rect: tuple[float, float] | None = None  # (length, width)
    best_area = 0.0
    span_min = 2.0 * r
    length = span_min
    while length <= reach_um - lead_um:
        w_avail = _max_width_um(keep_in_local, lead_um, lead_um + length, dbu, limit_um)
        if w_avail > cpw_footprint_um:
            area = length * w_avail
            aspect = max(length / w_avail, w_avail / length)
            if aspect <= SPIRAL_ASPECT_RATIO_MAX and area > best_area:
                best_area = area
                best_rect = (length, w_avail)
        length += step_um
    if best_rect is None:
        return None
    length_um, width_um = best_rect
    # Rough capacity: spiral fills the rectangle at pitch ~ 2r between runs.
    pitch = 2.0 * r
    capacity = (length_um * width_um) / pitch
    if capacity < target_length_um:
        return None
    logger.info(
        "Anchored spiral placement: rect %.1f × %.1f µm (capacity ≈ %.0f µm)",
        length_um,
        width_um,
        capacity,
    )
    return PlacementResult(
        start_um=start_um,
        direction_deg=direction_deg,
        length_um=length_um,
        width_um=width_um,
        geometry="spiral",
        n_meanders=None,
    )
