# Bug Fix & Improvement Plan (branch `bugfix-review`)

Context: tank drive; the firmware is PRISM's own template (PID, LQR, Ramsete, possibly pure pursuit). The firmware's `traj_loader.h` defines `TrajectoryPoint { Point pos; float velocity; float timestamp; }` with **no include guard macro**, and `Point` comes from `PRISM/utils/math_utils.h`.

## Part 1: Bugs

### Critical: broken output
1. **Exported `.hpp` never compiles.** `header_exporter.py:36` emits `{{ x, y, v, t }}`, so all four floats initialize `Point pos`, which g++ rejects with `too many initializers for 'Point'`. Fix: emit `{ { x, y }, v, t }`.
   I verified this with g++.
2. **Invalid C++ identifiers from filenames.** `2nd-auton.hpp` produces `2ND_AUTON` / `#ifndef 2ND_AUTON_HPP`, which fails to compile. Characters like `.`, `(` and `&` also get through. Fix: replace anything that isn't `[A-Za-z0-9_]` with `_`, and add a prefix such as `PATH_` when the name starts with a digit.
3. **Type clash with the firmware.** The inline `TrajectoryPoint` is guarded by `TRAJECTORY_POINT_DEFINED`, but `traj_loader.h` doesn't set that macro. Any translation unit that includes both gets a redefinition error. The inline `Point` will also collide with `math_utils.h`'s `Point`. Fix: by default, `#include "PRISM/auton/traj_loader.h"` and drop the inline structs. Keep the self-contained mode behind an option.
4. **`.bin` byte order and size are platform-native.** `struct.pack('i' / '4f')` uses native layout. Fix: use `'<i'` / `'<4f'` explicitly so the file matches the V5 Cortex-A9, which is little-endian with a 32-bit int.

### UI correctness
5. **Manual tangents on endpoints get overwritten.** `compute_tangents` (`app.py:32-36`) always resets the first and last tangents, so APPLY on an endpoint does nothing. Fix: respect `manual_tangent` there too.
6. **APPLY crashes on bad input.** `float()` on empty or non-numeric text raises inside the Tk callback. Fix: validate the input and show an error.
7. **`tk.filedialog` only works by accident.** `import tkinter as tk` doesn't load `filedialog`; it works only because matplotlib's Tk backend happens to import it. Fix: `from tkinter import filedialog`.
8. **`draw_all` keeps a stale `spline_line`.** It isn't reset to `None` after `remove()`, so a second `remove()` raises as soon as a path can drop below 2 points, which deleting waypoints will allow. Fix: reset the reference to `None`.
9. **Every mouse button adds a waypoint**, including right- and middle-click. Fix: check `event.button` (left adds or drags, right deletes; see improvements).
10. **No visual selection state.** It isn't obvious which waypoint the panel is editing. Highlight the selected waypoint.

### Algorithm / numerical
11. **The profile ignores path direction and drivetrain.** There is no heading or angular velocity. A single `a_max` is used for both lateral and longitudinal acceleration, and there is no limit on wheel speed. For tank drive, `v_wheel = v·(1 ± κ·W/2)` can exceed `v_max` on tight turns. Fix: cap `v ≤ v_max / (1 + |κ|·W/2)` using track width W.
12. **Sampling is uniform in t, not arc length.** Point density varies with tangent magnitude and segment length, so Menger curvature gets noisy on short segments, which jitters the velocity ceiling. Fix: resample by arc length (for example every 0.5 in) before profiling.
13. **Inconsistent tangent scale.** Endpoints use the full chord, while interior points use half of the neighbor span. This changes how a curve looks depending on where a point sits. Fix: use the same scale for both, or make tension a setting.
14. **`compute_timestamps` adds 0 s when the average speed is 0** but the distance is nonzero. It isn't reached today, but it will be once v_min or stops are added. Fix: use `t = 2d/(v0+v1)` with a guard that falls back to an accel-based time.
15. **`np.cross` on 2-D vectors is deprecated in NumPy 2.x.** Fix: compute the scalar cross product by hand.

### Repo / tooling
16. `requirements.txt` is UTF-16, so pip on other machines may fail to read it. Re-save it as UTF-8 and add `pytest`.
17. `ui/__pycache__/*.pyc` is still tracked. Run `git rm --cached` on it.
18. `tests/test_exporter.py` writes `test.bin` into the repo directory and only checks x. Fix: use `tmp_path`, check all four fields, and add tests for the header exporter (including a g++ syntax check when g++ is available).
19. The README says Python 3.10+, but the `.pyc` is from 3.8 and the local Python is 3.14. Pick one supported version and pin numpy/matplotlib versions that work with it. numpy 1.24.4 has no wheels for 3.13+.

## Part 2: Improvements (in priority order)

### A. Firmware-ready trajectory output (needed for Ramsete/LQR)
- Extend each point to `x, y, θ, v, ω, κ, t`. The heading comes from the spline derivative (`cubic_hermite_1d_derivative` exists but isn't used), and `ω = v·κ` uses *signed* curvature.
- Version the `.bin` format with a magic number, a version, the point count and the field layout, so the firmware can reject stale files.
- Coordinate this change with `traj_loader.h`. I'd need read access to the firmware repo.

### B. Editable robot / profile settings
- UI fields for v_max, a_max (longitudinal), a_lat_max, track width and sample spacing.
- Save these as a per-robot JSON config that the app loads at startup.

### C. Waypoint editing
- Right-click to delete; shift-click a segment to insert a point between two waypoints.
- Undo/redo using snapshots of the waypoint list.
- Drag a tangent handle (an arrow at the selected waypoint) instead of typing dx/dy, and add a "reset to auto" button.
- Snap to grid with a modifier key.

### D. Save / load projects
- A `.path.json` file with waypoints, tangents, manual flags, settings and a format version.
- Recent files, plus a prompt about unsaved changes on exit.

### E. Profile visualization
- Color the spline by velocity, with a colorbar.
- Velocity-vs-time and velocity-vs-distance plots in a lower panel.
- Show total path time and length.
- Optional "playback" that animates the robot along the path.

### F. Field realism
- Optional field image background (VURC field PNG) at 144×144.
- Draw the robot footprint at the start and end, and optionally along the path.
- Reversed segments for driving backwards (negative v and flipped heading).
- Per-segment speed caps, stop points, and event markers such as "intake on at waypoint 3", exported as markers.

## Status
- Done: bugs 1–12, 14–19 and improvement A. The firmware `traj_loader.h`/`.cpp` were updated locally in the template and not committed.
- Bug 13 was a false alarm. Catmull-Rom's `0.5·(next − prev)` has the same scale as the endpoint chord.
- Found in the firmware for later: `TrajectoryFollower::get_reference()` compares `timestamp` (seconds) with `pros::millis()` (ms), and does a linear scan with no interpolation.

## Suggested order
1. Bugs 1–4, plus tests (the export becomes usable).
2. Bugs 5–10, plus the repo cleanup in 16–19.
3. Improvement A together with bugs 11–15, since both change the profiler. Needs the firmware repo.
4. B → C → D → E → F.
