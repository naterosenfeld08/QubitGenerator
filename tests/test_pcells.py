"""GUI PCell registration and auto-mode smoke tests."""

from __future__ import annotations

import pytest

from resonator_gen.pcells import register_gui_pcells


@pytest.fixture(scope="module")
def pcells():
    register_gui_pcells()
    import sys

    from resonator_gen.pcells import user_package_path

    pkg_parent = str(user_package_path().parent)
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)
    from resonator_gen_kqc.elements.readout_resonator import ReadoutResonator

    return ReadoutResonator


def test_pcell_manual_mode(pcells) -> None:
    from kqcircuits.pya_resolver import pya

    layout = pya.Layout()
    cell = pcells.create(layout, frequency_ghz=5.0, placement_mode="manual")
    assert cell is not None
    assert cell.length() > 0


def test_pcell_auto_mode_solves_span(pcells) -> None:
    from kqcircuits.pya_resolver import pya

    layout = pya.Layout()
    cell = pcells.create(
        layout,
        frequency_ghz=5.0,
        placement_mode="auto",
        available_length=3000,
        available_width=2500,
    )
    assert cell is not None
    # Realized length equals the calibrated λ/4 body length (5948.45 µm at
    # 5 GHz with eps_eff 6.35), within annotation quantization.
    assert cell.length() == pytest.approx(5948.45, abs=0.05)


def test_pcell_registration_idempotent(pcells) -> None:
    register_gui_pcells()
    register_gui_pcells()
