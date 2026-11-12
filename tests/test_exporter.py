import os
import shutil
import struct
import subprocess

import pytest

from exporter.binary_exporter import export_trajectory, import_trajectory
from exporter.header_exporter import export_trajectory_header, make_identifier
from profiler.trajectory import TrajectoryPoint, generate_trajectory

# Path to the PRISM template root (contains include/ and src/); enables firmware compile tests.
FIRMWARE_ROOT = os.environ.get("PRISM_FIRMWARE_ROOT")
needs_firmware = pytest.mark.skipif(not FIRMWARE_ROOT, reason="set PRISM_FIRMWARE_ROOT to the template repo root")


def _traj():
    waypoints = [(0, 0), (1, 2), (6, 7), (9, 9)]
    tangents = [(0, 1), (1, 0), (1, 1), (0, 1)]
    return generate_trajectory(waypoints, tangents)


def _cxx():
    gxx = shutil.which("g++") or shutil.which("clang++")
    if gxx is None:
        pytest.skip("no C++ compiler available")
    return gxx


def test_binary_roundtrip(tmp_path):
    traj = _traj()
    path = tmp_path / "test.bin"
    export_trajectory(traj, path)
    result = import_trajectory(path)

    assert len(result) == len(traj)
    for got, want in zip(result, traj):
        assert tuple(got) == pytest.approx(tuple(want), rel=1e-6, abs=1e-5)


def test_binary_layout(tmp_path):
    path = tmp_path / "t.bin"
    export_trajectory([TrajectoryPoint(1, 2, 3, 4, 5, 6, 7)], path)
    data = path.read_bytes()
    assert len(data) == 12 + 28
    assert data[:12] == b'PRTJ' + struct.pack('<II', 2, 1)
    assert struct.unpack('<7f', data[12:]) == (1, 2, 3, 4, 5, 6, 7)


def test_binary_rejects_wrong_magic(tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b'NOPE' + bytes(8))
    with pytest.raises(ValueError):
        import_trajectory(path)


@pytest.mark.parametrize("name,expected", [
    ("red_auton", "RED_AUTON"),
    ("2nd-auton", "PATH_2ND_AUTON"),
    ("skills (v2).final", "SKILLS__V2__FINAL"),
])
def test_make_identifier(name, expected):
    assert make_identifier(name) == expected


def test_header_initializer_shape(tmp_path):
    path = tmp_path / "red.hpp"
    export_trajectory_header([TrajectoryPoint(1, 2, 3, 4, 5, 6, 7)], path)
    text = path.read_text()
    assert "{ { 1.000000f, 2.000000f }, 3.000000f, 4.000000f, 5.000000f, 6.000000f, 7.000000f }" in text
    assert '#include "PRISM/auton/traj_loader.h"' in text
    assert "struct TrajectoryPoint" not in text


def _compile_header(tmp_path, header, include_dirs=()):
    src = tmp_path / "main.cpp"
    src.write_text(f'#include "{header.name}"\n#include "{header.name}"\nint main() {{ return 0; }}\n')
    args = [_cxx(), "-std=c++17", "-fsyntax-only", f"-I{tmp_path}"] + [f"-I{d}" for d in include_dirs]
    return subprocess.run(args + [str(src)], capture_output=True, text=True)


def test_standalone_header_compiles(tmp_path):
    header = tmp_path / "2nd-auton.hpp"
    export_trajectory_header(_traj(), header, standalone=True)
    result = _compile_header(tmp_path, header)
    assert result.returncode == 0, result.stderr


@needs_firmware
def test_firmware_header_compiles(tmp_path):
    header = tmp_path / "red_auton.hpp"
    export_trajectory_header(_traj(), header)
    result = _compile_header(tmp_path, header, [os.path.join(FIRMWARE_ROOT, "include")])
    assert result.returncode == 0, result.stderr


@needs_firmware
def test_firmware_loader_reads_exported_bin(tmp_path):
    """Compile the real traj_loader.cpp on the host and load a planner-exported .bin."""
    traj = _traj()
    bin_path = tmp_path / "path.bin"
    export_trajectory(traj, bin_path)

    main = tmp_path / "main.cpp"
    main.write_text(r'''
#include "PRISM/auton/traj_loader.h"
#include <cstdio>
int main(int argc, char** argv) {
    auto t = load_trajectory(argv[1]);
    printf("%zu\n", t.size());
    for (auto& p : t)
        printf("%.6f %.6f %.6f %.6f %.6f %.6f %.6f\n",
               p.pos.x, p.pos.y, p.theta, p.velocity, p.omega, p.curvature, p.timestamp);
}
''')
    exe = tmp_path / "loader"
    build = subprocess.run([_cxx(), "-std=c++17", f"-I{os.path.join(FIRMWARE_ROOT, 'include')}", str(main),
                            os.path.join(FIRMWARE_ROOT, "src", "PRISM", "auton", "traj_loader.cpp"),
                            "-o", str(exe)], capture_output=True, text=True)
    assert build.returncode == 0, build.stderr

    out = subprocess.run([str(exe), str(bin_path)], capture_output=True, text=True).stdout.split("\n")
    assert int(out[0]) == len(traj)
    for line, want in zip(out[1:], traj):
        assert tuple(map(float, line.split())) == pytest.approx(tuple(want), rel=1e-5, abs=1e-5)

    bad = tmp_path / "bad.bin"
    bad.write_bytes(b'NOPE' + bytes(8))
    out = subprocess.run([str(exe), str(bad)], capture_output=True, text=True).stdout
    assert out.split()[0] == "0"
