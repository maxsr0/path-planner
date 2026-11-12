import math
import os
import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from spline.hermite import sample_hermite_2d
from spline.arclength import segment_args
from ui.waypoint import Waypoint
from profiler.trajectory import generate_trajectory
from profiler.config import RobotConfig, load_config, save_config
from exporter.binary_exporter import export_trajectory
from exporter.header_exporter import export_trajectory_header
from exporter.path_file import save_path, load_path, EXTENSION
from ui.velocity_view import VelocityView
from ui.fields import FIELDS_DIR, NO_FIELD, DEFAULT_FIELD, load_builtin_fields, custom_field


class App:
    # (config attribute, label) for each robot-settings field, in panel order
    SETTINGS_FIELDS = [
        ('v_max', 'max speed (in/s)'),
        ('a_max', 'max accel (in/s²)'),
        ('a_lat_max', 'lateral accel (blank = same)'),
        ('track_width', 'track width (in, 0 = off)'),
        ('spacing', 'point spacing (in)'),
    ]

    PLAY_FRAME_MS = 30
    FIELD_IMAGE_PX = 640   # field images are resized to at most this many pixels per side

    def __init__(self, root, fig, ax, canvas, entries, settings_entries=None, stats_var=None, config_path=None,
                 profile_ax=None, prefs_path=None, fields_dir=FIELDS_DIR):
        self.root = root
        self.profile_ax = profile_ax
        self.view = VelocityView(ax, profile_ax) if profile_ax is not None else None
        self.trajectory = []
        self.play_start = None    # time.monotonic() when playback started; None = stopped
        self._play_job = None
        self.on_play_state = None  # optional callback(playing: bool) for the PLAY button
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
        self.prefs_path = prefs_path
        self.fields_dir = fields_dir
        self.field_image = None       # (path, AxesImage) when a background image is shown
        self.field_name = NO_FIELD
        self.on_field_change = None   # optional callback(name) for the field picker
        self._initial_field()
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
        pts, tangents, signs = self._spline_inputs()
        for i in range(len(self.waypoints) - 1):
            for px, py in sample_hermite_2d(*segment_args(pts, tangents, i, signs), 50):
                d = math.hypot(px - x, py - y)
                if d < best[1]:
                    best = (i, d)
        return best

    def _signs(self):
        """+1 / -1 per segment (segment i leaves waypoint i; -1 = driven backwards)."""
        return [-1 if w.reversed else 1 for w in self.waypoints[:-1]]

    def _spline_inputs(self):
        pts = [(w.x, w.y) for w in self.waypoints]
        tangents = [(w.dx, w.dy) for w in self.waypoints]
        return pts, tangents, self._signs()

    def compute_tangents(self):
        """Auto headings: Catmull-Rom on the path, flipped to face backwards on reversed segments.

        At a waypoint where the direction changes, the heading averages the incoming and
        outgoing facing directions, which puts a cusp (a stop-and-reverse) there.
        """
        wps = self.waypoints
        if len(wps) < 2:
            return
        signs = self._signs()
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

    # ---------- undo / redo ----------

    def _snapshot(self):
        sel = next((i for i, w in enumerate(self.waypoints) if w is self.selected_waypoint), None)
        return [w.as_tuple() for w in self.waypoints], sel

    def _restore(self, snapshot):
        data, sel = snapshot
        self.waypoints = [Waypoint.from_tuple(t) for t in data]
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

        pts, tangents, signs = self._spline_inputs()
        path = []
        for i in range(len(wps) - 1):
            seg = sample_hermite_2d(*segment_args(pts, tangents, i, signs), 20)
            path += seg if i == 0 else seg[1:]
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

        self.trajectory = self._generate_trajectory() if len(self.waypoints) >= 2 else []
        if self.view is not None:
            self.view.update(self.trajectory, self.config.v_max, self.config.track_width)
            if self.play_start is None:
                self.view.set_time(None)
        else:
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
        if getattr(event, 'inaxes', self.ax) is not self.ax:
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
        if self.drag_mode is None and self.view is not None and self.play_start is None:
            inside = self.profile_ax is not None and getattr(event, 'inaxes', None) is self.profile_ax
            self.view.set_time(event.xdata if inside and event.xdata is not None else None)
            self.canvas.draw_idle()
            if inside:
                return
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
        elif event.key == ' ':
            self.toggle_play()
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

        cap = None
        if 'cap' in self.entries:
            text = self.entries['cap'].get().strip()
            if text:
                try:
                    cap = float(text)
                except ValueError:
                    cap = -1
                if not math.isfinite(cap) or cap <= 0:
                    messagebox.showerror("Invalid input", "Segment max speed must be a positive number (blank = no cap).")
                    return

        self.push_history()
        if 'cap' in self.entries:
            w.v_cap = cap
        if 'reverse' in self.entries:
            w.reversed = bool(self.entries['reverse'].get())
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
        if 'cap' in self.entries:
            self.entries['cap'].delete(0, tk.END)
            if w is not None and w.v_cap is not None:
                self.entries['cap'].insert(0, f"{w.v_cap:g}")
        if 'reverse' in self.entries:
            self.entries['reverse'].set(bool(w is not None and w.reversed))

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
        self._restore(([(w["x"], w["y"], w["dx"], w["dy"], w["manual_tangent"], w["reversed"], w["v_cap"])
                        for w in data], None))
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
        return generate_trajectory(pts, tangents, self.config,
                                   reversed_segments=[w.reversed for w in self.waypoints],
                                   speed_caps=[w.v_cap for w in self.waypoints])

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
        traj = self.trajectory
        length = sum(math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(traj, traj[1:]))
        peak = max(abs(p.velocity) for p in traj)  # reversed segments have negative velocity
        self.stats_var.set(f"length  {length:.1f} in\n"
                           f"time    {traj[-1].timestamp:.2f} s\n"
                           f"peak v  {peak:.1f} in/s")

    # ---------- playback ----------

    def toggle_play(self, *_):
        if self.play_start is not None:
            self.stop_play()
        elif self.view is not None and len(self.trajectory) >= 2:
            self.play_start = time.monotonic()
            self._notify_play(True)
            self.play_tick()

    def stop_play(self):
        if self._play_job is not None and self.root is not None:
            self.root.after_cancel(self._play_job)
        self._play_job = None
        self.play_start = None
        self._notify_play(False)
        if self.view is not None:
            self.view.set_time(None)
            self.canvas.draw_idle()

    def _notify_play(self, playing):
        if self.on_play_state is not None:
            self.on_play_state(playing)

    def play_tick(self, now=None):
        """Advance playback to real time (or `now`); stops after the end of the path."""
        if self.play_start is None or self.view is None:
            return
        t = (now if now is not None else time.monotonic()) - self.play_start
        if t > self.view.duration:
            self.stop_play()
            return
        self.view.set_time(t)
        self.canvas.draw_idle()
        if self.root is not None:
            self._play_job = self.root.after(self.PLAY_FRAME_MS, self.play_tick)

    # ---------- field background ----------

    def _load_prefs(self):
        if not self.prefs_path:
            return {}
        try:
            with open(self.prefs_path, encoding='utf-8') as f:
                prefs = json.load(f)
            return prefs if isinstance(prefs, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_prefs(self, **changes):
        if not self.prefs_path:
            return
        prefs = self._load_prefs()
        prefs.update(changes)
        try:
            with open(self.prefs_path, 'w', encoding='utf-8') as f:
                json.dump(prefs, f, indent=2)
        except OSError:
            pass  # preferences are a convenience; never block editing over them

    def _custom_fields(self):
        prefs = self._load_prefs()
        out = []
        for c in prefs.get('custom_fields', []):
            if isinstance(c, dict) and c.get('name') and c.get('path') and os.path.exists(c['path']):
                out.append(custom_field(c['name'], c['path']))
        old = prefs.get('field_image')  # pre-picker preference: a single custom image path
        if isinstance(old, str) and os.path.exists(old) and not any(f.path == old for f in out):
            out.append(custom_field(os.path.splitext(os.path.basename(old))[0], old))
        return out

    def field_options(self):
        """All selectable fields: built-ins first, then user-added images."""
        return load_builtin_fields(self.fields_dir) + self._custom_fields()

    def field_names(self):
        return [NO_FIELD] + [f.name for f in self.field_options()]

    def _initial_field(self):
        prefs = self._load_prefs()
        name = prefs.get('field')
        if name is None and isinstance(prefs.get('field_image'), str):
            name = os.path.splitext(os.path.basename(prefs['field_image']))[0]
        if name is None:
            name = DEFAULT_FIELD
        if not self.select_field(name, remember=False):
            self.select_field(NO_FIELD, remember=False)

    def _show_field(self, preset):
        """Draw the preset's image under the path. Returns success."""
        import numpy as np
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(preset.path) as im:
                im = im.convert('RGBA')
                # The field is only a few hundred pixels on screen; a smaller image keeps
                # every redraw (dragging, playback) fast. 2000 px renders cost ~140 ms/frame.
                im.thumbnail((self.FIELD_IMAGE_PX, self.FIELD_IMAGE_PX), Image.LANCZOS)
                img = np.asarray(im)
        except (OSError, ValueError, UnidentifiedImageError) as e:
            messagebox.showerror("Field image", f"Could not load {os.path.basename(preset.path)}: {e}")
            return False
        self._clear_field_artist()
        artist = self.ax.imshow(img, extent=preset.extent, origin='upper', zorder=1.1,
                                aspect='auto', interpolation='bilinear')
        lo, hi, _, _ = preset.extent
        self.ax.set_xlim(min(0, lo), max(144, hi))
        self.ax.set_ylim(min(0, lo), max(144, hi))
        self.ax.set_aspect('equal')
        self.ax.grid(False)  # the render shows the tiles itself
        self.field_image = (preset.path, artist)
        return True

    def _clear_field_artist(self):
        if self.field_image is not None:
            self.field_image[1].remove()
            self.field_image = None
        self.ax.set_xlim(0, 144)
        self.ax.set_ylim(0, 144)
        self.ax.grid(True)

    def select_field(self, name, remember=True):
        """Show a field by name (NO_FIELD = plain grid). Returns False if it isn't available."""
        if name == NO_FIELD:
            self._clear_field_artist()
        else:
            preset = next((f for f in self.field_options() if f.name == name), None)
            if preset is None or not self._show_field(preset):
                return False
        self.field_name = name
        if remember:
            self._save_prefs(field=name)
        if self.on_field_change is not None:
            self.on_field_change(name)
        self.canvas.draw_idle()
        return True

    def add_custom_field(self, image_path=None, name=None):
        """'+ Add image...': pick an image cropped to the 144 x 144 in field and select it."""
        if image_path is None:
            image_path = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
                title="Field image (top-down, cropped to the 144 x 144 in tiles)")
        if not image_path:
            return False
        image_path = os.path.abspath(image_path)
        name = name or os.path.splitext(os.path.basename(image_path))[0]
        if name == NO_FIELD or any(f.name == name and f.builtin for f in self.field_options()):
            name += " (custom)"
        preset = custom_field(name, image_path)
        if not self._show_field(preset):
            return False
        customs = [c for c in self._load_prefs().get('custom_fields', [])
                   if isinstance(c, dict) and c.get('name') != name]
        self._save_prefs(custom_fields=customs + [{"name": name, "path": image_path}])
        return self.select_field(name)

    def remove_custom_field(self, name):
        customs = [c for c in self._load_prefs().get('custom_fields', [])
                   if isinstance(c, dict) and c.get('name') != name]
        self._save_prefs(custom_fields=customs)
        if self.field_name == name:
            self.select_field(NO_FIELD)
        elif self.on_field_change is not None:
            self.on_field_change(self.field_name)
