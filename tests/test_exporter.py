import pytest

from exporter.binary_exporter import *
from profiler.trajectory import generate_trajectory


def test_binary():
    waypoints = [(0, 0), (1, 2), (6, 7), (9, 9)]
    tangents = [(0, 1), (1, 0), (1, 1), (0, 1)]
    traj = generate_trajectory(waypoints, tangents, 5, 100, 20)

    export_trajectory(traj, "test.bin")

    result = import_trajectory("test.bin")

    for i in range(len(traj)):
        assert result[i][0] == pytest.approx(traj[i][0])
