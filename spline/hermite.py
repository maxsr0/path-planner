import math
import numpy as np


def cubic_hermite_1d(p0, p1, m0, m1, t):
    a = 2 * p0 - 2 * p1 + m0 + m1
    b = -3 * p0 + 3 * p1 - 2 * m0 - m1
    c = m0
    d = p0
    # at^3 + bt^2 + ct + d
    return a * math.pow(t, 3) + b * math.pow(t, 2) + c * t + d


def cubic_hermite_1d_derivative(p0, p1, m0, m1, t):
    a = 2 * p0 - 2 * p1 + m0 + m1
    b = -3 * p0 + 3 * p1 - 2 * m0 - m1
    c = m0
    # 3at^2 + 2bt + c
    return (3 * a * math.pow(t, 2)) + (2 * b * t) + c


def cubic_hermite_1d_second_derivative(p0, p1, m0, m1, t):
    a = 2 * p0 - 2 * p1 + m0 + m1
    b = -3 * p0 + 3 * p1 - 2 * m0 - m1
    # 6at + 2b
    return 6 * a * t + 2 * b


def hermite_eval_2d(p0, p1, m0, m1, t):
    """Return (position, first derivative, second derivative) at t, each as (x, y)."""
    pos = cubic_hermite_2d(p0, p1, m0, m1, t)
    d1 = (cubic_hermite_1d_derivative(p0[0], p1[0], m0[0], m1[0], t),
          cubic_hermite_1d_derivative(p0[1], p1[1], m0[1], m1[1], t))
    d2 = (cubic_hermite_1d_second_derivative(p0[0], p1[0], m0[0], m1[0], t),
          cubic_hermite_1d_second_derivative(p0[1], p1[1], m0[1], m1[1], t))
    return pos, d1, d2


def cubic_hermite_2d(p0, p1, m0, m1, t):
    x = cubic_hermite_1d(p0[0], p1[0], m0[0], m1[0], t)
    y = cubic_hermite_1d(p0[1], p1[1], m0[1], m1[1], t)

    return x, y


def sample_hermite_2d(p0, p1, m0, m1, num_points):
    a = np.linspace(0, 1, num_points)
    output = [cubic_hermite_2d(p0, p1, m0, m1, t) for t in a]

    return output


def sample_hermite_path(waypoints, tangents, num_points_per_segment):
    path = []
    for i in range(len(waypoints) - 1):
        l = sample_hermite_2d(waypoints[i], waypoints[i+1], tangents[i], tangents[i+1], num_points_per_segment)
        if i == 0:
            path += l
        else:
            path += l[1:]

    return path
