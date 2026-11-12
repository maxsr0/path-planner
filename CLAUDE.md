# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PRISM Path Planner: a PySide6 (Qt) desktop tool for VEX U robotics. Users place waypoints on a 144×144 inch field, the app fits a spline, generates a velocity-profiled trajectory, and exports it for the robot (`.bin` for SD card, `.hpp` for embedding in C++ firmware).

## Commands

```bash
pip install -r requirements.txt   # numpy, PySide6, Pillow, pytest, pytest-qt
python main.py                    # launch the app (maximized; F11 = full screen)
python -m pytest                  # all tests; Qt tests run offscreen (tests/qt/conftest.py sets QT_QPA_PLATFORM)
python -m pytest tests/test_editor.py::test_drag_point_is_one_undo_step   # single test
```

No linter or build step is configured. **Write tests before code** for every change: write them, see them fail for the right reason, then implement.

## Architecture

Three layers, with no UI code below the top one:

1. **Core pipeline** (pure functions), orchestrated by `profiler/trajectory.py::generate_trajectory(waypoints, tangents, config, reversed_segments, speed_caps)`:
   - `spline/arclength.py`: samples each Hermite segment (`spline/hermite.py`) at equal arc-length spacing, so waypoints are exact samples, and computes analytic signed curvature (positive = left). `segment_args` negates headings on reversed segments, which makes a direction change a cusp.
   - `profiler/velocity_profiler.py`: speed ceiling `min(v_max, sqrt(a_lat/|κ|), v_max/(1+|κ|W/2), segment cap)`, then forward/backward passes with `a_max`. v=0 at the ends and at direction changes. `dt = 2d/(v0+v1)`.
   - Output: `TrajectoryPoint(x, y, theta, velocity, omega, curvature, timestamp)`. That field order is the export contract. Reversed points have negative velocity, robot-facing theta and robot-frame curvature (`omega = v·κ` always holds). `state_at` interpolates a pose at time t.
   - `profiler/config.py::RobotConfig` (validated, JSON load/save) and `exporter/` (`.bin`, `.hpp`, `.path.json`).
2. **`planner/`** (toolkit-free model; test it without a GUI):
   - `editor.py::Editor` owns waypoints, selection, sign-aware auto headings (`compute_tangents`), hit testing (pass `radius` in inches), drag (`begin_drag`/`drag_to`/`end_drag`), insert/delete, `update_waypoint` (several fields in one undo step), undo/redo, robot config, the cached `trajectory`, `stats()`, dirty tracking and `new`/`load`/`save`.
     - Every edit pushes history before mutating; a drag records one snapshot on its first move.
     - Listeners registered with `subscribe(fn)` get `'path' | 'selection' | 'config' | 'file'`.
     - `Editor` never opens dialogs; it raises `ValueError`/`OSError`.
   - `Playback` is the real-time clock.
   - `waypoint.py`: `dx/dy` is the robot *heading*. `reversed` and `v_cap` apply to the segment leaving the waypoint.
   - `fields.py`: built-in field renders from `fields/fields.json` (`size_mm` 3690 includes the wall; centered via `FieldPreset.extent`). `FieldLibrary` handles custom images and the remembered choice in `ui_prefs.json` (gitignored, per user).
3. **`qt_ui/`** (PySide6):
   - `main_window.py` holds the toolbar, status bar, playback `QTimer` and file prompts. Dialogs go through `ask_discard`/`ask_save_path`/`ask_open_path`/`ask_image_path`/`show_error`, which tests replace. Delete/Space/F/Esc are shortcuts on the field view only, so typing in the sidebars isn't hijacked.
   - `field_view.py` is a `QGraphicsView` in inches with scene y flipped (`to_scene`/`to_field`).
     - Waypoints and handles ignore the view transform, so they stay the same pixel size at any zoom.
     - The path is merged into same-color runs over a casing line, and the scene uses `NoIndex`. That's what keeps dragging at about 16 ms per frame.
   - `speed_plot.py` is a `QPainter` speed-vs-time strip. Compute `v_range()` once per paint: a per-point rescan was O(n²), and a call-count test guards it.
   - `panels.py` has the left waypoint list and editor (spin boxes commit on Enter or focus-out, one undo step each, no-op if unchanged) and the right robot settings and path stats.
   - `theme.py` defines the dark/light tokens, the stylesheet and the per-theme one-hue speed ramp (dark: lighter = faster; light: darker = faster), quantized to 32 steps (`SPEED_STEPS`) and cached. The choice persists in `ui_prefs.json`.

Testing notes: `tests/qt/test_main_window.py::dispose()` really destroys windows (`shiboken6.delete`). Leaked or still-open windows steal later tests' mouse events and slow them down. Offscreen widgets only paint after `waitExposed` or `grab()`.

## Export format contracts

These formats are read by robot firmware, so changes must stay in sync with the C++ side:
- `.bin`: little-endian `"PRTJ"` magic, `uint32` version (2), `uint32` count, then 7×`float32` per point in `TrajectoryPoint` order. Bump `VERSION` in `exporter/binary_exporter.py` and `TRAJ_VERSION` in firmware `traj_loader.cpp` together.
- `.hpp`: includes the firmware's `PRISM/auton/traj_loader.h` (firmware repo: `../../template/Prism Template`; `standalone=True` inlines the structs instead) and emits a `constexpr std::array<TrajectoryPoint, N>` whose name is the uppercased filename stem (e.g. `red_auton.hpp` → `RED_AUTON`), sanitized by `make_identifier`. Each element is `{ {x, y}, theta, v, omega, curvature, t }`.
- Set `PRISM_FIRMWARE_ROOT` to the template repo root to have pytest compile exported headers and the real `traj_loader.cpp` (needs g++/clang++):

```bash
PRISM_FIRMWARE_ROOT="../../template/Prism Template" python -m pytest
```

Do not commit or push the template repo without the user asking; edits there are left local.
