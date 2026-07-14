"""Command-line entry points."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from resonator_gen.calibration import Calibration
from resonator_gen.chip import Chip
from resonator_gen.config import ChipConfig
from resonator_gen.constants import DEFAULT_EPS_EFF
from resonator_gen.logging_config import get_logger

logger = get_logger(__name__)


def build_chip_main(argv: list[str] | None = None) -> int:
    """CLI: YAML config → GDS."""
    parser = argparse.ArgumentParser(description="Build a resonator test chip from YAML")
    parser.add_argument("config", type=Path, help="Path to chip YAML")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output GDS path (default: out/<chip_name>.gds)",
    )
    args = parser.parse_args(argv)
    cfg = ChipConfig.from_yaml(args.config)
    out = args.output or Path("out") / f"{cfg.name}.gds"
    chip = Chip(cfg)
    chip.build()
    chip.write_gds(out)
    for row in chip.report():
        logger.info(
            "OK %s: body %.3f µm (target electrical %.3f µm)",
            row.name,
            row.body_length_um,
            row.target_length_um,
        )
    return 0


def sweep_lengths_main(argv: list[str] | None = None) -> int:
    """CLI: print frequency → length table for a given eps_eff."""
    parser = argparse.ArgumentParser(description="Sweep frequency → λ/4 length")
    parser.add_argument("--eps-eff", type=float, default=DEFAULT_EPS_EFF)
    parser.add_argument(
        "--frequencies-ghz",
        type=float,
        nargs="+",
        default=[4.0, 4.5, 5.0, 5.5],
    )
    parser.add_argument("--mode", choices=["quarter", "half"], default="quarter")
    args = parser.parse_args(argv)
    cal = Calibration(eps_eff=args.eps_eff)
    for f_ghz in args.frequencies_ghz:
        f_hz = f_ghz * 1e9
        length_um = cal.target_length_um(f_hz, mode=args.mode)
        logger.info(
            "%.2f GHz → %.3f mm (eps_eff=%.4f, mode=%s)",
            f_ghz,
            length_um / 1000.0,
            args.eps_eff,
            args.mode,
        )
    return 0


if __name__ == "__main__":
    sys.exit(build_chip_main())
