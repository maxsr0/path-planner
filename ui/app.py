import math
import tkinter as tk

from spline.hermite import sample_hermite_path
from ui.waypoint import Waypoint
from profiler.trajectory import generate_trajectory
from exporter.binary_exporter import export_trajectory


class App:
    def __init__(self, root, fig, ax, canvas, entries):
        self.ax = ax
        self.canvas = canvas
        self.entries = entries
        self.waypoints = []
        self.dot_artists = []
        self.spline_line = None
        self.selected_waypoint = None
        self.is_dragging = False

    @staticmethod
    def check_distance(click_x, click_y, w):
        r = 5
        return math.pow(w.x - click_x, 2) + math.pow(w.y - click_y, 2) <= math.pow(r, 2)

    def compute_tangents(self):
        for i in range(1, len(self.waypoints) - 1):
            if not self.waypoints[i].manual_tangent:
                self.waypoints[i].auto_tangent(self.waypoints[i - 1], self.waypoints[i + 1])

        if len(self.waypoints) >= 2:
            self.waypoints[0].dx = self.waypoints[1].x - self.waypoints[0].x
            self.waypoints[0].dy = self.waypoints[1].y - self.waypoints[0].y
            self.waypoints[-1].dx = self.waypoints[-1].x - self.waypoints[-2].x
            self.waypoints[-1].dy = self.waypoints[-1].y - self.waypoints[-2].y

    def draw_spline(self, wps):
        if len(wps) < 2:
            return

        points = [(w.x, w.y) for w in wps]
        tangents = [(w.dx, w.dy) for w in wps]

        path = sample_hermite_path(points, tangents, 20)
        xs, ys = zip(*path)

        self.spline_line = self.ax.plot(xs, ys, '-', color='white')[0]

    def draw_waypoint(self, w):
        dot = self.ax.plot(w.x, w.y, 'o', color='white')[0]
        self.dot_artists.append(dot)

    def draw_all(self):
        if self.spline_line is not None:
            self.spline_line.remove()

        for d in self.dot_artists:
            d.remove()
        self.dot_artists.clear()

        for w in self.waypoints:
            self.draw_waypoint(w)

        self.draw_spline(self.waypoints)

        self.canvas.draw()

    def on_click(self, event):
        if event.xdata is None or event.ydata is None:
            return

        for w in self.waypoints:
            if self.check_distance(event.xdata, event.ydata, w):
                self.is_dragging = True
                self.selected_waypoint = w
                self.update_panel()
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

        self.selected_waypoint.x = float(self.entries['x'].get())
        self.selected_waypoint.y = float(self.entries['y'].get())
        self.selected_waypoint.dx = float(self.entries['dx'].get())
        self.selected_waypoint.dy = float(self.entries['dy'].get())
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

    def on_export(self):
        if len(self.waypoints) < 2:
            return

        pts = [(w.x, w.y) for w in self.waypoints]
        tangents = [(w.dx, w.dy) for w in self.waypoints]

        traj = generate_trajectory(pts, tangents, 20, 100, 20)

        file_path = tk.filedialog.asksaveasfilename(
            defaultextension=".bin",
            title="Export location"
        )
        if file_path:
            export_trajectory(traj, file_path)
