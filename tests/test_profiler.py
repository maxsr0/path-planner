import pytest

from profiler.velocity_profiler import velocity_profile
from spline.curvature import curvature_profile
from spline.hermite import sample_hermite_path
from profiler.velocity_profiler import compute_timestamps


def test_velocity_profile():
    path = sample_hermite_path(
        [(0, 0), (5, 0), (6, 1)],  # sharp corner at the end
        [(1, 0), (1, 0), (0, 1)],
        20
    )
    curvatures = curvature_profile(path)
    profile = velocity_profile(path, curvatures, 100, 30)

    assert profile[0] == pytest.approx(0)
    assert profile[-1] == pytest.approx(0)
    assert profile[10] > profile[0]
    assert profile[-2] < profile[10]


def test_compute_timestamp():
    path = sample_hermite_path(
        [(0, 0), (5, 0), (6, 1)],  # sharp corner at the end
        [(1, 0), (1, 0), (0, 1)],
        20
    )
    curvatures = curvature_profile(path)
    profile = velocity_profile(path, curvatures, 100, 30)

    t = compute_timestamps(path, profile)
    assert t[0] == pytest.approx(0)
    for i in range(1, len(path)):
        assert t[i] > t[i-1]
