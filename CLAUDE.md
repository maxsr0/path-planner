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

UI tests run headless: root `conftest.py` forces the Agg backend and provides the `make_app` fixture, which builds an `App` with fake entries and canvas, plus `Click`/`Key` fake events.

No linter or build step is configured.

## Architecture

The pipeline is pure functions over plain lists/tuples, orchestrated by `profiler/trajectory.py::generate_trajectory(waypoints, tangents, config)`:

1. `spline/arclength.py` — `sample_path_by_distance` resamples the cubic Hermite spline (`spline/hermite.py`) at equal arc-length spacing and returns position plus first and second derivatives. `signed_curvature` is analytic (positive = left turn).
2. `profiler/velocity_profiler.py` — the speed ceiling is `min(v_max, sqrt(a_lat/|κ|), v_max/(1+|κ|W/2))`, followed by forward (accel) and backward (decel) passes with `a_max`; start and end speed are 0. `compute_timestamps` uses `dt = 2d/(v0+v1)`.
3. Output is a list of `TrajectoryPoint(x, y, theta, velocity, omega, curvature, timestamp)` namedtuples. That field order is the export contract.

`profiler/config.py::RobotConfig` holds v_max, a_max, a_lat_max, track_width (0 disables the wheel limit) and spacing. `spline/curvature.py` (Menger) and `sample_hermite_path` (uniform t) are only used for the UI preview and in tests, not for export.

UI layer:
- `main.py` builds the tkinter window, side-panel entries (x, y, dx, dy), and buttons, then wires matplotlib canvas events to `ui/app.py::App`.
- `App` owns the `Waypoint` list (`ui/waypoint.py`), handles click/drag/select, recomputes tangents, redraws, and calls the pipeline. Editing: right-click/Delete removes, shift+click inserts into the nearest segment (`_nearest_segment`), ctrl snaps (`_point`), and the selected waypoint's handle at `p + m/3` (`HANDLE_SCALE`) is drag-editable. Modifier keys are read from the mpl event's `key` string (`_modifiers`).
- Path files: `exporter/path_file.py` (`save_path`/`load_path`, `{"format": "prism-path", "version": 1, "waypoints": [...]}`). `App.is_dirty()` compares the current waypoint snapshot (ignoring selection) with `_saved_data`, so undoing back to the saved state counts as clean. `confirm_discard()` guards New, Open and window close (`on_quit`).
- Undo/redo: every edit calls `push_history()` *before* mutating, which stores a `_snapshot()` (waypoint tuples + selected index). A drag records one snapshot on its first movement, so a plain click adds no history. New edit paths must call `push_history()` too. Profile settings come from `App.config`, edited in the ROBOT panel (`App.SETTINGS_FIELDS`) and persisted to `robot_config.json` next to `main.py` via `load_config`/`save_config`. A missing file means defaults; a bad file falls back to defaults with a warning. The panel also shows path length, time and peak speed (`update_stats`, recomputed on every redraw).
- Tangents: interior waypoints use Catmull-Rom (`0.5 * (next - prev)`) unless `manual_tangent` is set via the APPLY button; endpoint tangents point toward their neighbor unless manual.

## Export format contracts

These formats are read by robot firmware, so changes must stay in sync with the C++ side:
- `.bin`: little-endian `"PRTJ"` magic, `uint32` version (2), `uint32` count, then 7×`float32` per point in `TrajectoryPoint` order. Bump `VERSION` in `exporter/binary_exporter.py` and `TRAJ_VERSION` in firmware `traj_loader.cpp` together.
- `.hpp`: includes the firmware's `PRISM/auton/traj_loader.h` (firmware repo: `../../template/Prism Template`; `standalone=True` inlines the structs instead) and emits a `constexpr std::array<TrajectoryPoint, N>` whose name is the uppercased filename stem (e.g. `red_auton.hpp` → `RED_AUTON`), sanitized by `make_identifier`. Each element is `{ {x, y}, theta, v, omega, curvature, t }`.
- Set `PRISM_FIRMWARE_ROOT` to the template repo root to have pytest compile exported headers and the real `traj_loader.cpp` (needs g++/clang++):

```bash
PRISM_FIRMWARE_ROOT="../../template/Prism Template" python -m pytest
```

Do not commit or push the template repo without the user asking; edits there are left local.
