"""Calibration round-trip and basic physics tests."""

from __future__ import annotations

import pytest

from resonator_gen.calibration import Calibration
from resonator_gen.constants import FREQUENCY_ROUNDTRIP_REL_TOL


@pytest.mark.parametrize(
    ("frequency_hz", "expected_mm"),
    [
        (4.0e9, 7.44),
        (4.5e9, 6.61),
        (5.0e9, 5.95),
        (5.5e9, 5.41),
    ],
)
def test_nominal_quarter_wave_table(frequency_hz: float, expected_mm: float) -> None:
    cal = Calibration(eps_eff=6.35)
    length_mm = cal.target_length_um(frequency_hz, mode="quarter") / 1000.0
    assert length_mm == pytest.approx(expected_mm, abs=0.02)


def test_frequency_length_roundtrip() -> None:
    cal = Calibration(eps_eff=6.35, coupler_dL_um=0.0)
    for frequency_hz in [4.0e9, 4.7e9, 5.5e9, 6.2e9]:
        length_um = cal.target_length_um(frequency_hz, mode="quarter")
        f_back = cal.frequency_hz_from_length(length_um, mode="quarter")
        assert abs(f_back - frequency_hz) / frequency_hz <= FREQUENCY_ROUNDTRIP_REL_TOL


def test_half_wave_is_double_quarter() -> None:
    cal = Calibration(eps_eff=6.35)
    f = 5.0e9
    assert cal.target_length_um(f, mode="half") == pytest.approx(
        2.0 * cal.target_length_um(f, mode="quarter")
    )


def test_kinetic_inductance_override() -> None:
    cal = Calibration(eps_eff=6.35, kinetic_inductance_override_v_phi_m_s=1.0e8)
    assert cal.phase_velocity_m_s() == 1.0e8


def test_body_length_subtracts_coupler_dl() -> None:
    cal = Calibration(eps_eff=6.35, coupler_dL_um=100.0)
    target = cal.target_length_um(5.0e9)
    body = cal.body_length_um(5.0e9)
    assert body == pytest.approx(target - 100.0)
