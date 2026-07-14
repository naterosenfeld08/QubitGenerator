"""Meander resonator hits target body length within 1 nm."""

from __future__ import annotations

import random

import pytest

from resonator_gen.calibration import Calibration
from resonator_gen.config import CouplerSpec, CpwConfig, PlacementSpec, ResonatorSpec
from resonator_gen.constants import LENGTH_TOL_UM
from resonator_gen.resonators.meander import MeanderResonator


@pytest.fixture(scope="module")
def layout():
    from kqcircuits.pya_resolver import pya

    return pya.Layout()


def _make_spec(
    *,
    frequency_hz: float,
    radius_um: float,
    pitch_um: float,
    span_um: float,
    name: str = "R",
) -> ResonatorSpec:
    return ResonatorSpec(
        name=name,
        frequency_hz=frequency_hz,
        mode="quarter",
        geometry="meander",
        termination="short",
        bend_radius_um=radius_um,
        pitch_um=pitch_um,
        meanders=-1,
        coupler=CouplerSpec(),
        placement=PlacementSpec(x_um=0.0, y_um=0.0, orientation_deg=0.0, meander_span_um=span_um),
    )


def test_meander_length_single(layout) -> None:
    cal = Calibration(eps_eff=6.35)
    cpw = CpwConfig(width_um=10.0, gap_um=6.0, bend_radius_um=100.0, pitch_um=100.0)
    spec = _make_spec(frequency_hz=5.0e9, radius_um=100.0, pitch_um=100.0, span_um=1200.0)
    result = MeanderResonator(spec).build_standalone(layout, cal, cpw)
    assert abs(result.actual_length_um - result.body_length_um) <= LENGTH_TOL_UM


def test_meander_length_random_ensemble(layout) -> None:
    rng = random.Random(123)
    cal = Calibration(eps_eff=6.35)
    cpw = CpwConfig(width_um=10.0, gap_um=6.0, bend_radius_um=100.0, pitch_um=100.0)
    failures = []
    for i in range(100):
        frequency_hz = rng.uniform(4.0e9, 6.0e9)
        radius_um = rng.uniform(80.0, 150.0)
        pitch_um = max(100.0, 2.0 * radius_um)
        # Ensure span >= 4r and body length will exceed span for these freqs.
        span_um = max(4.0 * radius_um + 50.0, rng.uniform(900.0, 1800.0))
        body = cal.body_length_um(frequency_hz)
        if body < span_um:
            span_um = max(4.0 * radius_um + 10.0, body * 0.5)
        if body < span_um:
            continue
        spec = _make_spec(
            frequency_hz=frequency_hz,
            radius_um=radius_um,
            pitch_um=pitch_um,
            span_um=span_um,
            name=f"R{i}",
        )
        try:
            result = MeanderResonator(spec).build_standalone(layout, cal, cpw)
        except Exception as exc:  # pragma: no cover - collect
            failures.append((i, "build", str(exc)))
            continue
        if abs(result.actual_length_um - result.body_length_um) > LENGTH_TOL_UM:
            failures.append(
                (
                    i,
                    "length",
                    f"actual={result.actual_length_um} body={result.body_length_um}",
                )
            )
    assert not failures, f"{len(failures)} failures, first={failures[0]}"
