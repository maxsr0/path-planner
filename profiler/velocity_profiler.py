import math


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def velocity_ceiling(curvature, v_max, a_lat_max, track_width=0.0):
    """Max speed allowed at a point with the given (signed) curvature.

    - centripetal limit: v^2 * |k| <= a_lat_max
    - tank drive: the outer wheel moves at v * (1 + |k| * W/2) and must stay <= v_max
    """
    k = abs(curvature)
    ceil = v_max
    if k > 0:
        ceil = min(ceil, math.sqrt(a_lat_max / k))
        if track_width > 0:
            ceil = min(ceil, v_max / (1 + k * track_width / 2))
    return ceil


def velocity_profile(path, curvatures, v_max, a_max, a_lat_max=None, track_width=0.0):
    if a_lat_max is None:
        a_lat_max = a_max
    n = len(path)
    ceil = [velocity_ceiling(k, v_max, a_lat_max, track_width) for k in curvatures]

    speeds = [0.0] * n
    for i in range(1, n):  # forward pass: vf^2 = vi^2 + 2ad
        d = _dist(path[i - 1], path[i])
        speeds[i] = min(ceil[i], math.sqrt(speeds[i - 1] ** 2 + 2 * a_max * d))

    speeds[-1] = 0.0
    for i in range(n - 2, -1, -1):  # backward pass
        d = _dist(path[i], path[i + 1])
        speeds[i] = min(speeds[i], math.sqrt(speeds[i + 1] ** 2 + 2 * a_max * d))

    return speeds


def compute_timestamps(path, speeds, a_max=None):
    timestamps = [0.0] * len(path)
    for i in range(1, len(path)):
        d = _dist(path[i - 1], path[i])
        v_sum = speeds[i - 1] + speeds[i]
        if v_sum > 1e-9:
            dt = 2 * d / v_sum  # constant acceleration between samples
        elif d > 0 and a_max:
            dt = math.sqrt(2 * d / a_max)  # moving from rest
        else:
            dt = 0.0
        timestamps[i] = timestamps[i - 1] + dt
    return timestamps
