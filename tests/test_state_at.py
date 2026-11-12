import math

import pytest

from profiler.trajectory import TrajectoryPoint, state_at


def tp(x, y, theta, v, t):
    return TrajectoryPoint(x, y, theta, v, 0.0, 0.0, t)


def test_state_at_interpolates_and_clamps():
    traj = [tp(0, 0, 0, 0, 0), tp(10, 0, 0, 20, 1), tp(10, 10, math.pi / 2, 0, 2)]
    assert state_at(traj, -1) == (0, 0, 0, 0)
    assert state_at(traj, 0.5) == pytest.approx((5, 0, 0, 10))
    assert state_at(traj, 1.5) == pytest.approx((10, 5, math.pi / 4, 10))
    assert state_at(traj, 9) == (10, 10, math.pi / 2, 0)


def test_state_at_wraps_heading_the_short_way():
    traj = [tp(0, 0, math.radians(170), 1, 0), tp(1, 0, math.radians(-170), 1, 1)]
    theta = state_at(traj, 0.5)[2]
    assert math.cos(theta) == pytest.approx(-1, abs=1e-9)  # passes through 180, not 0
