"""Keep-in region clearance exactness tests (KLayout checks, no hand math)."""

from __future__ import annotations

import pytest

from resonator_gen.config import DieSpec, KeepoutEntry
from resonator_gen.keepouts import (
    KeepoutSet,
    die_region_from_spec,
    keepout_entry_region,
    rect_region,
)

DBU = 0.001


@pytest.fixture
def die_region():
    return die_region_from_spec(DieSpec(width_um=2000.0, height_um=2000.0, edge_margin_um=0.0), DBU)


def _separation_violations(region_a, region_b, distance_um: float) -> int:
    """Count separation violations between two regions below ``distance_um``."""
    from kqcircuits.pya_resolver import pya

    dist_dbu = int(round(distance_um / DBU))
    pairs = region_a.separation_check(region_b, dist_dbu)
    return pairs.count()


def test_keep_in_respects_clearance(die_region) -> None:
    ks = KeepoutSet(die_region, DBU)
    keepout = rect_region(900.0, 900.0, 1100.0, 1100.0, DBU)
    ks.add(keepout, "block")
    clearance_um = 66.0
    keep_in = ks.keep_in_region(clearance_um)
    assert not keep_in.is_empty()
    # No keep-in geometry closer than the clearance to the keepout.
    assert _separation_violations(keep_in, keepout, clearance_um - DBU) == 0


def test_keep_in_clearance_is_tight(die_region) -> None:
    """Boundary sits at exactly the clearance: probing slightly beyond finds it."""
    ks = KeepoutSet(die_region, DBU)
    keepout = rect_region(900.0, 900.0, 1100.0, 1100.0, DBU)
    ks.add(keepout, "block")
    clearance_um = 66.0
    keep_in = ks.keep_in_region(clearance_um)
    # Probe with clearance + 2 dbu must produce violations (edges are that close).
    assert _separation_violations(keep_in, keepout, clearance_um + 2 * DBU) > 0


def test_multiple_keepouts_union(die_region) -> None:
    ks = KeepoutSet(die_region, DBU)
    ks.add(rect_region(0.0, 0.0, 200.0, 200.0, DBU), "pad_sw")
    ks.add(rect_region(1800.0, 1800.0, 2000.0, 2000.0, DBU), "pad_ne")
    assert ks.sources() == ["pad_sw", "pad_ne"]
    keep_in = ks.keep_in_region(50.0)
    # Center point must remain inside keep-in.
    from kqcircuits.pya_resolver import pya

    probe = pya.Region(pya.Box(999_000, 999_000, 1_001_000, 1_001_000))
    assert (probe - keep_in).is_empty()


def test_keepout_entry_polygon() -> None:
    entry = KeepoutEntry(kind="polygon", points_um=[[0, 0], [100, 0], [50, 100]], source="marker")
    region = keepout_entry_region(entry, DBU)
    assert region.count() == 1
    assert region.area() > 0


def test_cache_invalidation(die_region) -> None:
    ks = KeepoutSet(die_region, DBU)
    empty_keep_in_area = ks.keep_in_region(10.0).area()
    ks.add(rect_region(0.0, 0.0, 500.0, 500.0, DBU), "late")
    assert ks.keep_in_region(10.0).area() < empty_keep_in_area
