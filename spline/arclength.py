import math

import numpy as np

from spline.hermite import cubic_hermite_2d, hermite_eval_2d

EPS = 1e-9


def _split(u, num_segments):
    seg = min(int(u), num_segments - 1)
    return seg, u - seg


def sample_path_by_distance(waypoints, tangents, spacing, oversample=200):
    """Sample the spline at equal arc-length spacing.

    Returns a list of (position, d1, d2) tuples. Uniform spacing keeps the
    curvature and velocity profile independent of tangent magnitudes and
    segment lengths, which uniform-in-t sampling does not.
    """
    num_segments = len(waypoints) - 1
    if num_segments < 1:
        raise ValueError("need at least two waypoints")
    if spacing <= 0:
        raise ValueError("spacing must be positive")

    def seg_args(u):
        seg, t = _split(u, num_segments)
        return waypoints[seg], waypoints[seg + 1], tangents[seg], tangents[seg + 1], t

    # Dense table: global parameter u in [0, num_segments] -> cumulative arc length.
    us = np.linspace(0, num_segments, num_segments * oversample + 1)
    pts = np.array([cubic_hermite_2d(*seg_args(u)) for u in us])
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    total = cum[-1]

    n = max(1, math.ceil(total / spacing))
    target_us = np.interp(np.linspace(0, total, n + 1), cum, us)

    return [hermite_eval_2d(*seg_args(u)) for u in target_us]


def signed_curvature(d1, d2):
    """Signed curvature of a parametric curve (positive = turning left / CCW)."""
    speed_sq = d1[0] ** 2 + d1[1] ** 2
    if speed_sq < EPS:
        return 0.0
    return (d1[0] * d2[1] - d1[1] * d2[0]) / speed_sq ** 1.5
