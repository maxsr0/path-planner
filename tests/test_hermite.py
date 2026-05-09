import pytest

from spline.hermite import cubic_hermite_1d
from spline.hermite import cubic_hermite_1d_derivative
from spline.hermite import cubic_hermite_2d
from spline.hermite import sample_hermite_2d
from spline.hermite import sample_hermite_path


def test_cubic_hermite_1d():
    assert cubic_hermite_1d(0, 1, 1, 0, 0) == 0
    assert cubic_hermite_1d(0, 1, 1, 0, 1) == 1
    assert cubic_hermite_1d(0, 1, 1, 0, 0.5) == 0.625

    assert cubic_hermite_1d_derivative(0, 1, 1, 0, 0) == 1
    assert cubic_hermite_1d_derivative(0, 1, 1, 0, 1) == 0

    assert cubic_hermite_2d((0, 0), (1, 1), (1, 0), (0, 1), 0) == pytest.approx((0, 0))
    assert cubic_hermite_2d((0, 0), (1, 1), (1, 0), (0, 1), 1) == pytest.approx((1, 1))

    result = sample_hermite_2d((0, 0), (1, 1), (1,0), (0,1), 5)
    assert result[0][0] == pytest.approx(0)
    assert result[0][1] == pytest.approx(0)

    waypoints = [(1,1), (2,2), (3,5)]
    tangents = [(0,1), (1,0), (0,0)]

    result = sample_hermite_path(waypoints, tangents, 5)
    assert len(result) == 9
    assert result[0] == waypoints[0]
    assert result[8] == waypoints[2]

