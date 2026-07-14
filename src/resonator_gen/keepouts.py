"""Exact keepout / keep-in region algebra on KLayout Regions.

All boolean operations run on integer database units (dbu); micrometre
values are converted once at the boundary. No rasterization anywhere.
"""

from __future__ import annotations

from typing import Any

from resonator_gen.config import DieSpec, FeedlineSpec, KeepoutEntry
from resonator_gen.logging_config import get_logger

logger = get_logger(__name__)


def _pya() -> Any:
    from kqcircuits.pya_resolver import pya

    return pya


def um_to_dbu(value_um: float, dbu: float) -> int:
    """Convert micrometres to integer database units."""
    return int(round(value_um / dbu))


def rect_region(
    x_min_um: float,
    y_min_um: float,
    x_max_um: float,
    y_max_um: float,
    dbu: float,
) -> Any:
    """Axis-aligned rectangle as a Region in dbu."""
    pya = _pya()
    return pya.Region(
        pya.Box(
            um_to_dbu(x_min_um, dbu),
            um_to_dbu(y_min_um, dbu),
            um_to_dbu(x_max_um, dbu),
            um_to_dbu(y_max_um, dbu),
        )
    )


def polygon_region(points_um: list[list[float]], dbu: float) -> Any:
    """Simple polygon as a Region in dbu."""
    pya = _pya()
    pts = [pya.Point(um_to_dbu(x, dbu), um_to_dbu(y, dbu)) for x, y in points_um]
    return pya.Region(pya.Polygon(pts))


def die_region_from_spec(die: DieSpec, dbu: float) -> Any:
    """Die rectangle (before edge margin) as a Region."""
    x0, y0 = die.origin_um
    return rect_region(x0, y0, x0 + die.width_um, y0 + die.height_um, dbu)


def keepout_entry_region(entry: KeepoutEntry, dbu: float) -> Any:
    """Convert a config keepout entry to a Region."""
    if entry.kind == "rect":
        (x0, y0), (x1, y1) = entry.points_um[0], entry.points_um[-1]
        return rect_region(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), dbu)
    return polygon_region(entry.points_um, dbu)


def feedline_footprint_region(
    feedline: FeedlineSpec,
    half_width_um: float,
    dbu: float,
) -> Any:
    """Feedline polyline extruded to its CPW footprint (``a/2 + b`` half-width)."""
    pya = _pya()
    pts = [pya.Point(um_to_dbu(x, dbu), um_to_dbu(y, dbu)) for x, y in feedline.path_um]
    width_dbu = 2 * um_to_dbu(half_width_um, dbu)
    path = pya.Path(pts, width_dbu, width_dbu // 2, width_dbu // 2)
    return pya.Region(path.polygon())


def cell_region(cell: Any, layer_dt: tuple[int, int]) -> Any:
    """Flattened Region of a cell's shapes on ``(layer, datatype)``."""
    pya = _pya()
    layout = cell.layout()
    layer_index = layout.layer(pya.LayerInfo(layer_dt[0], layer_dt[1]))
    return pya.Region(cell.begin_shapes_rec(layer_index))


class KeepoutSet:
    """Accumulates keepout Regions and derives the exact keep-in region.

    Parameters
    ----------
    die_region :
        Die outline Region (already shrunk by any edge margin).
    dbu :
        Database unit of the layout in micrometres.
    """

    def __init__(self, die_region: Any, dbu: float) -> None:
        pya = _pya()
        self._die = die_region.dup()
        self._dbu = float(dbu)
        self._keepouts = pya.Region()
        self._sources: list[str] = []
        self._cache: dict[int, Any] = {}

    @property
    def dbu(self) -> float:
        """Database unit in micrometres."""
        return self._dbu

    def add(self, shape: Any, source: str) -> None:
        """Union a keepout Region into the set and invalidate the cache."""
        self._keepouts += shape
        self._keepouts.merge()
        self._sources.append(source)
        self._cache.clear()

    def sources(self) -> list[str]:
        """Names of all added keepout sources, in insertion order."""
        return list(self._sources)

    def grown(self, clearance_um: float) -> Any:
        """Keepouts grown isotropically by ``clearance_um``."""
        clearance_dbu = um_to_dbu(clearance_um, self._dbu)
        grown = self._keepouts.dup()
        if clearance_dbu > 0:
            grown.size(clearance_dbu)
            grown.merge()
        return grown

    def keep_in_region(self, clearance_um: float) -> Any:
        """Die minus grown keepouts; cached per clearance (in dbu)."""
        key = um_to_dbu(clearance_um, self._dbu)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._die - self.grown(clearance_um)
        result.merge()
        self._cache[key] = result
        return result
