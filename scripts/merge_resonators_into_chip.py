#!/usr/bin/env python3
"""Merge generated resonators into an existing chip GDS.

Copies cells ``R0``…``R3`` from a resonator-gen GDS into a base chip,
remaps KQCircuits fab layers onto the base chip's layer numbers, and applies
a placement offset so you can drop them next to your feedline.

Example
-------
    python scripts/merge_resonators_into_chip.py \\
        --base ~/Documents/Qubit\\(Correct\\).gds \\
        --resonators out/test_chip_v1.gds \\
        --output out/Qubit_with_resonators.gds \\
        --dx 0 --dy 0 \\
        --gap-layer 1/0
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from kqcircuits.pya_resolver import pya

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("merge_resonators")

# KQCircuits layers produced by resonator_gen (face 1t1).
KQC_GAP = (130, 1)  # base_metal_gap_wo_grid — fab geometry
KQC_AVOID = (133, 1)  # ground_grid_avoidance — optional
KQC_PATH = (135, 1)  # waveguide_path — annotation
KQC_PORTS = (154, 1)  # ports — annotation
KQC_REFS = (225, 0)  # refpoints — annotation


def parse_layer(text: str) -> tuple[int, int]:
    """Parse ``'layer/datatype'`` (e.g. ``'1/0'``)."""
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not match:
        raise argparse.ArgumentTypeError(f"Expected LAYER/DATATYPE like 1/0, got {text!r}")
    return int(match.group(1)), int(match.group(2))


def layer_index(layout: pya.Layout, layer_dt: tuple[int, int]) -> int:
    """Return (or create) a layer index for ``(layer, datatype)``."""
    return layout.layer(pya.LayerInfo(layer_dt[0], layer_dt[1]))


def copy_region_transformed(
    src_cell: pya.Cell,
    src_layer: int,
    dst_cell: pya.Cell,
    dst_layer: int,
    trans: pya.DCplxTrans,
) -> int:
    """Flatten ``src_cell`` shapes on ``src_layer`` into ``dst_cell`` with ``trans``.

    Returns
    -------
    int
        Number of polygons inserted.
    """
    region = pya.Region(src_cell.begin_shapes_rec(src_layer))
    if region.is_empty():
        return 0
    # Region uses integer database units of the source layout.
    dbu_src = src_cell.layout().dbu
    dbu_dst = dst_cell.layout().dbu
    if abs(dbu_src - dbu_dst) > 1e-15:
        # Scale integer coords if database units differ.
        scale = dbu_src / dbu_dst
        region = region.transformed(pya.VCplxTrans(scale, 0, False, 0, 0))
    # Apply micron-space placement in destination dbu.
    ix = round(trans.disp.x / dbu_dst)
    iy = round(trans.disp.y / dbu_dst)
    angle_deg = trans.angle
    mirror = trans.is_mirror()
    it = pya.ICplxTrans(1.0, angle_deg, mirror, ix, iy)
    region = region.transformed(it)
    dst_cell.shapes(dst_layer).insert(region)
    return region.count()


def merge(
    base_path: Path,
    resonators_path: Path,
    output_path: Path,
    *,
    resonators: list[str],
    dx_um: float,
    dy_um: float,
    gap_layer: tuple[int, int],
    include_avoidance: bool,
    include_annotations: bool,
) -> None:
    """Copy resonator fab geometry into the base chip and write ``output_path``."""
    base = pya.Layout()
    base.read(str(base_path))
    src = pya.Layout()
    src.read(str(resonators_path))

    if abs(base.dbu - src.dbu) > 1e-12:
        logger.warning(
            "Database units differ (base=%.6g, resonators=%.6g); scaling applied",
            base.dbu,
            src.dbu,
        )

    top = base.top_cell()
    if top is None:
        raise RuntimeError(f"No top cell in {base_path}")

    dst_gap = layer_index(base, gap_layer)
    dst_avoid = layer_index(base, gap_layer)  # unused unless include_avoidance with separate layer
    src_gap = layer_index(src, KQC_GAP)
    src_avoid = layer_index(src, KQC_AVOID)

    placement = pya.DCplxTrans(1.0, 0.0, False, pya.DVector(dx_um, dy_um))
    total_polys = 0

    for name in resonators:
        cell = src.cell(name)
        if cell is None:
            raise RuntimeError(f"Cell {name!r} not found in {resonators_path}")
        n = copy_region_transformed(cell, src_gap, top, dst_gap, placement)
        total_polys += n
        logger.info(
            "%s: copied %d gap polygons → %d/%d at offset (%.3f, %.3f) µm",
            name,
            n,
            gap_layer[0],
            gap_layer[1],
            dx_um,
            dy_um,
        )
        if include_avoidance:
            n_av = copy_region_transformed(cell, src_avoid, top, dst_avoid, placement)
            logger.info("%s: copied %d avoidance polygons onto same target layer", name, n_av)
            total_polys += n_av
        if include_annotations:
            for ld in (KQC_PATH, KQC_PORTS, KQC_REFS):
                src_l = layer_index(src, ld)
                dst_l = layer_index(base, ld)
                n_ann = copy_region_transformed(cell, src_l, top, dst_l, placement)
                if n_ann:
                    logger.info("%s: copied %d shapes from %d/%d (annotation)", name, n_ann, ld[0], ld[1])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    base.write(str(output_path))
    logger.info(
        "Wrote %s (%d polygons inserted into top cell %r)",
        output_path,
        total_polys,
        top.name,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy resonator_gen R* cells into an existing chip GDS with layer remap."
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=Path.home() / "Documents" / "Qubit(Correct).gds",
        help="Existing chip GDS (default: ~/Documents/Qubit(Correct).gds)",
    )
    parser.add_argument(
        "--resonators",
        type=Path,
        default=Path("out/test_chip_v1.gds"),
        help="GDS produced by scripts/build_chip.py (default: out/test_chip_v1.gds)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("out/Qubit_with_resonators.gds"),
        help="Output path (never overwrites --base unless you set it explicitly)",
    )
    parser.add_argument(
        "--cells",
        nargs="+",
        default=["R0", "R1", "R2", "R3"],
        help="Resonator cell names to copy (default: R0 R1 R2 R3)",
    )
    parser.add_argument("--dx", type=float, default=0.0, help="X offset in µm applied to all resonators")
    parser.add_argument("--dy", type=float, default=0.0, help="Y offset in µm applied to all resonators")
    parser.add_argument(
        "--gap-layer",
        type=parse_layer,
        default=(1, 0),
        help="Destination layer for KQC gap geometry (default: 1/0). Try 1/1 if that is your CPW layer.",
    )
    parser.add_argument(
        "--include-avoidance",
        action="store_true",
        help="Also copy ground-grid avoidance shapes onto the gap layer",
    )
    parser.add_argument(
        "--include-annotations",
        action="store_true",
        help="Also copy path/port/refpoint annotation layers (usually not needed)",
    )
    args = parser.parse_args(argv)

    if not args.base.is_file():
        logger.error("Base GDS not found: %s", args.base)
        return 1
    if not args.resonators.is_file():
        logger.error("Resonator GDS not found: %s (run scripts/build_chip.py first)", args.resonators)
        return 1
    if args.output.resolve() == args.base.resolve():
        logger.error("Refusing to overwrite the base chip in place; choose a different --output")
        return 1

    merge(
        args.base,
        args.resonators,
        args.output,
        resonators=list(args.cells),
        dx_um=args.dx,
        dy_um=args.dy,
        gap_layer=args.gap_layer,
        include_avoidance=args.include_avoidance,
        include_annotations=args.include_annotations,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
