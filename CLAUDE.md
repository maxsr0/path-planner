# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PRISM Path Planner: a tkinter + matplotlib desktop tool for VEX U robotics. Users place waypoints on a 144×144 inch field, the app fits a spline, generates a velocity-profiled trajectory, and exports it for the robot (`.bin` for SD card, `.hpp` for embedding in C++ firmware).

## Commands

```bash
pip install -r requirements.txt   # numpy>=1.26, matplotlib>=3.8, pytest
python main.py                    # launch the GUI
python -m pytest                  # run all tests (root conftest.py makes packages importable)
python -m pytest tests/test_profiler.py::test_name   # single test
```

No linter or build step is configured.

## Architecture

The pipeline is pure functions over plain lists/tuples, orchestrated by `profiler/trajectory.py::generate_trajectory`:

1. `spline/hermite.py` — `sample_hermite_path(waypoints, tangents, num_points_per_segment)` samples cubic Hermite segments into `(x, y)` points.
2. `spline/curvature.py` — `curvature_profile(path)` computes discrete Menger curvature per sample.
3. `profiler/velocity_profiler.py` — `velocity_profile` caps speed at `min(v_max, sqrt(a_max/κ))`, then does a forward (accel) and backward (decel) pass; start and end speed are forced to 0. `compute_timestamps` integrates time from distance / average speed.
4. Output is a list of `(x, y, v, t)` tuples consumed by `exporter/binary_exporter.py` and `exporter/header_exporter.py`.

The same `a_max` is used for both lateral (curvature ceiling) and longitudinal acceleration.

UI layer:
- `main.py` builds the tkinter window, side-panel entries (x, y, dx, dy), and buttons, then wires matplotlib canvas events to `ui/app.py::App`.
- `App` owns the `Waypoint` list (`ui/waypoint.py`), handles click/drag/select, recomputes tangents, redraws, and calls the pipeline. Trajectory parameters are currently hardcoded in `App._generate_trajectory` (`20` points/segment, `v_max=100`, `a_max=20`).
- Tangents: interior waypoints use Catmull-Rom (`0.5 * (next - prev)`) unless `manual_tangent` is set via the APPLY button; endpoint tangents always point toward their neighbor.

## Export format contracts

These formats are read by robot firmware, so changes must stay in sync with the C++ side:
- `.bin`: `int32` point count, then `float32 x, y, velocity, timestamp` per point.
- `.bin` is written explicitly little-endian (`<i`, `<4f`) to match `traj_loader.cpp`.
- `.hpp`: includes the firmware's `PRISM/auton/traj_loader.h` (firmware repo: `../../template/Prism Template`; `standalone=True` inlines the structs instead) and emits a `constexpr std::array<TrajectoryPoint, N>` whose name is the uppercased filename stem (e.g. `red_auton.hpp` → `RED_AUTON`), sanitized by `make_identifier`. Each element is `{ {x, y}, v, t }`.
- Set `PRISM_FIRMWARE_INCLUDE` to the template's `include/` dir to have pytest compile exported headers against the real firmware types (needs g++/clang++).
