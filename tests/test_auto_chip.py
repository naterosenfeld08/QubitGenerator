"""End-to-end auto-placement chip tests: regression, failure path, determinism."""

from __future__ import annotations

from pathlib import Path

import pytest

from resonator_gen.chip import Chip
from resonator_gen.config import ChipConfig
from resonator_gen.constants import AUTO_LENGTH_TOL_UM
from resonator_gen.routing import PlacementInfeasibleError


@pytest.fixture
def auto_yaml(repo_root: Path) -> Path:
    return repo_root / "configs" / "test_chip_v1_auto.yaml"


def _pairwise_separation_violations(chip: Chip, clearance_um: float) -> int:
    """Count separation violations between distinct resonator cells."""
    from kqcircuits.pya_resolver import pya

    from resonator_gen.constants import GAP_LAYER
    from resonator_gen.keepouts import cell_region

    cells = [r.cell_instance for r in chip.report()]
    dist_dbu = int(round(clearance_um / 0.001))
    violations = 0
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            ra = cell_region(cells[i], GAP_LAYER)
            rb = cell_region(cells[j], GAP_LAYER)
            violations += ra.separation_check(rb, dist_dbu).count()
    _ = pya
    return violations


def test_auto_chip_builds_and_hits_lengths(auto_yaml: Path) -> None:
    cfg = ChipConfig.from_yaml(auto_yaml)
    chip = Chip(cfg)
    chip.build()
    results = chip.report()
    assert len(results) == 4
    for row in results:
        # AUTO tolerance: solved (non-round) spans add annotation-grid
        # quantization to the measured length; the analytic solve is exact.
        assert abs(row.actual_length_um - row.body_length_um) <= AUTO_LENGTH_TOL_UM, row.name


def test_auto_chip_respects_clearance(auto_yaml: Path) -> None:
    cfg = ChipConfig.from_yaml(auto_yaml)
    chip = Chip(cfg)
    chip.build()
    # Default clearance: pitch_ratio_min * (w + 2g) = 3 * 22 = 66 µm.
    assert _pairwise_separation_violations(chip, 66.0) == 0


def test_auto_chip_determinism(auto_yaml: Path, tmp_path: Path) -> None:
    from tests.test_chip_build import _gds_content_digest

    cfg = ChipConfig.from_yaml(auto_yaml)
    paths = []
    for i in range(2):
        chip = Chip(cfg)
        chip.build()
        path = tmp_path / f"auto_{i}.gds"
        chip.write_gds(path)
        paths.append(path)
    assert _gds_content_digest(paths[0]) == _gds_content_digest(paths[1])


def test_auto_overcrowded_raises(auto_yaml: Path) -> None:
    cfg = ChipConfig.from_yaml(auto_yaml)
    # Shrink the die so nothing fits above the feedline.
    data = cfg.model_dump()
    data["die"] = {
        "width_um": 9500.0,
        "height_um": 700.0,
        "origin_um": [-500.0, -300.0],
        "edge_margin_um": 100.0,
    }
    small = ChipConfig.model_validate(data)
    chip = Chip(small)
    with pytest.raises(PlacementInfeasibleError) as excinfo:
        chip.build()
    err = excinfo.value
    assert err.target_length_um > 0.0
    assert err.clearance_um > 0.0
    assert len(err.geometries_tried) >= 1


def test_auto_requires_die() -> None:
    with pytest.raises(ValueError, match="die"):
        ChipConfig.model_validate(
            {
                "name": "no_die",
                "feedline": {"path_um": [[0, 0], [1000, 0]]},
                "resonators": [
                    {
                        "name": "R0",
                        "frequency_hz": 5.0e9,
                        "placement": {"mode": "auto", "x_um": 500, "y_um": 0},
                    }
                ],
            }
        )
