"""Constraint soft/hard enforcement tests."""

from __future__ import annotations

import logging

import pytest

from resonator_gen.constraints import ConstraintError, check_bend_radius, check_pitch


def test_radius_ok() -> None:
    # footprint = 10 + 12 = 22; 3*22 = 66; r=100 ok
    result = check_bend_radius(100.0, 10.0, 6.0, hard_fail=True)
    assert result.ok


def test_radius_hard_fail() -> None:
    with pytest.raises(ConstraintError):
        check_bend_radius(10.0, 10.0, 6.0, hard_fail=True)


def test_radius_soft_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        result = check_bend_radius(10.0, 10.0, 6.0, hard_fail=False)
    assert not result.ok
    assert any("bend_radius_um" in rec.message for rec in caplog.records)


def test_pitch_hard_fail() -> None:
    with pytest.raises(ConstraintError):
        check_pitch(10.0, 10.0, 6.0, hard_fail=True)


def test_pitch_ok() -> None:
    result = check_pitch(100.0, 10.0, 6.0, hard_fail=True)
    assert result.ok
