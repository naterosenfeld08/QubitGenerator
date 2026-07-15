#!/usr/bin/env python3
"""Snap off-grid resonators in QubitFinalCooperGroup.gds onto the layout grid.

Context
-------
``QubitFinalCooperGroup.gds`` is a hand-ported hybrid: ``resonator_gen`` meander
resonators dropped into a base chip (feedline + bond pads + qubit couplers).
During porting, the two *bottom* resonators picked up sub-µm fractional offsets,
so their coupling arms no longer land on the 1 µm grid or line up with the
feedline / qubit-coupler geometry. The two *top* resonators are already exact.

Because a meander's arc vertices are irrational, we must NOT round vertices
(that would corrupt the meander and detune it). Instead we apply a single rigid
integer-nanometre translation per resonator. A rigid translation preserves the
centerline length exactly, so the resonant frequency is unchanged.

Transforms (derived in the chat diagnosis)
------------------------------------------
* Bottom-left resonator  (arm tip y=6.760, legs x=…​.78):
  mirror-align directly under the top-left resonator ->
  legs to x=2915/2935/2965/2985, tip flush at the feedline gap y=7.0.
  => translate by (dx, dy) = (-1.780, +0.240) µm.
* Bottom-right resonator  (arm tip y=-125.207, legs x=…​.354):
  snap to the nearest 1 µm grid (it couples through a qubit, so its arm is
  intentionally short of the feedline) ->
  => translate by (dx, dy) = (-0.354, +0.207) µm.

The resonators are identified robustly by their bounding boxes rather than by
shape index.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from kqcircuits.pya_resolver import pya

LAYER = (1, 0)

# Resonator identification (bbox top edge, µm) -> rigid translation (dx, dy) µm.
# Tolerance is generous; only the two bottom resonators match.
_BOTTOM_LEFT_TOP_UM = 6.760
_BOTTOM_RIGHT_TOP_UM = -125.207
_MATCH_TOL_UM = 0.05

BOTTOM_LEFT_SHIFT_UM = (-1.780, +0.240)
BOTTOM_RIGHT_SHIFT_UM = (-0.354, +0.207)


def _classify(top_um: float) -> tuple[float, float] | None:
    """Return the rigid shift (µm) for a shape given its bbox-top, else None."""
    if abs(top_um - _BOTTOM_LEFT_TOP_UM) <= _MATCH_TOL_UM:
        return BOTTOM_LEFT_SHIFT_UM
    if abs(top_um - _BOTTOM_RIGHT_TOP_UM) <= _MATCH_TOL_UM:
        return BOTTOM_RIGHT_SHIFT_UM
    return None


def align(input_path: Path, output_path: Path) -> None:
    """Read ``input_path``, snap the two bottom resonators, write ``output_path``."""
    layout = pya.Layout()
    layout.read(str(input_path))
    dbu = layout.dbu
    top = layout.top_cell()
    li = layout.layer(pya.LayerInfo(*LAYER))

    moved = 0
    shapes_layer = top.shapes(li)
    to_replace: list[tuple[pya.Shape, pya.Trans]] = []
    for s in shapes_layer.each():
        shift = _classify(s.bbox().top * dbu)
        if shift is None:
            continue
        dx_dbu = round(shift[0] / dbu)
        dy_dbu = round(shift[1] / dbu)
        to_replace.append((s, pya.Trans(pya.Vector(dx_dbu, dy_dbu))))

    for s, trans in to_replace:
        poly = s.polygon or s.simple_polygon
        if poly is None:
            continue
        shapes_layer.replace(s, poly.transformed(trans))
        moved += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output_path))
    print(f"Aligned {moved} resonator polygons; wrote {output_path}")

    # Report new coupling-arm positions for verification.
    layout2 = pya.Layout()
    layout2.read(str(output_path))
    top2 = layout2.top_cell()
    li2 = layout2.layer(pya.LayerInfo(*LAYER))
    for s in top2.shapes(li2).each():
        bb = s.bbox()
        t = bb.top * layout2.dbu
        if abs(t - 7.0) <= 1e-6 or abs(t - (-125.0)) <= 1e-6:
            print(f"  resonator now: bbox_top={t:.3f} µm  x=[{bb.left*layout2.dbu:.3f},{bb.right*layout2.dbu:.3f}]")


def main(argv: list[str] | None = None) -> int:
    default_in = Path.home() / "Desktop" / "Quantum Design" / "QubitFinalCooperGroup.gds"
    default_out = Path.home() / "Desktop" / "Quantum Design" / "QubitFinalCooperGroup_aligned.gds"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=default_in)
    parser.add_argument("--output", type=Path, default=default_out)
    args = parser.parse_args(argv)
    align(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
