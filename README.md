# PRISM Path Planner

A desktop path planner for VEX robotics, built for the PRISM VURC team. Draw a path on the real game field, and the planner turns it into a time-stamped, velocity-profiled trajectory (position, heading, speed and turn rate at every point) ready for a Ramsete-style follower on the robot.

![PRISM Path Planner, dark theme](docs/img.png)

<sub>Light theme: [docs/light.png](docs/light.png)</sub>

## Features

- **The real field, full screen.** Choose VURC or V5RC 2027 *Override* (match or Skills), a plain perimeter, a grid, or your own image. Zoom and pan for precise placement.
- **Direct editing.** Click to add waypoints, drag to move them, drag the square handle to bend the curve, shift+click to insert, and right-click to delete. Full undo/redo.
- **Driving in reverse and speed caps, per segment.** Reversed segments export negative velocity, and the robot stops where it changes direction.
- **Speed you can see.** The path is colored by planned speed, and a speed-vs-time graph sits underneath. Hover to scrub a robot-sized marker along the path, or play it back in real time.
- **Live numbers:** total time, path length and peak speed update as you edit.
- **Firmware-ready exports:** a `.bin` for the SD card or a `.hpp` to compile into the robot program.
- **Light and dark themes**, and editable `.path.json` files you can save and reopen.

## Setup

Requires **Python 3.10 or newer** (tested on 3.14). PySide6 and NumPy have no builds for older versions, so on Python 3.8 or 3.9 `pip install` fails with "No matching distribution found".

```bash
git clone https://github.com/maxsr0/path-planner
cd path-planner
py -3.14 -m venv .venv          # Windows; elsewhere: python3 -m venv .venv
.venv\Scripts\activate          # Windows; elsewhere: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The app opens maximized. **F11** toggles full screen, and **F1** (or **? Shortcuts** in the bottom-right) lists every shortcut.

**First thing to do:** enter your robot's numbers in the **Robot** panel and click **Apply robot settings**. The defaults (100 in/s, 20 in/s², track width off) are placeholders. With the track width set, the planner keeps the outer wheel under max speed in turns.

## Using the planner

```
 New Open Save | Undo Redo | Play Fit Speed graph | Field ▾             Light theme | Export .bin  Export .hpp
┌───────────────┬───────────────────────────────────────────┬────────────────┐
│ WAYPOINTS     │                                           │ ROBOT          │
│  1 (18, 22)   │                                           │  max speed     │
│  2 (52, 64)   │               the field                   │  max accel …   │
│ SELECTED      │                                           │ PATH           │
│  x  y         ├───────────────────────────────────────────┤  total time    │
│  heading      │  speed vs time                            │  length        │
│  reverse, cap │                                           │  peak speed    │
└───────────────┴───────────────────────────────────────────┴────────────────┘
 cursor x / y   hint for whatever is under the mouse                ? Shortcuts
```

### On the field

| Do this | To |
|---|---|
| Click empty field | Add a waypoint at the end of the path (it becomes selected) |
| Drag a waypoint | Move it. Hold **Ctrl** to snap to whole inches |
| Drag the square handle | Set the heading by hand (grey = automatic, accent color = manual) |
| **Shift**+click near the path | Insert a waypoint into that segment |
| Right-click a waypoint, or **Delete** | Remove it. **Esc** deselects |
| Mouse wheel / middle-drag / **F** | Zoom / pan / fit the field |

Waypoints are numbered on the field and in the list. Dashed squares show the robot's footprint (sized to the track width) at the start and end.

### Left sidebar: waypoints

Click a row to select a waypoint. Its **x**, **y** and **heading** apply when you press Enter or click away, and each change is one undo step. Changing the heading makes it manual; **Auto heading** puts it back to automatic.

Two options apply to the segment *leaving* the selected waypoint:

- **Drive next segment in reverse.** The robot backs along that segment. It's drawn dashed on the field and shows as negative speed on the graph. Where the direction changes, the path forms a cusp and the robot comes to a stop.
- **Max speed, next segment.** A speed cap for that segment only (**none** = no cap).

### Right sidebar: robot and path

**Robot**: max speed, max acceleration, lateral (turning) acceleration, track width and point spacing. **Apply robot settings** saves them to `robot_config.json`, which is loaded on every start. **Path**: total time, length and peak speed of the current path.

### Speed graph and playback

The path and the graph share one blue color scale for speed, so the graph's y axis is the key for the path colors. Hover over the graph to move the robot marker to that moment, or press **Space** (or **Play**) to watch it drive in real time. **Ctrl+G** hides the graph.

### Toolbar

- **New / Open / Save** (Ctrl+N / Ctrl+O / Ctrl+S; Ctrl+Shift+S = Save As) work with `.path.json` files. These store waypoints only, so the same path can be exported with different robot settings. The title shows `*` while there are unsaved changes, and you're asked before anything is lost.
- **Undo / Redo** (Ctrl+Z / Ctrl+Y) cover every edit.
- **Field ▾** offers VURC 2027 Override, VURC 2027 Override (Skills), V5RC 2027 Override, V5RC 2027 Override (Skills), V5RC Field Perimeter, **None (grid)**, or **+ Add image…** for your own top-down image cropped to the 144×144 in tiles.
- **Light theme / Dark theme** (Ctrl+T) switches the whole app.
- **Export .bin** (Ctrl+E) and **Export .hpp** (Ctrl+Shift+E) write the trajectory for the robot (see below). File names default to the path's name.

Your field and theme choices are remembered per user in `ui_prefs.json`.

## Using a path on the robot

Every exported point is one `TrajectoryPoint`:

| field | unit / meaning |
|---|---|
| `pos.x`, `pos.y` | in |
| `theta` | rad, counter-clockwise from +x: the direction the robot **faces** (path direction + π when reversing) |
| `velocity` | in/s, **negative while reversing** |
| `omega` | rad/s, turn rate (`velocity × curvature`) |
| `curvature` | 1/in, in the robot's frame (positive = turning left) |
| `timestamp` | s since the start of the path |

**`.bin` (load from the SD card)**

```cpp
#include "PRISM/auton/traj_loader.h"
#include "PRISM/auton/traj_follower.h"

