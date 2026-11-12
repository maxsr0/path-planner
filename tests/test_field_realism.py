import json
import math

import numpy as np
import pytest

from profiler.config import RobotConfig
from profiler.trajectory import generate_trajectory

CFG = RobotConfig(v_max=60, a_max=60, spacing=0.25)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def heading_rate_matches_omega(traj):
    """d(theta)/dt from consecutive points should match the exported omega."""
    for a, b in zip(traj[1:-2], traj[2:-1]):
        dt = b.timestamp - a.timestamp
        if dt <= 1e-6 or a.velocity == 0 or b.velocity == 0:
            continue
        rate = wrap(b.theta - a.theta) / dt
        assert rate == pytest.approx((a.omega + b.omega) / 2, abs=0.05)


# ---------- trajectory ----------

def test_reversed_straight_line_drives_backwards():
    # Robot faces -x (heading tangents point -x) and backs up toward +x.
    traj = generate_trajectory([(0, 0), (48, 0)], [(-48, 0), (-48, 0)], CFG, reversed_segments=[True])
    assert traj[-1].x == pytest.approx(48)
    assert all(p.velocity <= 1e-9 for p in traj)
    assert min(p.velocity for p in traj) < -10
    for p in traj:
        assert abs(wrap(p.theta - math.pi)) < 1e-6
        assert p.omega == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("reverse", [False, True])
def test_omega_matches_heading_rate_on_curves(reverse):
    s = -1 if reverse else 1
    traj = generate_trajectory([(0, 0), (40, 40), (80, 0)], [(s * 40, 0), (s * 40, 0), (s * 40, 0)], CFG,
                               reversed_segments=[reverse, reverse])
    for p in traj:
        assert p.omega == pytest.approx(p.velocity * p.curvature)
    heading_rate_matches_omega(traj)


def test_direction_change_stops_at_cusp():
    # Drive forward to (48, 0), then back up to (24, 24).
    wps = [(0, 0), (48, 0), (24, 24)]
    tangents = [(48, 0), (48, 0), (24, -24)]  # robot keeps facing roughly +x while backing up
    traj = generate_trajectory(wps, tangents, CFG, reversed_segments=[False, True])
    cusp = min(range(len(traj)), key=lambda i: math.hypot(traj[i].x - 48, traj[i].y))
    assert (traj[cusp].x, traj[cusp].y) == pytest.approx((48, 0))
    assert traj[cusp].velocity == pytest.approx(0, abs=1e-9)
    assert all(p.velocity >= -1e-9 for p in traj[:cusp])
    assert all(p.velocity <= 1e-9 for p in traj[cusp:])
    assert all(b.timestamp > a.timestamp for a, b in zip(traj, traj[1:]))
    # heading is continuous through the cusp (no instant 180-degree flip)
    assert abs(wrap(traj[cusp + 1].theta - traj[cusp - 1].theta)) < math.radians(20)


def test_segment_speed_cap():
    wps = [(0, 0), (60, 0), (120, 0)]
    tangents = [(60, 0), (60, 0), (60, 0)]
    traj = generate_trajectory(wps, tangents, CFG, speed_caps=[20, None])
    first = [p for p in traj if p.x < 60]
    second = [p for p in traj if p.x > 70]
    assert max(p.velocity for p in first) <= 20 + 1e-9
    assert max(p.velocity for p in second) > 30


def test_no_options_matches_plain_call():
    wps, tangents = [(0, 0), (30, 40), (90, 10)], [(30, 40), (45, -15), (60, -30)]
    plain = generate_trajectory(wps, tangents, CFG)
    explicit = generate_trajectory(wps, tangents, CFG, reversed_segments=[False, False], speed_caps=[None, None])
    assert plain == explicit


# ---------- app ----------


# ---------- field picker ----------

from planner.fields import DEFAULT_FIELD, FIELDS_DIR, NO_FIELD, load_builtin_fields


def test_builtin_override_fields_present():
    names = [f.name for f in load_builtin_fields()]
    assert names == ["VURC 2027 - Override", "VURC 2027 - Override (Skills)", "V5RC 2027 - Override",
                     "V5RC 2027 - Override (Skills)", "V5RC Field Perimeter"]
    f = load_builtin_fields()[0]
    assert f.size_in == pytest.approx(3690 / 25.4)
    lo, hi, _, _ = f.extent
    assert (lo + hi) / 2 == pytest.approx(72) and hi - lo == pytest.approx(145.28, abs=0.01)
