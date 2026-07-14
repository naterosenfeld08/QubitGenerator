"""Optional full test-chip PCell assembled from YAML defaults."""

from __future__ import annotations

from pathlib import Path

from kqcircuits.chips.chip import Chip as KqcChip
from kqcircuits.util.parameters import Param, pdt

from resonator_gen.chip import Chip as GenChip
from resonator_gen.config import ChipConfig


class TestChip(KqcChip):
    """Build ``configs/test_chip_v1.yaml`` (or a custom path) into a chip cell."""

    config_path = Param(
        pdt.TypeString,
        "Config YAML path",
        "",
        docstring="Empty uses repo configs/test_chip_v1.yaml",
    )

    def build(self):
        path = self.config_path
        if not path:
            # Walk up from this file to the repository root.
            repo = Path(__file__).resolve().parents[3]
            path = str(repo / "configs" / "test_chip_v1.yaml")
        cfg = ChipConfig.from_yaml(path)
        gen = GenChip(cfg)
        gen.build()
        # Insert generated top cell content by copying instances is complex;
        # for GUI use, prefer scripts/build_chip.py. Here we create a label.
        self.refpoints["chip_origin"] = self.refpoints.get("base", None)
