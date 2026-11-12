"""Toolkit-free path editing model.

The UI layer (Qt) owns widgets and dialogs; everything else - waypoints, selection,
tangents, undo/redo, segment options, files, robot config, trajectory and stats -
lives here so it can be tested without a GUI.
"""
import math
import os
import time

from exporter.path_file import EXTENSION, load_path, save_path
from planner.waypoint import Waypoint
from profiler.config import RobotConfig, load_config, save_config
from profiler.trajectory import generate_trajectory, state_at
from spline.arclength import segment_args
from spline.hermite import sample_hermite_2d

_UNSET = object()


class Editor:
    PICK_RADIUS = 5.0      # in: distance that grabs a waypoint or tangent handle
    INSERT_RADIUS = 8.0    # in: max distance from the path for insert
    SNAP = 1.0             # in: snap grid
    HANDLE_SCALE = 1 / 3   # handle drawn at p + m/3 (the equivalent Bezier control point)
    MAX_HISTORY = 200

    def __init__(self, config=None, config_path=None):
        self.waypoints = []
        self.selected = None
        self.undo_stack = []
        self.redo_stack = []
        self.file_path = None
        self.config_path = config_path
        self.config_error = None
        if config is not None:
            self.config = config
        elif config_path:
            self.config, self.config_error = load_config(config_path)
        else:
            self.config = RobotConfig()
        self._listeners = []
        self._drag = None            # (waypoint, mode) while dragging
        self._drag_snapshot = None
        self._trajectory = None      # cache, cleared on every path change
        self._saved_data = self._data()

    # ---------- change notification ----------

    def subscribe(self, fn):
        """fn(kind) is called after changes. kind: 'path', 'selection', 'config' or 'file'."""
        self._listeners.append(fn)

    def _emit(self, kind):
        if kind in ('path', 'config'):
            self._trajectory = None
        for fn in list(self._listeners):
            fn(kind)

    # ---------- geometry helpers ----------

    def snap(self, x, y):
        return round(x / self.SNAP) * self.SNAP, round(y / self.SNAP) * self.SNAP

    def handle_pos(self, w):
        return w.x + w.dx * self.HANDLE_SCALE, w.y + w.dy * self.HANDLE_SCALE

    def signs(self):
        """+1 / -1 per segment (segment i leaves waypoint i; -1 = driven backwards)."""
        return [-1 if w.reversed else 1 for w in self.waypoints[:-1]]

    def spline_inputs(self):
        pts = [(w.x, w.y) for w in self.waypoints]
        tangents = [(w.dx, w.dy) for w in self.waypoints]
        return pts, tangents, self.signs()

    def preview_path(self, per_segment=30):
        """Sampled spline points for drawing (no timing)."""
        if len(self.waypoints) < 2:
            return []
        pts, tangents, signs = self.spline_inputs()
        path = []
        for i in range(len(pts) - 1):
            seg = sample_hermite_2d(*segment_args(pts, tangents, i, signs), per_segment)
            path += seg if i == 0 else seg[1:]
        return path

    def hit_test(self, x, y):
        """('point' | 'handle', waypoint) under (x, y), or None. Nearest wins."""
        candidates = [(math.hypot(w.x - x, w.y - y), 'point', w) for w in self.waypoints]
        if self.selected is not None:
            hx, hy = self.handle_pos(self.selected)
            candidates.append((math.hypot(hx - x, hy - y), 'handle', self.selected))
        candidates = [c for c in candidates if c[0] <= self.PICK_RADIUS]
        if not candidates:
            return None
        _, mode, w = min(candidates, key=lambda c: c[0])
        return mode, w

    def nearest_segment(self, x, y):
        """(segment index, distance) of the path segment closest to (x, y)."""
        best = (None, float('inf'))
        if len(self.waypoints) < 2:
            return best
        pts, tangents, signs = self.spline_inputs()
        for i in range(len(pts) - 1):
            for px, py in sample_hermite_2d(*segment_args(pts, tangents, i, signs), 50):
                d = math.hypot(px - x, py - y)
                if d < best[1]:
                    best = (i, d)
        return best

    def compute_tangents(self):
        """Auto headings: Catmull-Rom on the path, flipped to face backwards on reversed segments."""
        wps = self.waypoints
        if len(wps) < 2:
            return
        signs = self.signs()
        for i, w in enumerate(wps):
            if w.manual_tangent:
                continue
            if i == 0:
                s = signs[0]
                w.dx, w.dy = s * (wps[1].x - w.x), s * (wps[1].y - w.y)
            elif i == len(wps) - 1:
                s = signs[-1]
                w.dx, w.dy = s * (w.x - wps[-2].x), s * (w.y - wps[-2].y)
            else:
                s_in, s_out = signs[i - 1], signs[i]
                prev, nxt = wps[i - 1], wps[i + 1]
                w.dx = 0.5 * (s_in * (w.x - prev.x) + s_out * (nxt.x - w.x))
                w.dy = 0.5 * (s_in * (w.y - prev.y) + s_out * (nxt.y - w.y))

    # ---------- history ----------

    def _data(self):
        return [w.as_tuple() for w in self.waypoints]

    def _snapshot(self):
        sel = next((i for i, w in enumerate(self.waypoints) if w is self.selected), None)
        return self._data(), sel

    def _restore(self, snapshot):
        data, sel = snapshot
        self.waypoints = [Waypoint.from_tuple(t) for t in data]
        self.selected = self.waypoints[sel] if sel is not None else None
        self._drag = self._drag_snapshot = None
        self._emit('path')
        self._emit('selection')

    def _push_history(self, snapshot=None):
        self.undo_stack.append(snapshot if snapshot is not None else self._snapshot())
        del self.undo_stack[:-self.MAX_HISTORY]
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self._snapshot())
            self._restore(self.undo_stack.pop())

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self._snapshot())
            self._restore(self.redo_stack.pop())

    def _changed(self):
        self.compute_tangents()
        self._emit('path')

    # ---------- edits ----------

    def select(self, w):
        if w is not self.selected:
            self.selected = w
            self._emit('selection')

    def add_waypoint(self, x, y, snap=False):
        return self._insert_at(len(self.waypoints), x, y, snap)

    def insert_waypoint(self, x, y, snap=False):
        """Insert into the nearest segment if (x, y) is within INSERT_RADIUS of the path."""
        seg, dist = self.nearest_segment(x, y)
        if seg is None or dist > self.INSERT_RADIUS:
            return None
        return self._insert_at(seg + 1, x, y, snap)

    def _insert_at(self, index, x, y, snap):
        if snap:
            x, y = self.snap(x, y)
        self._push_history()
        w = Waypoint(x, y)
        self.waypoints.insert(index, w)
        self.selected = w
        self._changed()
        self._emit('selection')
        return w

    def delete_waypoint(self, w=None):
        w = w if w is not None else self.selected
        if w is None or not any(w is o for o in self.waypoints):
            return
        self._push_history()
        self.waypoints.remove(w)
        if self.selected is w:
            self.selected = None
            self._emit('selection')
        self._changed()

    def update_waypoint(self, w, x=None, y=None, dx=None, dy=None, reversed=None, v_cap=_UNSET):
        """Apply several field edits as one undo step. Editing dx/dy makes the tangent manual."""
        if v_cap is not _UNSET and v_cap is not None:
            v_cap = float(v_cap)
            if not math.isfinite(v_cap) or v_cap <= 0:
                raise ValueError("segment max speed must be a positive number")
        self._push_history()
        if x is not None:
            w.x = x
        if y is not None:
            w.y = y
        if (dx is not None and dx != w.dx) or (dy is not None and dy != w.dy):
            w.dx = w.dx if dx is None else dx
            w.dy = w.dy if dy is None else dy
            w.manual_tangent = True
        if reversed is not None:
            w.reversed = bool(reversed)
        if v_cap is not _UNSET:
            w.v_cap = v_cap
        self._changed()

    def reset_tangent(self, w=None):
        w = w if w is not None else self.selected
        if w is None or not w.manual_tangent:
            return
        self._push_history()
        w.manual_tangent = False
        self._changed()

    # ---------- dragging ----------

    def begin_drag(self, w, mode):
        """mode: 'point' moves the waypoint, 'handle' edits its tangent."""
        self.select(w)
        self._drag = (w, mode)
        self._drag_snapshot = self._snapshot()  # committed on the first movement

    def drag_to(self, x, y, snap=False):
        if self._drag is None:
            return
        w, mode = self._drag
        if self._drag_snapshot is not None:
            self._push_history(self._drag_snapshot)
            self._drag_snapshot = None
        if mode == 'point':
            w.x, w.y = self.snap(x, y) if snap else (x, y)
        else:
            w.dx = (x - w.x) / self.HANDLE_SCALE
            w.dy = (y - w.y) / self.HANDLE_SCALE
            w.manual_tangent = True
        self._changed()

    def end_drag(self):
        self._drag = self._drag_snapshot = None

    @property
    def dragging(self):
        return self._drag is not None

    # ---------- robot config ----------

    def set_config(self, config):
        """Validate, apply and (if config_path is set) save. Raises ValueError on bad values."""
        config.validate()
        self.config = config
        if self.config_path:
            save_config(config, self.config_path)
        self._emit('config')

    # ---------- trajectory ----------

    @property
    def trajectory(self):
        if self._trajectory is None:
            if len(self.waypoints) < 2:
                self._trajectory = []
            else:
                pts, tangents, _ = self.spline_inputs()
                self._trajectory = generate_trajectory(
                    pts, tangents, self.config,
                    reversed_segments=[w.reversed for w in self.waypoints],
                    speed_caps=[w.v_cap for w in self.waypoints])
        return self._trajectory

    def stats(self):
        traj = self.trajectory
        if len(traj) < 2:
            return None
        return {
            "length": sum(math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(traj, traj[1:])),
            "time": traj[-1].timestamp,
            "peak": max(abs(p.velocity) for p in traj),
        }

    def pose_at(self, t):
        """(x, y, theta, velocity) at time t along the trajectory."""
        return state_at(self.trajectory, t)

    # ---------- files ----------

    def is_dirty(self):
        return self._data() != self._saved_data

    def path_stem(self):
        if not self.file_path:
            return "untitled"
        name = os.path.basename(self.file_path)
        for ext in (EXTENSION, ".json"):
            if name.lower().endswith(ext):
                return name[:-len(ext)]
        return name

    def _mark_saved(self):
        self._saved_data = self._data()
        self._emit('file')

    def _reset_to(self, waypoints):
        self.waypoints = waypoints
        self.selected = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._emit('path')
        self._emit('selection')
        self._mark_saved()

    def new(self):
        self.file_path = None
        self._reset_to([])

    def load(self, path):
        """Open a .path.json. Raises ValueError/OSError without touching the current path."""
        data = load_path(path)
        self.file_path = path
        self._reset_to([Waypoint(d["x"], d["y"], d["dx"], d["dy"], d["manual_tangent"],
                                 d["reversed"], d["v_cap"]) for d in data])

    def save(self, path=None):
        """Save to path (or the current file). Adds .path.json if no .json extension. Raises OSError."""
        path = path or self.file_path
        if not path:
            raise ValueError("no file path")
        if not path.lower().endswith(".json"):
            path += EXTENSION
        save_path(path, self.waypoints)
        self.file_path = path
        self._mark_saved()


class Playback:
    """Real-time playback clock over an Editor's trajectory."""

    def __init__(self, editor):
        self.editor = editor
        self.start_time = None

    @property
    def playing(self):
        return self.start_time is not None

    def start(self, now=None):
        if len(self.editor.trajectory) >= 2:
            self.start_time = time.monotonic() if now is None else now

    def stop(self):
        self.start_time = None

    def time(self, now=None):
        """Seconds into the path, or None (and stopped) once past the end."""
        if self.start_time is None:
            return None
        t = (time.monotonic() if now is None else now) - self.start_time
        if not self.editor.trajectory or t > self.editor.trajectory[-1].timestamp:
            self.stop()
            return None
        return t
