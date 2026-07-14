"""Anchored placement search tests: meander-math parity and synthetic regions."""

from __future__ import annotations

import random

import pytest

from resonator_gen.keepouts import KeepoutSet, rect_region
from resonator_gen.routing import (
    PlacementInfeasibleError,
    auto_meander_count,
    find_anchored_placement,
    meander_width_required_um,
    min_span_um,
)

DBU = 0.001
CPW_FOOTPRINT_UM = 10.0 + 2 * 6.0 + 2 * 5.0  # a + 2b + 2*margin = 32 µm


# ---------------------------------------------------------------------------
# Parity: our mirrored width math vs the installed KQC Meander geometry
# ---------------------------------------------------------------------------


def _kqc_meander_bbox_height_um(span_um: float, length_um: float, r_um: float, n: int) -> float:
    from kqcircuits.elements.meander import Meander
    from kqcircuits.pya_resolver import pya

    layout = pya.Layout()
    cell = Meander.create(
        layout,
        start_point=[0.0, 0.0],
        end_point=[span_um, 0.0],
        length=float(length_um),
        meanders=n,
        a=10,
        b=6,
        r=r_um,
    )
    bbox = cell.dbbox()
    return bbox.height()


def test_meander_width_parity_with_kqc() -> None:
    rng = random.Random(7)
    for _ in range(50):
        r = rng.uniform(80.0, 150.0)
        span = rng.uniform(4.2 * r, 12.0 * r)
        n = auto_meander_count(span, r)
        if n < 1:
            continue
        # Random target length above span, below the 90°-bend regime and beyond it.
        length = span + rng.uniform(50.0, 6.0 * r * n)
        width_pred = meander_width_required_um(span, length, r, n)
        bbox_h = _kqc_meander_bbox_height_um(span, length, r, n)
        # bbox height = meander perpendicular extent + CPW gap extent
        # (a/2 + b each side = 11 µm) + avoidance margin (5 µm each side).
        # For n == 1 KQC places the single fold on one side only, so the
        # geometric extent is width/2; for n >= 2 runs go to ±width/2.
        w_geo = bbox_h - 2 * (10.0 / 2 + 6.0) - 2 * 5.0
        expected_extent = width_pred / 2.0 if n == 1 else width_pred
        assert expected_extent == pytest.approx(w_geo, abs=0.05), (
            f"span={span} length={length} r={r} n={n}"
        )


def test_meander_width_zero_when_target_equals_span() -> None:
    assert meander_width_required_um(500.0, 500.0, 100.0, 1) == 0.0


def test_meander_width_rejects_short_target() -> None:
    with pytest.raises(ValueError):
        meander_width_required_um(500.0, 400.0, 100.0, 1)


def test_meander_width_rejects_small_span() -> None:
    with pytest.raises(ValueError):
        meander_width_required_um(100.0, 500.0, 100.0, 1)


# ---------------------------------------------------------------------------
# Synthetic keep-in regions with hand-computable answers
# ---------------------------------------------------------------------------


def _keep_in(die_w: float, die_h: float, keepouts: list[tuple[float, float, float, float]], clearance: float):
    die = rect_region(0.0, 0.0, die_w, die_h, DBU)
    ks = KeepoutSet(die, DBU)
    for x0, y0, x1, y1 in keepouts:
        ks.add(rect_region(x0, y0, x1, y1, DBU), "synthetic")
    return ks.keep_in_region(clearance)


def test_open_rectangle_places_meander() -> None:
    # 4000×3000 open die, anchor at bottom center pointing up.
    keep_in = _keep_in(4000.0, 3000.0, [], 0.0)
    result = find_anchored_placement(
        keep_in,
        DBU,
        start_um=(2000.0, 0.0),
        direction_deg=90.0,
        target_length_um=6000.0,
        bend_radius_um=100.0,
        cpw_footprint_um=CPW_FOOTPRINT_UM,
    )
    assert result.geometry == "meander"
    assert result.length_um >= min_span_um(100.0)
    # Corridor must fit inside the die width from the center: width <= 4000.
    assert result.width_um <= 4000.0
    # Feasibility invariant: required width at chosen span is what was used.
    n = result.n_meanders
    assert n is not None and n >= 1
    w = meander_width_required_um(result.length_um, 6000.0, 100.0, n)
    assert result.width_um == pytest.approx(w + CPW_FOOTPRINT_UM, abs=1e-6)


