# PRISM Path Planner

An autonomous path planning tool for VEX robotics, built for the PRISM VURC team. Place waypoints on a 144×144 inch field, tune tangents, and export a time-stamped trajectory binary ready to load on a robot.

![field screenshot placeholder](docs/img.png)

---

## How it works

### Path generation

Waypoints are connected using **cubic Hermite splines**. Each segment is defined by two endpoints and their tangent vectors, giving C1-continuous paths where heading is smooth across waypoints. Interior tangents are computed automatically using the Catmull-Rom convention, but can be overridden manually per waypoint.

### Sampling and curvature

The spline is resampled at **equal arc-length spacing** (0.5 in by default), so point density doesn't depend on tangent length or segment size. At each sample, heading comes from the spline's first derivative, and **signed curvature** is computed analytically:

```
κ = (x′y″ − y′x″) / (x′² + y′²)^(3/2)      (positive = turning left)
```

### Velocity profiling

Each point gets a speed ceiling, which is the smallest of:

- `v_max`
- the centripetal limit `sqrt(a_lat_max / |κ|)`
- the tank-drive outer-wheel limit `v_max / (1 + |κ|·W/2)` (when a track width `W` is set)

A **bidirectional pass** then enforces `a_max`. The forward pass accelerates up to the ceiling, and the backward pass guarantees the robot can slow or stop in time. Angular velocity is `ω = v·κ`. Robot constants live in `profiler/config.py::RobotConfig`.

### Export formats

Two export options are available. Each trajectory point is:

| field | unit |
|---|---|
| `x`, `y` | in |
| `theta` | rad, CCW from +x |
| `velocity` | in/s |
| `omega` | rad/s |
| `curvature` | 1/in, signed |
| `timestamp` | s |

**`.bin` — compact binary (SD card)**

```
char[4] "PRTJ" | uint32 version (2) | uint32 point count
[float32 x, y, theta, velocity, omega, curvature, timestamp] × N
```

The file is little-endian. `load_trajectory()` in the PRISM template reads it and rejects files with the wrong magic or version.

**`.hpp` — C++ header (embedded in firmware)**

Generates a `constexpr std::array<TrajectoryPoint, N>` that you include directly in your robot project. No SD card required as the path is baked into the binary. The header includes `PRISM/auton/traj_loader.h` for the `TrajectoryPoint` type. For use outside the PRISM template, `export_trajectory_header(..., standalone=True)` defines `Point`/`TrajectoryPoint` inline instead.

```cpp
#include "paths/my_path.hpp"

chassis.follow_trajectory(
    std::vector<TrajectoryPoint>(MY_PATH.begin(), MY_PATH.end())
);
```

The array name is derived from the filename (e.g. `red_auton.hpp` → `RED_AUTON`); invalid characters become `_`, and names starting with a digit get a `PATH_` prefix.

---

## Project structure

```
path-planner/
├── main.py                   # entry point, tkinter setup
├── spline/
│   ├── hermite.py            # cubic Hermite interpolation
│   └── curvature.py          # Menger curvature on discrete path
├── profiler/
│   ├── velocity_profiler.py  # bidirectional velocity pass
│   └── trajectory.py         # ties spline + profiler together
├── exporter/
│   ├── binary_exporter.py    # packs trajectory to .bin
│   └── header_exporter.py    # generates .hpp for firmware embed
├── ui/
│   ├── app.py                # click/drag waypoint interaction
│   ├── field.py              # matplotlib field rendering
│   └── waypoint.py           # waypoint data + tangent logic
└── tests/
```

---

## Setup

Python 3.10+ (tested on 3.14 with NumPy 2.x).

```bash
git clone https://github.com/maxsr0/path-planner
cd path-planner
pip install -r requirements.txt
python main.py
```

Dependencies: `numpy`, `matplotlib` (plus `pytest` for tests; run with `python -m pytest`)

---

## Usage

- **Click** anywhere on the field to place a waypoint. The new waypoint is selected automatically.
- **Drag** a waypoint to move it, and the spline updates live. Hold **Ctrl** to snap to whole inches.
- **Select** a waypoint to edit its position and tangent in the right panel. A square **tangent handle** appears: drag it to bend the curve (grey = automatic tangent, teal = manual).
- **Shift+click** near the path to insert a waypoint into that segment.
- **Right-click** a waypoint, or press **Delete** with one selected, to remove it. **Esc** deselects.
- **Ctrl+Z** / **Ctrl+Y** (or Ctrl+Shift+Z) undo and redo any edit.
- **Apply** commits typed values. Changing dx/dy makes the tangent manual; **Auto Tan** returns it to automatic.
- **New / Open / Save** (Ctrl+N / Ctrl+O / Ctrl+S, Ctrl+Shift+S = Save As) work with editable `.path.json` files. They hold the waypoints and tangents only; robot settings stay in `robot_config.json`, so one path can be exported for different robots. The title bar shows `*` when there are unsaved changes, and you're asked to save before New, Open or closing the window. Exports default to the path's name.
- **Robot** panel: set max speed, max accel, lateral accel, track width and point spacing, then **Apply Settings**. Values are saved to `robot_config.json` and reloaded on startup. Below it you'll see the path's length, total time and peak speed.
- **Export .bin** to save a binary trajectory for SD card loading
- **Export .hpp** to generate a C++ header to embed the path directly in firmware

---

## Built for

[PRISM](https://prismrobotics.org) - VEX U Robotics Competition team.
