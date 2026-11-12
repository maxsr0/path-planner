import math
from typing import NamedTuple, Tuple

import numpy as np

from spline.hermite import cubic_hermite_2d, hermite_eval_2d

EPS = 1e-9


class Sample(NamedTuple):
    pos: Tuple[float, float]
    d1: Tuple[float, float]   # path derivative (direction of travel along the path)
    d2: Tuple[float, float]
    seg: int                  # index of the segment this sample belongs to


def segment_args(waypoints, tangents, i, signs=None):
    """Hermite (p0, p1, m0, m1) for segment i.

    tangents are robot *headings*; a reversed segment (sign -1) is traversed
    against them, so its path derivatives are the negated headings.
    """
    s = signs[i] if signs is not None else 1
    m0 = (s * tangents[i][0], s * tangents[i][1])
    m1 = (s * tangents[i + 1][0], s * tangents[i + 1][1])
    return waypoints[i], waypoints[i + 1], m0, m1


def sample_path_by_distance(waypoints, tangents, spacing, oversample=200, signs=None):
    """Sample each segment at equal arc-length spacing; waypoints are always sample points.

    Returns a list of Sample. A waypoint between segments i and i+1 appears once,
    as the first sample of segment i+1 (its derivatives come from that segment).
    """
    num_segments = len(waypoints) - 1
    if num_segments < 1:
        raise ValueError("need at least two waypoints")
    if spacing <= 0:
        raise ValueError("spacing must be positive")

    samples = []
    ts = np.linspace(0, 1, oversample + 1)
    for i in range(num_segments):
        args = segment_args(waypoints, tangents, i, signs)
        pts = np.array([cubic_hermite_2d(*args, t) for t in ts])
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        n = max(1, math.ceil(cum[-1] / spacing))
        targets = np.interp(np.linspace(0, cum[-1], n + 1), cum, ts)
        if i < num_segments - 1:
            targets = targets[:-1]  # the end point is the next segment's first sample
        for t in targets:
            pos, d1, d2 = hermite_eval_2d(*args, t)
            samples.append(Sample(pos, d1, d2, i))
    return samples


def signed_curvature(d1, d2):
    """Signed curvature of a parametric curve (positive = turning left / CCW)."""
    speed_sq = d1[0] ** 2 + d1[1] ** 2
    if speed_sq < EPS:
        return 0.0
    return (d1[0] * d2[1] - d1[1] * d2[0]) / speed_sq ** 1.5