std::vector<TrajectoryPoint> path = load_trajectory("/usd/red_auton.bin");  // empty if missing or invalid
TrajectoryFollower follower;
follower.start_following(path);
```

File layout, little-endian: `"PRTJ"`, `uint32` version (2), `uint32` point count, then 7 × `float32` per point in the order above. `load_trajectory` returns an empty vector for a file with the wrong magic, a wrong version, or a truncated file.

**`.hpp` (compiled into the program, no SD card)**

```cpp
#include "paths/red_auton.hpp"   // defines RED_AUTON

follower.start_following(std::vector<TrajectoryPoint>(RED_AUTON.begin(), RED_AUTON.end()));
```

The header includes `PRISM/auton/traj_loader.h` for the `TrajectoryPoint` type and defines a `constexpr std::array<TrajectoryPoint, N>`. The array name comes from the file name: `red_auton.hpp` becomes `RED_AUTON`, other characters become `_`, and names starting with a digit get a `PATH_` prefix.

> **Firmware compatibility.** These formats need the version-2 `traj_loader.h` / `traj_loader.cpp`, with the `theta`, `omega` and `curvature` fields, in the PRISM template. The follower must also handle negative velocity on reversed segments. For use outside the PRISM template, `export_trajectory_header(..., standalone=True)` writes a header that defines its own `Point`/`TrajectoryPoint`.

## How it works

1. **Spline.** Waypoints are joined by cubic Hermite segments using each waypoint's heading as the tangent, so heading is smooth through every waypoint. Automatic headings follow the Catmull-Rom rule (`½·(next − previous)`), flipped on reversed segments. That flip is what turns a direction change into a cusp.
2. **Sampling.** Each segment is resampled at equal distance along the curve (0.5 in by default), so waypoints are exact samples and point density doesn't depend on how long the handles are. Heading and signed curvature come from the spline's derivatives:

   ```
   κ = (x′y″ − y′x″) / (x′² + y′²)^(3/2)      (positive = turning left)
   ```
3. **Speed limits.** Each point's top speed is the smallest of: max speed; the turning limit `sqrt(a_lat / |κ|)`; the outer-wheel limit `v_max / (1 + |κ|·W/2)` for track width `W`; and the segment's cap. Speed is zero at the start, the end and every direction change.
4. **Acceleration.** A forward pass accelerates as fast as `a_max` allows up to those limits, and a backward pass makes sure the robot can always slow down in time.
5. **Timing.** The time between points assumes constant acceleration (`dt = 2d / (v₀ + v₁)`). Turn rate is `ω = v·κ`.

## Project structure

```
path-planner/
├── main.py              # starts the app
├── fields/              # built-in field images + fields.json (names, real-world sizes)
├── spline/              # Hermite math, arc-length sampling, curvature
├── profiler/            # robot config, speed limits + accel passes, TrajectoryPoint
├── exporter/            # .bin, .hpp and .path.json read/write
├── planner/             # the editing model: waypoints, undo/redo, files, stats (no GUI code)
├── qt_ui/               # the PySide6 window, field view, speed graph, sidebars, themes
├── tests/               # pytest; tests/qt drives the real UI offscreen
└── docs/                # screenshots
```

## Development

```bash
python -m pytest                                        # all tests (the Qt ones run offscreen)
python -m pytest tests/test_editor.py -k undo           # a subset
```

Set `PRISM_FIRMWARE_ROOT` to the PRISM template checkout to also compile the exported headers and the template's `traj_loader.cpp`, and load a planner-exported `.bin` with it (needs g++ or clang++):

```bash
PRISM_FIRMWARE_ROOT="../../template/Prism Template" python -m pytest
```

New features are written test-first. See `CLAUDE.md` for the architecture notes.

## Credits

Built for [PRISM](https://prismrobotics.org), a VEX U Robotics Competition team. The built-in field images come from the [path.jerryio](https://github.com/Jerrylum/path.jerryio) project.
