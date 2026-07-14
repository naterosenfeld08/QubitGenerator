"""Analytic centerline paths (straights + circular arcs).

Length is an invariant of the path:

    L = Σ s_i  +  Σ r_i · |θ_i|

and is never measured from GDS polygons.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, sin
from typing import Sequence

import numpy as np


Point2D = tuple[float, float]


@dataclass(frozen=True)
class StraightSegment:
    """Straight centerline segment between two points (µm)."""

    start_um: Point2D
    end_um: Point2D

    def length_um(self) -> float:
        """Return Euclidean length in micrometres."""
        dx = self.end_um[0] - self.start_um[0]
        dy = self.end_um[1] - self.start_um[1]
        return float((dx * dx + dy * dy) ** 0.5)

    def point_at(self, s_um: float) -> Point2D:
        """Return the point a distance ``s_um`` from the start."""
        length = self.length_um()
        if length == 0.0:
            return self.start_um
        t = s_um / length
        return (
            self.start_um[0] + t * (self.end_um[0] - self.start_um[0]),
            self.start_um[1] + t * (self.end_um[1] - self.start_um[1]),
        )


@dataclass(frozen=True)
class ArcSegment:
    """Circular arc centerline segment (µm, radians)."""

    center_um: Point2D
    radius_um: float
    theta_start_rad: float
    theta_end_rad: float

    def delta_theta_rad(self) -> float:
        """Signed turn angle in radians."""
        return self.theta_end_rad - self.theta_start_rad

    def length_um(self) -> float:
        """Return arc length ``r · |Δθ|`` in micrometres."""
        return abs(self.radius_um * self.delta_theta_rad())

    def point_at(self, s_um: float) -> Point2D:
        """Return the point a distance ``s_um`` along the arc from the start."""
        length = self.length_um()
        if length == 0.0:
            return (
                self.center_um[0] + self.radius_um * cos(self.theta_start_rad),
                self.center_um[1] + self.radius_um * sin(self.theta_start_rad),
            )
        sign = 1.0 if self.delta_theta_rad() >= 0.0 else -1.0
        theta = self.theta_start_rad + sign * (s_um / self.radius_um)
        return (
            self.center_um[0] + self.radius_um * cos(theta),
            self.center_um[1] + self.radius_um * sin(theta),
        )


Segment = StraightSegment | ArcSegment


@dataclass(frozen=True)
class Centerline:
    """Ordered sequence of straight and arc segments."""

    segments: tuple[Segment, ...]

    @classmethod
    def from_segments(cls, segments: Sequence[Segment]) -> Centerline:
        """Build a centerline from a sequence of segments."""
        return cls(segments=tuple(segments))

    def length_um(self) -> float:
        """Analytic total length in micrometres."""
        return float(sum(seg.length_um() for seg in self.segments))

    def point_at(self, s_um: float) -> Point2D:
        """Return the point a distance ``s_um`` along the path from the start."""
        remaining = s_um
        for seg in self.segments:
            seg_len = seg.length_um()
            if remaining <= seg_len or seg is self.segments[-1]:
                return seg.point_at(min(remaining, seg_len))
            remaining -= seg_len
        if not self.segments:
            raise ValueError("Empty centerline has no points")
        return self.segments[-1].point_at(self.segments[-1].length_um())

    def numeric_length_um(self, samples_per_um: float = 100.0) -> float:
        """Integrate the parametrized curve numerically (for tests).

        Parameters
        ----------
        samples_per_um :
            Samples per micrometre of analytic length (≥ 10 recommended).
        """
        total = 0.0
        for seg in self.segments:
            seg_len = seg.length_um()
            if seg_len == 0.0:
                continue
            n = max(2, int(np.ceil(seg_len * samples_per_um)) + 1)
            s_vals = np.linspace(0.0, seg_len, n)
            pts = np.array([seg.point_at(float(s)) for s in s_vals], dtype=float)
            diffs = np.diff(pts, axis=0)
            total += float(np.linalg.norm(diffs, axis=1).sum())
        return total

    def to_corner_points_um(self) -> list[Point2D]:
        """Approximate the path as corner points for ``WaveguideCoplanar``.

        Straights contribute their endpoints. Arcs are replaced by start,
        one mid-chord corner (compatible with KQC circular-bend extrusion
        only when the turn is a single circular corner between straights);
        for multi-sample arcs we densify for future Euler support tests.
        """
        if not self.segments:
            return []
        points: list[Point2D] = []
        for seg in self.segments:
            if isinstance(seg, StraightSegment):
                if not points:
                    points.append(seg.start_um)
                points.append(seg.end_um)
            else:
                start = seg.point_at(0.0)
                end = seg.point_at(seg.length_um())
                if not points:
                    points.append(start)
                # Use a single corner point approximation for circular bends:
                # KQC WaveguideCoplanar builds circular fillets between corners.
                # For a pure arc between known straights, the corner is the
                # intersection of the incoming/outgoing tangents. When we only
                # have the arc, densify moderately for length tests / extrusion.
                n = max(3, int(abs(seg.delta_theta_rad()) / (np.pi / 16)) + 1)
                for i in range(1, n):
                    s = seg.length_um() * i / n
                    points.append(seg.point_at(s))
                points.append(end)
        return _dedupe_points(points)


def _dedupe_points(points: list[Point2D], tol_um: float = 1e-9) -> list[Point2D]:
    if not points:
        return []
    out = [points[0]]
    for p in points[1:]:
        if abs(p[0] - out[-1][0]) > tol_um or abs(p[1] - out[-1][1]) > tol_um:
            out.append(p)
    return out


def corner_path_from_points(points_um: Sequence[Point2D], bend_radius_um: float) -> Centerline:
    """Build an analytic straights+arcs centerline from polyline corners.

    Parameters
    ----------
    points_um :
        Corner waypoints.
    bend_radius_um :
        Circular fillet radius inserted at each interior corner.
    """
    pts = list(points_um)
    if len(pts) < 2:
        raise ValueError("Need at least two points")
    if len(pts) == 2:
        return Centerline.from_segments([StraightSegment(pts[0], pts[1])])

    segments: list[Segment] = []
    # Accumulate cutback along vertices using tangent-half-angle fillet.
    # For each interior vertex i, replace sharp corner with circular arc of
    # radius r, cutting both adjacent edges by r*tan(|α|/2).
    from math import tan

    # Precompute unit directions of each edge
    edges = []
    for i in range(len(pts) - 1):
        dx = pts[i + 1][0] - pts[i][0]
        dy = pts[i + 1][1] - pts[i][1]
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0.0:
            raise ValueError("Zero-length edge in corner path")
        edges.append(((dx / length, dy / length), length))

    cursor = pts[0]
    for i in range(1, len(pts) - 1):
        v_in, len_in = edges[i - 1]
        v_out, len_out = edges[i]
        # Turn angle via atan2 cross/dot
        cross = v_in[0] * v_out[1] - v_in[1] * v_out[0]
        dot = v_in[0] * v_out[0] + v_in[1] * v_out[1]
        alpha = atan2(cross, dot)
        if abs(alpha) < 1e-15:
            # Colinear — skip arc
            continue
        cut = bend_radius_um * tan(abs(alpha) / 2.0)
        if cut > len_in - 1e-9 or cut > len_out - 1e-9:
            raise ValueError(
                f"Bend radius {bend_radius_um} too large for corner at index {i}"
            )
        corner = pts[i]
        arc_start = (corner[0] - v_in[0] * cut, corner[1] - v_in[1] * cut)
        arc_end = (corner[0] + v_out[0] * cut, corner[1] + v_out[1] * cut)
        if (arc_start[0] - cursor[0]) ** 2 + (arc_start[1] - cursor[1]) ** 2 > 1e-18:
            segments.append(StraightSegment(cursor, arc_start))
        # Arc center = corner - sign * r * unit(bisector of normals)...
        # Center is offset from corner along (v_in_perp blended): for circular
        # fillet, center = arc_start + r * rot90(v_in) with correct sign.
        # Rotate v_in by +90° for left turns (alpha>0), -90° for right.
        if alpha > 0:
            n = (-v_in[1], v_in[0])
        else:
            n = (v_in[1], -v_in[0])
        center = (
            arc_start[0] + n[0] * bend_radius_um,
            arc_start[1] + n[1] * bend_radius_um,
        )
        theta0 = atan2(arc_start[1] - center[1], arc_start[0] - center[0])
        theta1 = atan2(arc_end[1] - center[1], arc_end[0] - center[0])
        # Unwrap theta1 to follow alpha sign
        if alpha > 0 and theta1 < theta0:
            theta1 += 2.0 * np.pi
        elif alpha < 0 and theta1 > theta0:
            theta1 -= 2.0 * np.pi
        segments.append(
            ArcSegment(
                center_um=center,
                radius_um=bend_radius_um,
                theta_start_rad=theta0,
                theta_end_rad=theta1,
            )
        )
        cursor = arc_end
    # Final straight to last point
    if (pts[-1][0] - cursor[0]) ** 2 + (pts[-1][1] - cursor[1]) ** 2 > 1e-18:
        segments.append(StraightSegment(cursor, pts[-1]))
    return Centerline.from_segments(segments)
