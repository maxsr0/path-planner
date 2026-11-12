import math
import os
import tkinter as tk
from tkinter import filedialog, messagebox

from spline.hermite import sample_hermite_path, sample_hermite_2d
from ui.waypoint import Waypoint
from profiler.trajectory import generate_trajectory
from profiler.config import RobotConfig, load_config, save_config
from exporter.binary_exporter import export_trajectory
from exporter.header_exporter import export_trajectory_header
from exporter.path_file import save_path, load_path, EXTENSION


class App:
    # (config attribute, label) for each robot-settings field, in panel order
    SETTINGS_FIELDS = [
        ('v_max', 'max speed (in/s)'),
        ('a_max', 'max accel (in/s²)'),
        ('a_lat_max', 'lateral accel (blank = same)'),
        ('track_width', 'track width (in, 0 = off)'),
        ('spacing', 'point spacing (in)'),
    ]

    def __init__(self, root, fig, ax, canvas, entries, settings_entries=None, stats_var=None, config_path=None):
        self.root = root
        self.ax = ax
        self.canvas = canvas
        self.entries = entries
        self.waypoints = []
        self.dot_artists = []
        self.spline_line = None
        self.selected_waypoint = None
        self.is_dragging = False
        self.drag_mode = None          # None | 'point' | 'handle'
        self._drag_snapshot = None
        self.handle_artists = []
        self.undo_stack = []
        self.redo_stack = []
        self.settings_entries = settings_entries or {}
        self.stats_var = stats_var
        self.config_path = config_path
        self.config = RobotConfig()
        if config_path:
            self.config, error = load_config(config_path)
            if error:
                messagebox.showwarning("Robot settings", error)
        self.fill_settings()
        self.file_path = None
        self._saved_data = self._snapshot()[0]
        self.update_title()

    PICK_RADIUS = 5.0      # in: click distance that grabs a waypoint or tangent handle
    INSERT_RADIUS = 8.0    # in: max distance from the path for shift-click insert
    SNAP = 1.0             # in: grid used while ctrl is held
    HANDLE_SCALE = 1 / 3   # handle drawn at p + m/3 (the equivalent Bezier control point)
    MAX_HISTORY = 200

    # ---------- helpers ----------

    @staticmethod
    def check_distance(click_x, click_y, w, r=PICK_RADIUS):
        return (w.x - click_x) ** 2 + (w.y - click_y) ** 2 <= r ** 2

    @staticmethod
    def _modifiers(event):
        """(shift, ctrl) held during a matplotlib mouse event."""
        parts = set((getattr(event, 'key', None) or '').lower().replace('+', ' ').split())
        return 'shift' in parts, bool(parts & {'control', 'ctrl'})

    def _point(self, event):
        """Event position, snapped to the SNAP grid while ctrl is held."""
        x, y = event.xdata, event.ydata
        if self._modifiers(event)[1]:
            x, y = round(x / self.SNAP) * self.SNAP, round(y / self.SNAP) * self.SNAP
        return x, y

    def _handle_pos(self, w):
        return w.x + w.dx * self.HANDLE_SCALE, w.y + w.dy * self.HANDLE_SCALE

    def _nearest_segment(self, x, y):
        """(segment index, distance) of the path segment closest to (x, y)."""
        best = (None, float('inf'))
        for i, (a, b) in enumerate(zip(self.waypoints, self.waypoints[1:])):
            for px, py in sample_hermite_2d((a.x, a.y), (b.x, b.y), (a.dx, a.dy), (b.dx, b.dy), 50):
                d = math.hypot(px - x, py - y)
                if d < best[1]:
                    best = (i, d)
        return best

    def compute_tangents(self):
        for i in range(1, len(self.waypoints) - 1):
            if not self.waypoints[i].manual_tangent:
                self.waypoints[i].auto_tangent(self.waypoints[i - 1], self.waypoints[i + 1])

        if len(self.waypoints) >= 2:
            first, last = self.waypoints[0], self.waypoints[-1]
            if not first.manual_tangent:
                first.dx = self.waypoints[1].x - first.x
                first.dy = self.waypoints[1].y - first.y
            if not last.manual_tangent:
                last.dx = last.x - self.waypoints[-2].x
                last.dy = last.y - self.waypoints[-2].y

    # ---------- undo / redo ----------

    def _snapshot(self):
        sel = next((i for i, w in enumerate(self.waypoints) if w is self.selected_waypoint), None)
        return [(w.x, w.y, w.dx, w.dy, w.manual_tangent) for w in self.waypoints], sel

    def _restore(self, snapshot):
        data, sel = snapshot
        self.waypoints = []
        for x, y, dx, dy, manual in data:
            w = Waypoint(x, y, dx, dy)
            w.manual_tangent = manual
            self.waypoints.append(w)
        self.selected_waypoint = self.waypoints[sel] if sel is not None else None
        self._end_drag()
        self.update_panel()
        self.draw_all()

    def push_history(self, snapshot=None):
        """Record the current state (call before every edit)."""
        self.undo_stack.append(snapshot if snapshot is not None else self._snapshot())
        del self.undo_stack[:-self.MAX_HISTORY]
        self.redo_stack.clear()

    def undo(self, *_):
        if self.undo_stack:
            self.redo_stack.append(self._snapshot())
            self._restore(self.undo_stack.pop())

    def redo(self, *_):
        if self.redo_stack:
            self.undo_stack.append(self._snapshot())
            self._restore(self.redo_stack.pop())

    # ---------- drawing ----------

    def draw_spline(self, wps):
        if len(wps) < 2:
            return

        points = [(w.x, w.y) for w in wps]
        tangents = [(w.dx, w.dy) for w in wps]

        path = sample_hermite_path(points, tangents, 20)
        xs, ys = zip(*path)

        self.spline_line = self.ax.plot(xs, ys, '-', color='white')[0]

    def draw_waypoint(self, w):
        if w is self.selected_waypoint:
            dot = self.ax.plot(w.x, w.y, 'o', color='#4fc', markersize=9, zorder=3)[0]
        else:
            dot = self.ax.plot(w.x, w.y, 'o', color='white', zorder=3)[0]
        self.dot_artists.append(dot)

    def draw_handle(self, w):
        hx, hy = self._handle_pos(w)
        color = '#4fc' if w.manual_tangent else '#888'
        self.handle_artists.append(self.ax.plot([w.x, hx], [w.y, hy], '-', color=color, lw=1, zorder=4)[0])
        self.handle_artists.append(self.ax.plot(hx, hy, 's', color=color, markersize=6, zorder=4)[0])

    def draw_all(self):
        if self.spline_line is not None:
            self.spline_line.remove()
            self.spline_line = None

        for artist in self.dot_artists + self.handle_artists:
            artist.remove()
        self.dot_artists.clear()
        self.handle_artists.clear()

        for w in self.waypoints:
            self.draw_waypoint(w)
        if self.selected_waypoint is not None:
            self.draw_handle(self.selected_waypoint)

        self.draw_spline(self.waypoints)
        self.update_stats()
        self.update_title()

        self.canvas.draw()

    # ---------- mouse / keys ----------

    def _start_drag(self, mode):
        self.drag_mode = mode
        self.is_dragging = True
        self._drag_snapshot = self._snapshot()  # committed to history on first movement

    def _end_drag(self):
        self.drag_mode = None
        self.is_dragging = False
        self._drag_snapshot = None

    def on_click(self, event):
        if event.xdata is None or event.ydata is None:
            return
        x, y = event.xdata, event.ydata

        if event.button == 3:  # right-click deletes
            hit = next((w for w in self.waypoints if self.check_distance(x, y, w)), None)
            if hit is not None:
                self.delete_waypoint(hit)
            return
        if event.button != 1:
            return

        # Grab whichever is closer: a waypoint or the selected waypoint's tangent handle.
        candidates = [(math.hypot(w.x - x, w.y - y), 'point', w) for w in self.waypoints]
        if self.selected_waypoint is not None:
            hx, hy = self._handle_pos(self.selected_waypoint)
            candidates.append((math.hypot(hx - x, hy - y), 'handle', self.selected_waypoint))
        candidates = [c for c in candidates if c[0] <= self.PICK_RADIUS]
        if candidates:
            _, mode, w = min(candidates, key=lambda c: c[0])
            self.selected_waypoint = w
            self._start_drag(mode)
            self.update_panel()
            self.draw_all()
            return

        shift, _ = self._modifiers(event)
        if shift and len(self.waypoints) >= 2:
            seg, dist = self._nearest_segment(x, y)
            if dist > self.INSERT_RADIUS:
                return
            index = seg + 1
        else:
            index = len(self.waypoints)

        self.push_history()
        w = Waypoint(*self._point(event))
        self.waypoints.insert(index, w)
        self.selected_waypoint = w
        self.compute_tangents()
        self.update_panel()
        self.draw_all()

    def on_drag(self, event):
        w = self.selected_waypoint
        if self.drag_mode is None or w is None:
            return
        if event.xdata is None or event.ydata is None:
            return

        if self._drag_snapshot is not None:
            self.push_history(self._drag_snapshot)
            self._drag_snapshot = None

        if self.drag_mode == 'point':
            w.x, w.y = self._point(event)
        else:  # tangent handle
            w.dx = (event.xdata - w.x) / self.HANDLE_SCALE
            w.dy = (event.ydata - w.y) / self.HANDLE_SCALE
            w.manual_tangent = True

        self.compute_tangents()
        self.update_panel()
        self.draw_all()

    def on_release(self, event):
        self._end_drag()

    def on_key(self, event):
        """matplotlib key_press_event on the field canvas."""
        if event.key in ('delete', 'backspace'):
            self.delete_waypoint()
        elif event.key == 'escape':
            self.selected_waypoint = None
            self.update_panel()
            self.draw_all()

    # ---------- edits ----------

    def delete_waypoint(self, w=None):
        w = w if w is not None else self.selected_waypoint
        if w is None or not any(w is o for o in self.waypoints):
            return
        self.push_history()
        self.waypoints.remove(w)
        if self.selected_waypoint is w:
            self.selected_waypoint = None
        self.compute_tangents()
        self.update_panel()
        self.draw_all()

    def reset_tangent(self):
        w = self.selected_waypoint
        if w is None or not w.manual_tangent:
            return
        self.push_history()
        w.manual_tangent = False
        self.compute_tangents()
        self.update_panel()
        self.draw_all()

    def on_apply(self):
        w = self.selected_waypoint
        if w is None:
            return

        try:
            values = {k: float(self.entries[k].get()) for k in ('x', 'y', 'dx', 'dy')}
        except ValueError:
            messagebox.showerror("Invalid input", "x, y, dx and dy must all be numbers.")
            return

        self.push_history()
        # Only freeze the tangent if it was actually edited (the panel shows values rounded to 3 places).
        if values['dx'] != round(w.dx, 3) or values['dy'] != round(w.dy, 3):
            w.dx, w.dy = values['dx'], values['dy']
            w.manual_tangent = True
        w.x, w.y = values['x'], values['y']

        self.compute_tangents()
        self.update_panel()
        self.draw_all()

    def update_panel(self):
        w = self.selected_waypoint
        for key in ('x', 'y', 'dx', 'dy'):
            self.entries[key].delete(0, tk.END)
            if w is not None:
                self.entries[key].insert(0, round(getattr(w, key), 3))

    # ---------- path files ----------

    def is_dirty(self):
        """True if the waypoints differ from the last saved/opened state."""
        return self._snapshot()[0] != self._saved_data

    def _mark_saved(self):
        self._saved_data = self._snapshot()[0]
        self.update_title()

    def _path_stem(self):
        if not self.file_path:
            return "untitled"
        name = os.path.basename(self.file_path)
        for ext in (EXTENSION, ".json"):
            if name.lower().endswith(ext):
                return name[:-len(ext)]
        return name

    def update_title(self):
        if self.root is None:
            return
        star = "*" if self.is_dirty() else ""
        self.root.title(f"{star}{self._path_stem()} - PRISM Path Planner")

    def confirm_discard(self):
        """Ask to save unsaved changes. Returns False if the user cancelled."""
        if not self.is_dirty():
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", f"Save changes to {self._path_stem()}?")
        if answer is None:
            return False
        if answer:
            return self.save()
        return True

    def _load_state(self, data):
        self._restore(([(w["x"], w["y"], w["dx"], w["dy"], w["manual_tangent"]) for w in data], None))
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._mark_saved()

    def new_path(self, *_):
        if not self.confirm_discard():
            return
        self.file_path = None
        self._load_state([])

    def open_path(self, *_, file_path=None):
        if not self.confirm_discard():
            return
        if file_path is None:
            file_path = filedialog.askopenfilename(
                filetypes=[("PRISM path", "*" + EXTENSION), ("JSON", "*.json"), ("All files", "*.*")],
                title="Open path")
        if not file_path:
            return
        try:
            data = load_path(file_path)
        except (OSError, ValueError) as e:
            messagebox.showerror("Open path", f"Could not open {os.path.basename(file_path)}: {e}")
            return
        self.file_path = file_path
        self._load_state(data)

    def save(self, *_):
        """Save to the current file (asks for a name the first time). Returns True on success."""
        if not self.file_path:
            return self.save_as()
        try:
            save_path(self.file_path, self.waypoints)
        except OSError as e:
            messagebox.showerror("Save path", f"Could not save {self.file_path}: {e}")
            return False
        self._mark_saved()
        return True

    def save_as(self, *_):
        file_path = filedialog.asksaveasfilename(
            filetypes=[("PRISM path", "*" + EXTENSION)],
            initialfile=self._path_stem() + EXTENSION,
            title="Save path as")
        if not file_path:
            return False
        if not file_path.lower().endswith(".json"):
            file_path += EXTENSION
        self.file_path = file_path
        return self.save()

    def on_quit(self, *_):
        if self.confirm_discard() and self.root is not None:
            self.root.quit()

    def _generate_trajectory(self):
        pts = [(w.x, w.y) for w in self.waypoints]
        tangents = [(w.dx, w.dy) for w in self.waypoints]
        return generate_trajectory(pts, tangents, self.config)

    def on_export(self):
        if len(self.waypoints) < 2:
            return
        traj = self._generate_trajectory()
        file_path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[("Binary trajectory", "*.bin")],
            initialfile=self._path_stem() + ".bin",
            title="Export .bin (SD card)"
        )
        if file_path:
            export_trajectory(traj, file_path)

    def on_export_header(self):
        if len(self.waypoints) < 2:
            return
        traj = self._generate_trajectory()
        file_path = filedialog.asksaveasfilename(
            defaultextension=".hpp",
            filetypes=[("C++ header", "*.hpp")],
            initialfile=self._path_stem() + ".hpp",
            title="Export .hpp (embed in firmware)"
        )
        if file_path:
            export_trajectory_header(traj, file_path)

    def fill_settings(self):
        for name, entry in self.settings_entries.items():
            value = getattr(self.config, name)
            entry.delete(0, tk.END)
            entry.insert(0, "" if value is None else f"{value:g}")

    def read_settings(self):
        """Parse the settings entries into a validated RobotConfig (raises ValueError)."""
        labels = dict(self.SETTINGS_FIELDS)
        values = {}
        for name, entry in self.settings_entries.items():
            text = entry.get().strip()
            if name == 'a_lat_max' and text == "":
                values[name] = None
                continue
            try:
                values[name] = float(text)
            except ValueError:
                raise ValueError(f"{labels[name]}: '{text}' is not a number")
        return RobotConfig(**values).validate()

    def on_apply_settings(self):
        try:
            self.config = self.read_settings()
        except ValueError as e:
            messagebox.showerror("Invalid robot settings", str(e))
            return

        if self.config_path:
            try:
                save_config(self.config, self.config_path)
            except OSError as e:
                messagebox.showerror("Robot settings", f"Could not save {self.config_path}: {e}")
        self.fill_settings()
        self.draw_all()

    def update_stats(self):
        if self.stats_var is None:
            return
        if len(self.waypoints) < 2:
            self.stats_var.set("place 2+ waypoints")
            return
        traj = self._generate_trajectory()
        length = sum(math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(traj, traj[1:]))
        peak = max(p.velocity for p in traj)
        self.stats_var.set(f"length  {length:.1f} in\n"
                           f"time    {traj[-1].timestamp:.2f} s\n"
                           f"peak v  {peak:.1f} in/s")
