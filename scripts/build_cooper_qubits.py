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


def build(input_path: Path, output_path: Path) -> None:
    layout = pya.Layout()
    layout.read(str(input_path))
    dbu = layout.dbu
    top = layout.top_cell()
    li_gap = layout.layer(pya.LayerInfo(*GAP_LAYER))
    li_jj = layout.layer(pya.LayerInfo(*JJ_LAYER))

    # Bottom-right claw: center conductor y in [-76, -41], open end faces -x at x=4604.
    br = ClawEnd(x_end=4604.0, cc_lo=-76.0, cc_hi=-41.0)
    gap, jj = build_transmon_left(br, dbu)

    top.shapes(li_gap).insert(gap)
    top.shapes(li_jj).insert(jj)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(output_path))
    print(f"Added bottom-right transmon; wrote {output_path}")


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
