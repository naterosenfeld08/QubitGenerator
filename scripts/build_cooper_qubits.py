#!/usr/bin/env python3
"""Add transmon qubits to QubitFinalCooperGroup (Phase 2).

The Cooper chip is drawn in NEGATIVE tone on layer 1/0 (drawn polygons = etched
gaps; undrawn = superconducting metal). The reference qubit in ChipDesign.gds is
positive tone, so a transmon here must be drawn as a *gap moat* that defines a
metal island, rather than as a solid island.

This module builds a single-island transmon (matching the reference dimensions:
55 um island, 30x5 um neck) connected to its resonator's claw center conductor,
and grounded through a Josephson junction. The JJ is placed on a dedicated layer
(2/0) as small metal leads bridging a break in the neck-to-ground gap, since a
real junction is a separate fabrication step, not part of the base etch mask.

Currently builds the BOTTOM-RIGHT transmon as the validated template; the other
three follow once the template is confirmed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from kqcircuits.pya_resolver import pya

GAP_LAYER = (1, 0)
JJ_LAYER = (2, 0)

# Reference transmon dimensions (um), from ChipDesign.gds / build_quantum_chip.rb.
ISLAND = 55.0
NECK_L = 30.0
NECK_W = 5.0
MOAT = 20.0
JJ_BREAK = 5.0  # gap the JJ bridges between neck tip and ground


@dataclass(frozen=True)
class ClawEnd:
    """Geometry of a resonator claw's metal center-conductor end.

    The center conductor is the metal strip ``y in [cc_lo, cc_hi]`` whose open
    end faces ``-x`` at ``x = x_end`` (i.e. the island attaches on the left).
    """

    x_end: float
    cc_lo: float
    cc_hi: float


def _box(x1: float, y1: float, x2: float, y2: float, dbu: float) -> pya.Box:
    return pya.Box(round(x1 / dbu), round(y1 / dbu), round(x2 / dbu), round(y2 / dbu))


def build_transmon_left(claw: ClawEnd, dbu: float) -> tuple[pya.Region, pya.Region]:
    """Build a transmon whose island attaches to ``claw`` and extends toward -x.

    Returns
    -------
    (gap_region, jj_region)
        ``gap_region`` are the negative-tone moat polygons for layer 1/0;
        ``jj_region`` are the junction leads for the JJ layer.
    """
    cc_mid = 0.5 * (claw.cc_lo + claw.cc_hi)
    # Island: right edge sits just left of the claw end, vertically centered on cc.
    isl_x2 = claw.x_end - MOAT  # leave clearance; link bridges the moat
    isl_x1 = isl_x2 - ISLAND
    isl_y1 = cc_mid - ISLAND / 2.0
    isl_y2 = cc_mid + ISLAND / 2.0

    # Metal we must preserve (NOT etched):
    island = pya.Region(_box(isl_x1, isl_y1, isl_x2, isl_y2, dbu))
    link = pya.Region(_box(isl_x2, claw.cc_lo, claw.x_end, claw.cc_hi, dbu))
    neck_x2 = isl_x1
    neck_x1 = neck_x2 - NECK_L
    neck = pya.Region(_box(neck_x1, cc_mid - NECK_W / 2.0, neck_x2, cc_mid + NECK_W / 2.0, dbu))
    keep = island + link + neck

    # Moat: a filled rectangle around the island/neck, minus the metal we keep,
    # minus the JJ break (so a metal fin of neck reaches the break for the JJ).
    moat_x1 = neck_x1 - JJ_BREAK
    moat = pya.Region(_box(moat_x1, isl_y1 - MOAT, claw.x_end, isl_y2 + MOAT, dbu))
    gap = moat - keep

    # JJ: two overlapping leads on the JJ layer bridging the break between the
    # neck tip (x=neck_x1) and ground (x<moat_x1) at the center-conductor height.
    jj = pya.Region()
    jj += pya.Region(_box(neck_x1 - JJ_BREAK * 0.6, cc_mid - 0.5, neck_x1 + 0.5, cc_mid + 0.5, dbu))
    jj += pya.Region(_box(neck_x1 - JJ_BREAK * 0.6, cc_mid - 0.3, neck_x1 - JJ_BREAK * 0.2, cc_mid + 0.3, dbu))
    return gap, jj


# Feedline gap outer edges (um): lower gap [7,32], upper gap [75,100]; the CPW
# is symmetric about y = 53.5.
FEED_MID = 53.5

# Resonators are identical meanders up to an x-translation. Each entry gives the
# resonator's center-conductor x-center and the bbox-top used to identify it.
# `above` = resonator sits above the feedline (arm points down).
# The bottom-right (x_center 4751, arm already pulled back) is the template.
BR_X_CENTER = 4751.0
PULLBACK = 132.0  # move each flush resonator this far from the feedline

RESONATORS = [
    # (name, bbox_top_um, x_center, above)
    ("bottom_left", 7.0, 2950.0, False),
    ("top_left", 2700.0, 2950.0, True),
    ("top_right", 2100.0, 5200.0, True),
]

# Bounding box (um) enclosing exactly the bottom-right claw+qubit unit on 1/0.
_UNIT_BOX_UM = (4490.0, -130.0, 4790.0, -10.0)


def _unit_polygons(top: pya.Cell, li_gap: int, li_jj: int, dbu: float):
    """Collect the bottom-right claw+qubit polygons (gap + JJ) to replicate."""
    x1, y1, x2, y2 = _UNIT_BOX_UM
    sel = pya.Box(round(x1 / dbu), round(y1 / dbu), round(x2 / dbu), round(y2 / dbu))
    gap_polys = []
    for s in top.shapes(li_gap).each():
        if sel.contains(s.bbox().p1) and sel.contains(s.bbox().p2):
            poly = s.polygon or s.simple_polygon
            if poly is not None:
                gap_polys.append(poly.dup())
    jj_polys = [(s.polygon or s.simple_polygon).dup() for s in top.shapes(li_jj).each()]
    return gap_polys, jj_polys


def build(input_path: Path, output_path: Path) -> None:
    layout = pya.Layout()
    layout.read(str(input_path))
    dbu = layout.dbu
    top = layout.top_cell()
    li_gap = layout.layer(pya.LayerInfo(*GAP_LAYER))
    li_jj = layout.layer(pya.LayerInfo(*JJ_LAYER))

    def um(v: float) -> int:
        return round(v / dbu)

    # 1) Complete the bottom-right transmon (its claw arc+leads already exist).
    br = ClawEnd(x_end=4604.0, cc_lo=-76.0, cc_hi=-41.0)
    gap, jj = build_transmon_left(br, dbu)
    top.shapes(li_gap).insert(gap)
    top.shapes(li_jj).insert(jj)

    # 2) Snapshot the completed bottom-right claw+qubit unit for replication.
    unit_gap, unit_jj = _unit_polygons(top, li_gap, li_jj, dbu)

    # 3) Reroute the other three: pull each meander back to create the qubit gap,
    #    then drop a transformed copy of the unit at its coupling end.
    for name, bbox_top, x_center, above in RESONATORS:
        dx = um(x_center - BR_X_CENTER)
        if above:
            # Pull up, and mirror the (below-feedline) unit about y = FEED_MID.
            meander_trans = pya.Trans(0, False, 0, um(+PULLBACK))
            unit_trans = pya.Trans(0, True, dx, um(2 * FEED_MID))
        else:
            meander_trans = pya.Trans(0, False, 0, um(-PULLBACK))
            unit_trans = pya.Trans(0, False, dx, 0)

        # Translate the two meander polygons for this resonator (identified by bbox top).
        for s in list(top.shapes(li_gap).each()):
            bb = s.bbox()
            poly = s.polygon or s.simple_polygon
            if poly is None or poly.num_points() < 100:
                continue
            if abs(bb.top * dbu - bbox_top) <= 0.2:
                top.shapes(li_gap).replace(s, poly.transformed(meander_trans))

        for poly in unit_gap:
            top.shapes(li_gap).insert(poly.transformed(unit_trans))
        for poly in unit_jj:
            top.shapes(li_jj).insert(poly.transformed(unit_trans))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output_path))
    print(f"Built 4 transmons (bottom-right template + 3 replicas); wrote {output_path}")


def main(argv: list[str] | None = None) -> int:
    base = Path.home() / "Desktop" / "Quantum Design"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=base / "QubitFinalCooperGroup_aligned.gds")
    parser.add_argument("--output", type=Path, default=base / "QubitFinalCooperGroup_qubits.gds")
    args = parser.parse_args(argv)
    build(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
