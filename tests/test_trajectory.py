import math

import pytest

from profiler.config import RobotConfig
from profiler.trajectory import generate_trajectory
from profiler.velocity_profiler import velocity_ceiling
from spline.arclength import sample_path_by_distance, signed_curvature

WAYPOINTS = [(0, 0), (1, 2), (6, 7), (9, 9)]
TANGENTS = [(0, 1), (1, 0), (1, 1), (0, 1)]


def test_generate_trajectory_endpoints():
    traj = generate_trajectory(WAYPOINTS, TANGENTS)
    assert traj[0].velocity == pytest.approx(0)
    assert traj[0].timestamp == pytest.approx(0)
    assert traj[-1].velocity == pytest.approx(0)
    assert (traj[0].x, traj[0].y) == pytest.approx(WAYPOINTS[0])
    assert (traj[-1].x, traj[-1].y) == pytest.approx(WAYPOINTS[-1])
    assert all(b.timestamp > a.timestamp for a, b in zip(traj, traj[1:]))


def test_uniform_arc_length_spacing():
    # Very different tangent magnitudes per segment would bunch up uniform-in-t samples.
    # (tangents chosen so x(t) is monotonic, i.e. the curve never doubles back)
    samples = sample_path_by_distance([(0, 0), (10, 0), (12, 0)], [(20, 0), (4, 0), (2, 0)], 0.5)
    gaps = [math.dist(a[0], b[0]) for a, b in zip(samples, samples[1:])]
    assert max(gaps) - min(gaps) < 0.01


def test_straight_line_heading_and_zero_curvature():
    traj = generate_trajectory([(0, 0), (0, 48)], [(0, 48), (0, 48)])
    for p in traj:
        assert p.theta == pytest.approx(math.pi / 2)
        assert p.curvature == pytest.approx(0, abs=1e-9)
        assert p.omega == pytest.approx(0, abs=1e-9)


def test_signed_curvature_left_vs_right():
    # CCW circle of radius 2: d1 = (-2 sin, 2 cos), d2 = (-2 cos, -2 sin) at angle 0
    assert signed_curvature((0, 2), (-2, 0)) == pytest.approx(0.5)
    assert signed_curvature((0, 2), (2, 0)) == pytest.approx(-0.5)


def test_omega_is_velocity_times_curvature_and_turn_sign():
    left = generate_trajectory([(0, 0), (24, 24)], [(36, 0), (0, 36)])
    right = generate_trajectory([(0, 0), (24, -24)], [(36, 0), (0, -36)])
    mid_l, mid_r = left[len(left) // 2], right[len(right) // 2]
    assert mid_l.curvature > 0 and mid_l.omega > 0
    assert mid_r.curvature < 0 and mid_r.omega < 0
    for p in left:
        assert p.omega == pytest.approx(p.velocity * p.curvature)


def test_tank_wheel_speed_limit():
    k, v_max, w = 0.1, 60.0, 12.0
    ceil = velocity_ceiling(k, v_max, a_lat_max=1e9, track_width=w)
    assert ceil * (1 + k * w / 2) == pytest.approx(v_max)


def test_profile_respects_limits():
    cfg = RobotConfig(v_max=50, a_max=30, a_lat_max=40, track_width=12)
    traj = generate_trajectory(WAYPOINTS, TANGENTS, cfg)
    for p in traj:
        assert p.velocity <= cfg.v_max + 1e-6
        assert p.velocity ** 2 * abs(p.curvature) <= cfg.a_lat_max + 1e-6
        assert p.velocity * (1 + abs(p.curvature) * cfg.track_width / 2) <= cfg.v_max + 1e-6
