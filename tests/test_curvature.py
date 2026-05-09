import pytest

from spline.curvature import curvature_at_point
from spline.curvature import curvature_profile


def test_curvature_at_point():
    assert curvature_at_point((0, 0), (0, 1), (0, 2)) == pytest.approx(0)
    assert curvature_at_point((1, 0), (0, 1), (-1, 0)) == pytest.approx(1)

    path = [(0,0), (0,1), (0,2), (0,3)]
    result = curvature_profile(path)
    assert len(result) == len(path)
    for r in result:
        assert r == pytest.approx(0)
