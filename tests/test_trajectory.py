import pytest

from profiler.trajectory import generate_trajectory


def test_generate_trajectory():
    waypoints = [(0, 0), (1, 2), (6, 7), (9, 9)]
    tangents = [(0, 1), (1, 0), (1, 1), (0, 1)]
    result = generate_trajectory(waypoints, tangents, 5, 100, 20)

    assert len(result) == pytest.approx(13)
    assert result[0][3] == result[0][2] == pytest.approx(0)
    assert result[12][2] == pytest.approx(0)
    