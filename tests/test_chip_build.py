"""Chip YAML → GDS build and determinism tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from resonator_gen.chip import Chip
from resonator_gen.config import ChipConfig
from resonator_gen.constants import LENGTH_TOL_UM


def _gds_content_digest(path: Path) -> str:
    """Hash GDS bytes after zeroing the optional libname timestamp region heuristically.

    KLayout may embed timestamps; for robust comparison we hash the structure
    by reloading and rewriting with a fixed libname.
    """
    from kqcircuits.pya_resolver import pya

    layout = pya.Layout()
    layout.read(str(path))
    # Normalize libname to strip variable metadata when possible.
    try:
        layout.rename_cell(layout.top_cell().cell_index(), "TOP")
    except Exception:
        pass
    tmp = path.with_suffix(".norm.gds")
    layout.write(str(tmp))
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    tmp.unlink(missing_ok=True)
    return digest


def test_chip_config_loads(test_chip_yaml: Path) -> None:
    cfg = ChipConfig.from_yaml(test_chip_yaml)
    assert cfg.name == "test_chip_v1"
    assert len(cfg.resonators) == 4


def test_chip_build_report(test_chip_yaml: Path, tmp_path: Path) -> None:
    cfg = ChipConfig.from_yaml(test_chip_yaml)
    chip = Chip(cfg)
    chip.build()
    results = chip.report()
    assert len(results) == 4
    for row in results:
        assert abs(row.actual_length_um - row.body_length_um) <= LENGTH_TOL_UM
    out = tmp_path / "chip.gds"
    chip.write_gds(out)
    assert out.stat().st_size > 0


def test_gds_regeneration_determinism(test_chip_yaml: Path, tmp_path: Path) -> None:
    cfg = ChipConfig.from_yaml(test_chip_yaml)
    paths = []
    for i in range(2):
        chip = Chip(cfg)
        chip.build()
        path = tmp_path / f"chip_{i}.gds"
        chip.write_gds(path)
        paths.append(path)
    assert _gds_content_digest(paths[0]) == _gds_content_digest(paths[1])


def test_spiral_smoke() -> None:
    from kqcircuits.pya_resolver import pya

    from resonator_gen.calibration import Calibration
    from resonator_gen.config import CouplerSpec, CpwConfig, PlacementSpec, ResonatorSpec
    from resonator_gen.resonators.spiral import SpiralResonator

    layout = pya.Layout()
    cal = Calibration(eps_eff=6.35)
    cpw = CpwConfig()
    spec = ResonatorSpec(
        name="S0",
        frequency_hz=5.0e9,
        geometry="spiral",
        coupler=CouplerSpec(),
        placement=PlacementSpec(x_um=0, y_um=0, orientation_deg=0, meander_span_um=1200),
    )
    result = SpiralResonator(spec).build_standalone(layout, cal, cpw)
    assert abs(result.actual_length_um - result.body_length_um) <= 1.0  # spiral tol looser smoke
