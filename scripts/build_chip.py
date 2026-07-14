#!/usr/bin/env python3
"""Build a chip GDS from a YAML config."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resonator_gen.cli import build_chip_main

if __name__ == "__main__":
    raise SystemExit(build_chip_main())