def test_notch_near_anchor_narrows_corridor() -> None:
    # Notch beside the anchor axis: grown keepout reaches x=2050, so a corridor
    # centered on x=2000 can be at most 100 µm wide (hand-computable bound).
    keep_in_notch = _keep_in(4000.0, 3000.0, [(2100.0, 0.0, 2600.0, 800.0)], 50.0)
    result = find_anchored_placement(
        keep_in_notch,
        DBU,
        start_um=(2000.0, 0.0),
        direction_deg=90.0,
        target_length_um=3000.0,
        bend_radius_um=100.0,
        cpw_footprint_um=CPW_FOOTPRINT_UM,
    )
    assert result.geometry == "meander"
    assert result.width_um <= 100.0 + 1e-6


def test_l_shaped_region() -> None:
    # Block the right half above y=1000: usable corridor is the left leg.
    keep_in = _keep_in(4000.0, 3000.0, [(2000.0, 1000.0, 4000.0, 3000.0)], 50.0)
    result = find_anchored_placement(
        keep_in,
        DBU,
        start_um=(1000.0, 0.0),
        direction_deg=90.0,
        target_length_um=5000.0,
        bend_radius_um=100.0,
        cpw_footprint_um=CPW_FOOTPRINT_UM,
    )
    assert result.geometry == "meander"
    # Corridor is centered on x=1000; must not cross into x>2000-50 region.
    assert 1000.0 + result.width_um / 2.0 <= 2000.0 - 50.0 + 1e-6


def test_region_with_hole() -> None:
    # An island keepout in the middle of the corridor axis.
    keep_in = _keep_in(4000.0, 4000.0, [(1900.0, 1500.0, 2100.0, 1700.0)], 50.0)
    result = find_anchored_placement(
        keep_in,
        DBU,
        start_um=(2000.0, 0.0),
        direction_deg=90.0,
        target_length_um=4000.0,
        bend_radius_um=100.0,
        cpw_footprint_um=CPW_FOOTPRINT_UM,
    )
    # The corridor must stop short of the island (span+lead below y=1450).
    assert result.length_um + CPW_FOOTPRINT_UM / 2.0 <= 1500.0 - 50.0 + 1e-6


def test_infeasible_raises_with_diagnostics() -> None:
    # Tiny die: no meander or spiral can fit 8 mm.
    keep_in = _keep_in(900.0, 900.0, [], 0.0)
    with pytest.raises(PlacementInfeasibleError) as excinfo:
        find_anchored_placement(
            keep_in,
            DBU,
            start_um=(450.0, 0.0),
            direction_deg=90.0,
            target_length_um=8000.0,
            bend_radius_um=100.0,
            cpw_footprint_um=CPW_FOOTPRINT_UM,
            clearance_um=66.0,
        )
    err = excinfo.value
    assert err.target_length_um == 8000.0
    assert err.clearance_um == 66.0
    assert "meander" in err.geometries_tried
    assert "spiral" in err.geometries_tried
    if err.best_feasible_length_um is not None:
        assert err.best_feasible_length_um < 8000.0
        assert err.shortfall_um is not None and err.shortfall_um > 0.0


def test_spiral_selected_for_square_region() -> None:
    # Meander corridor forced infeasible: preferred spiral in a square region.
    keep_in = _keep_in(2000.0, 2000.0, [], 0.0)
    result = find_anchored_placement(
        keep_in,
        DBU,
        start_um=(1000.0, 0.0),
        direction_deg=90.0,
        target_length_um=5000.0,
        bend_radius_um=100.0,
        cpw_footprint_um=CPW_FOOTPRINT_UM,
        preferred_geometry="spiral",
    )
    assert result.geometry == "spiral"
    aspect = max(result.length_um / result.width_um, result.width_um / result.length_um)
    assert aspect <= 2.0 + 1e-9


def test_meander_selected_for_long_thin_region() -> None:
    # 800 µm wide, 6000 µm tall strip: meander is the natural fit.
    keep_in = _keep_in(800.0, 6000.0, [], 0.0)
    result = find_anchored_placement(
        keep_in,
        DBU,
        start_um=(400.0, 0.0),
        direction_deg=90.0,
        target_length_um=7000.0,
        bend_radius_um=100.0,
        cpw_footprint_um=CPW_FOOTPRINT_UM,
    )
    assert result.geometry == "meander"


def test_determinism_of_search() -> None:
    keep_in = _keep_in(4000.0, 3000.0, [(500.0, 500.0, 900.0, 900.0)], 66.0)
    results = [
        find_anchored_placement(
            keep_in,
            DBU,
            start_um=(2000.0, 0.0),
            direction_deg=90.0,
            target_length_um=6500.0,
            bend_radius_um=100.0,
            cpw_footprint_um=CPW_FOOTPRINT_UM,
        )
        for _ in range(2)
    ]
    assert results[0] == results[1]
