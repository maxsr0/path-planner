import bisect
import math
from typing import NamedTuple

from spline.arclength import sample_path_by_distance, signed_curvature
from profiler.config import RobotConfig
from profiler.velocity_profiler import velocity_profile, compute_timestamps


class TrajectoryPoint(NamedTuple):
    """Field order matches the firmware's TrajectoryPoint and the .bin layout."""
    x: float
    y: float
    theta: float      # heading, radians, CCW from +x
    velocity: float   # in/s
    omega: float      # angular velocity, rad/s (velocity * curvature)
    curvature: float  # signed, 1/in (positive = turning left)
    timestamp: float  # s


def state_at(trajectory, t):
    """Interpolated (x, y, theta, velocity) at time t, clamped to the trajectory's time range."""
    if not trajectory:
        raise ValueError("empty trajectory")
    if t <= trajectory[0].timestamp:
        p = trajectory[0]
        return p.x, p.y, p.theta, p.velocity
    if t >= trajectory[-1].timestamp:
        p = trajectory[-1]
        return p.x, p.y, p.theta, p.velocity

    i = bisect.bisect_right([p.timestamp for p in trajectory], t)
    a, b = trajectory[i - 1], trajectory[i]
    span = b.timestamp - a.timestamp
    f = (t - a.timestamp) / span if span > 0 else 0.0
    dtheta = (b.theta - a.theta + math.pi) % (2 * math.pi) - math.pi  # shortest way round
    return (a.x + (b.x - a.x) * f,
            a.y + (b.y - a.y) * f,
            a.theta + dtheta * f,
            a.velocity + (b.velocity - a.velocity) * f)


def generate_trajectory(waypoints, tangents, config=None, reversed_segments=None, speed_caps=None):
    """Build the time-parameterized trajectory.

    tangents: robot heading vectors at each waypoint.
    reversed_segments[i]: drive segment i (waypoint i -> i+1) backwards. Reversed points get
        negative velocity, theta = the direction the robot faces, and robot-frame curvature,
        so omega = velocity * curvature still holds. The robot stops where direction changes.
    speed_caps[i]: optional max speed (in/s) for segment i (None = no cap).
    Both lists may be per-waypoint (extra trailing entries are ignored).
    """
    config = config or RobotConfig()
    num_segments = len(waypoints) - 1
    signs = [-1 if reversed_segments and reversed_segments[i] else 1 for i in range(num_segments)]
    caps = [(speed_caps[i] if speed_caps and speed_caps[i] is not None else math.inf)
            for i in range(num_segments)]

    samples = sample_path_by_distance(waypoints, tangents, config.spacing, signs=signs)
    path = [s.pos for s in samples]
    path_curvatures = [signed_curvature(s.d1, s.d2) for s in samples]

    # Per-point speed limits: the segment cap, the lower cap at joints, and a full stop at direction changes.
    limits = []
    for j, s in enumerate(samples):
        lim = caps[s.seg]
        if j > 0 and samples[j - 1].seg != s.seg:
            lim = min(lim, caps[samples[j - 1].seg])
            if signs[samples[j - 1].seg] != signs[s.seg]:
                lim = 0.0
        limits.append(lim)

    speeds = velocity_profile(path, path_curvatures, config.v_max, config.a_max,
                              config.lateral_accel, config.track_width, limits)
    timestamps = compute_timestamps(path, speeds, config.a_max)

    # Heading = direction the robot faces (path direction, flipped on reversed segments).
    points = []
    last = math.atan2(signs[0] * tangents[0][1], signs[0] * tangents[0][0])
    for s, k, v, t in zip(samples, path_curvatures, speeds, timestamps):
        sign = signs[s.seg]
        if math.hypot(*s.d1) > 1e-9:
            last = math.atan2(sign * s.d1[1], sign * s.d1[0])
        velocity, curvature = sign * v, sign * k
        points.append(TrajectoryPoint(s.pos[0], s.pos[1], last, velocity, velocity * curvature, curvature, t))
    return points
