import math
import numpy as np


def velocity_profile(path, curvatures, v_max, a_max):
    ceil = [0.0] * len(path)

    for i in range(len(path)):
        k = curvatures[i]
        ceil[i] = min(v_max, math.sqrt(a_max / k)) if k > 0 else v_max

    speeds = [0.0] * len(path)
    speeds[0] = 0

    for i in range(1, len(path)):  # forwards pass
        dist = np.linalg.norm(np.array(path[i]) - np.array(path[i - 1]))
        speeds[i] = min(ceil[i], math.sqrt(speeds[i - 1] ** 2 + 2 * a_max * dist))  # vf^2 = vi^2 + 2ax

    speeds[-1] = 0
    for i in range(len(path) - 2, -1, -1):  # backwards pass
        dist = np.linalg.norm(np.array(path[i]) - np.array(path[i + 1]))
        speeds[i] = min(speeds[i], math.sqrt(speeds[i + 1] ** 2 + 2 * a_max * dist))

    return speeds


def compute_timestamps(path, speeds):
    timestamps = [0] * len(path)
    for i in range(1, len(path)):
        dist = np.linalg.norm(np.array(path[i]) - np.array(path[i - 1]))
        v = (speeds[i - 1] + speeds[i]) / 2
        if v == 0:
            timestamps[i] = timestamps[i - 1] + 0
        else:
            timestamps[i] = timestamps[i - 1] + dist / v

    return timestamps
