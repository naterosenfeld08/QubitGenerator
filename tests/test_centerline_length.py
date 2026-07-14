"""Analytic vs numeric centerline length tests."""

from __future__ import annotations

import math
import random

import pytest

from resonator_gen.centerline import (
    ArcSegment,
    Centerline,
    StraightSegment,
    corner_path_from_points,
)


def test_straight_length() -> None:
    seg = StraightSegment((0.0, 0.0), (3.0, 4.0))
    assert seg.length_um() == pytest.approx(5.0)


def test_arc_length() -> None:
    arc = ArcSegment(center_um=(0.0, 0.0), radius_um=100.0, theta_start_rad=0.0, theta_end_rad=math.pi / 2)
    assert arc.length_um() == pytest.approx(100.0 * math.pi / 2)


def test_centerline_sum() -> None:
    path = Centerline.from_segments(
        [
            StraightSegment((0.0, 0.0), (100.0, 0.0)),
            ArcSegment((100.0, 100.0), 100.0, -math.pi / 2, 0.0),
            StraightSegment((200.0, 100.0), (200.0, 200.0)),
        ]
    )
    assert path.length_um() == pytest.approx(100.0 + 100.0 * math.pi / 2 + 100.0)


def test_analytic_vs_numeric_random_ensemble() -> None:
    rng = random.Random(42)
    for _ in range(30):
        segments: list = []
        x = y = 0.0
        for _step in range(rng.randint(2, 6)):
            if rng.random() < 0.5:
                dx = rng.uniform(10.0, 200.0)
                dy = rng.uniform(-50.0, 50.0)
                segments.append(StraightSegment((x, y), (x + dx, y + dy)))
                x, y = x + dx, y + dy
            else:
                r = rng.uniform(50.0, 150.0)
                dtheta = rng.choice([-1.0, 1.0]) * rng.uniform(math.pi / 6, math.pi / 2)
                theta0 = rng.uniform(0.0, 2.0 * math.pi)
                # Place center so arc starts at (x,y)
                cx = x - r * math.cos(theta0)
                cy = y - r * math.sin(theta0)
                arc = ArcSegment((cx, cy), r, theta0, theta0 + dtheta)
                segments.append(arc)
                x, y = arc.point_at(arc.length_um())
        path = Centerline.from_segments(segments)
        analytic = path.length_um()
        numeric = path.numeric_length_um(samples_per_um=200.0)
        assert abs(analytic - numeric) <= 1e-9 * max(1.0, analytic) + 1e-6


def test_corner_path_right_angle() -> None:
    path = corner_path_from_points([(0.0, 0.0), (200.0, 0.0), (200.0, 200.0)], bend_radius_um=50.0)
    # Two straights of 150 each + quarter arc 50*pi/2
    expected = 150.0 + 150.0 + 50.0 * math.pi / 2
    assert path.length_um() == pytest.approx(expected, rel=1e-9)
    assert abs(path.length_um() - path.numeric_length_um(500.0)) < 1e-6
