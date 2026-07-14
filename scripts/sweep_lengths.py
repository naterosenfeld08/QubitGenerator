#!/usr/bin/env python3
"""Print frequency → length verification sweep."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resonator_gen.cli import sweep_lengths_main

if __name__ == "__main__":
    raise SystemExit(sweep_lengths_main())
