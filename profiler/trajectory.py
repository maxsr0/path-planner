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


def generate_trajectory(waypoints, tangents, config=None):
    config = config or RobotConfig()
    samples = sample_path_by_distance(waypoints, tangents, config.spacing)

    path = [pos for pos, _, _ in samples]
    curvatures = [signed_curvature(d1, d2) for _, d1, d2 in samples]

    # Heading from the spline derivative; hold the last heading through cusps.
    headings = []
    last = math.atan2(tangents[0][1], tangents[0][0])
    for _, d1, _ in samples:
        if math.hypot(*d1) > 1e-9:
            last = math.atan2(d1[1], d1[0])
        headings.append(last)

    velocities = velocity_profile(path, curvatures, config.v_max, config.a_max,
                                  config.lateral_accel, config.track_width)
    timestamps = compute_timestamps(path, velocities, config.a_max)

    return [TrajectoryPoint(x, y, th, v, v * k, k, t)
            for (x, y), th, v, k, t in zip(path, headings, velocities, curvatures, timestamps)]
