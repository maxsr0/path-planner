import math
import tkinter as tk
from tkinter import filedialog, messagebox

from spline.hermite import sample_hermite_path
from ui.waypoint import Waypoint
from profiler.trajectory import generate_trajectory
from profiler.config import RobotConfig, load_config, save_config
from exporter.binary_exporter import export_trajectory
from exporter.header_exporter import export_trajectory_header


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
        self.ax = ax
        self.canvas = canvas
        self.entries = entries
        self.waypoints = []
        self.dot_artists = []
        self.spline_line = None
        self.selected_waypoint = None
        self.is_dragging = False
        self.settings_entries = settings_entries or {}
        self.stats_var = stats_var
        self.config_path = config_path
        self.config = RobotConfig()
        if config_path:
            self.config, error = load_config(config_path)
            if error:
                messagebox.showwarning("Robot settings", error)
        self.fill_settings()

    @staticmethod
    def check_distance(click_x, click_y, w):
        r = 5
        return math.pow(w.x - click_x, 2) + math.pow(w.y - click_y, 2) <= math.pow(r, 2)

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

    def draw_all(self):
        if self.spline_line is not None:
            self.spline_line.remove()
            self.spline_line = None

        for d in self.dot_artists:
            d.remove()
        self.dot_artists.clear()

        for w in self.waypoints:
            self.draw_waypoint(w)

        self.draw_spline(self.waypoints)
        self.update_stats()

        self.canvas.draw()

    def on_click(self, event):
        if event.button != 1:  # left button only; others reserved (e.g. right-click delete)
            return
        if event.xdata is None or event.ydata is None:
            return

        for w in self.waypoints:
            if self.check_distance(event.xdata, event.ydata, w):
                self.is_dragging = True
                self.selected_waypoint = w
                self.update_panel()
                self.draw_all()
                return

        w = Waypoint(event.xdata, event.ydata)
        self.waypoints.append(w)

        self.compute_tangents()

        self.draw_all()

    def on_drag(self, event):
        if not self.is_dragging or self.selected_waypoint is None:
            return
        if event.xdata is None or event.ydata is None:
            return

        self.selected_waypoint.x = event.xdata
        self.selected_waypoint.y = event.ydata

        self.compute_tangents()

        self.update_panel()
        self.draw_all()

    def on_release(self, event):
        self.is_dragging = False

    def on_apply(self):
        if self.selected_waypoint is None:
            return

        try:
            values = {k: float(self.entries[k].get()) for k in ('x', 'y', 'dx', 'dy')}
        except ValueError:
            messagebox.showerror("Invalid input", "x, y, dx and dy must all be numbers.")
            return

        self.selected_waypoint.x = values['x']
        self.selected_waypoint.y = values['y']
        self.selected_waypoint.dx = values['dx']
        self.selected_waypoint.dy = values['dy']
        self.selected_waypoint.manual_tangent = True

        self.compute_tangents()
        self.draw_all()

    def update_panel(self):
        self.entries['x'].delete(0, tk.END)
        self.entries['x'].insert(0, round(self.selected_waypoint.x, 3))

        self.entries['y'].delete(0, tk.END)
        self.entries['y'].insert(0, round(self.selected_waypoint.y, 3))

        self.entries['dx'].delete(0, tk.END)
        self.entries['dx'].insert(0, round(self.selected_waypoint.dx, 3))

        self.entries['dy'].delete(0, tk.END)
        self.entries['dy'].insert(0, round(self.selected_waypoint.dy, 3))

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
