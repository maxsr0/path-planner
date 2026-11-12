import os
import shutil
import subprocess

import pytest

from exporter.binary_exporter import export_trajectory, import_trajectory
from exporter.header_exporter import export_trajectory_header, make_identifier
from profiler.trajectory import generate_trajectory

FIRMWARE_INCLUDE_DIR = os.environ.get("PRISM_FIRMWARE_INCLUDE")


def _traj():
    waypoints = [(0, 0), (1, 2), (6, 7), (9, 9)]
    tangents = [(0, 1), (1, 0), (1, 1), (0, 1)]
    return generate_trajectory(waypoints, tangents, 5, 100, 20)


def test_binary_roundtrip(tmp_path):
    traj = _traj()
    path = tmp_path / "test.bin"
    export_trajectory(traj, path)
    result = import_trajectory(path)

    assert len(result) == len(traj)
    for got, want in zip(result, traj):
        assert got == pytest.approx(want, rel=1e-6, abs=1e-5)


def test_binary_layout_little_endian(tmp_path):
    path = tmp_path / "t.bin"
    export_trajectory([(1.0, 2.0, 3.0, 4.0)], path)
    data = path.read_bytes()
    assert len(data) == 4 + 16
    assert data[:4] == b'\x01\x00\x00\x00'


@pytest.mark.parametrize("name,expected", [
    ("red_auton", "RED_AUTON"),
    ("2nd-auton", "PATH_2ND_AUTON"),
    ("skills (v2).final", "SKILLS__V2__FINAL"),
])
def test_make_identifier(name, expected):
    assert make_identifier(name) == expected


def test_header_initializer_shape(tmp_path):
    path = tmp_path / "red.hpp"
    export_trajectory_header([(1, 2, 3, 4)], path)
    text = path.read_text()
    assert "{ { 1.000000f, 2.000000f }, 3.000000f, 4.000000f }" in text
    assert '#include "PRISM/auton/traj_loader.h"' in text
    assert "struct TrajectoryPoint" not in text


def _compile(tmp_path, header, include_dirs=()):
    gxx = shutil.which("g++") or shutil.which("clang++")
    if gxx is None:
        pytest.skip("no C++ compiler available")
    src = tmp_path / "main.cpp"
    src.write_text(f'#include "{header.name}"\n#include "{header.name}"\nint main() {{ return 0; }}\n')
    args = [gxx, "-std=c++17", "-fsyntax-only", f"-I{tmp_path}"]
    args += [f"-I{d}" for d in include_dirs]
    return subprocess.run(args + [str(src)], capture_output=True, text=True)


def test_standalone_header_compiles(tmp_path):
    header = tmp_path / "2nd-auton.hpp"
    export_trajectory_header(_traj(), header, standalone=True)
    result = _compile(tmp_path, header)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not FIRMWARE_INCLUDE_DIR, reason="set PRISM_FIRMWARE_INCLUDE to the template's include/ dir")
def test_firmware_header_compiles(tmp_path):
    header = tmp_path / "red_auton.hpp"
    export_trajectory_header(_traj(), header)
    result = _compile(tmp_path, header, [FIRMWARE_INCLUDE_DIR])
    assert result.returncode == 0, result.stderr
