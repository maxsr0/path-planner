"""Speed visualization: path colored by speed, a speed-vs-time plot, and a robot marker."""
import math

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Polygon

from profiler.trajectory import state_at

# One-hue sequential ramp (blue, dark -> light for the dark surface). The darkest step
# (#184f95) still clears 2:1 against the field so slow sections never vanish.
SPEED_CMAP = LinearSegmentedColormap.from_list(
    "speed", ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"])

SURFACE = '#0d1117'
INK = '#aaa'      # text
MUTED = '#555'    # ticks
GRID = '#333'     # grid lines and spines
ROBOT = '#e8e8e8'


def _segments(xs, ys):
    pts = np.column_stack([xs, ys])
    return np.stack([pts[:-1], pts[1:]], axis=1)


class VelocityView:
    def __init__(self, field_ax, profile_ax):
        self.field_ax = field_ax
        self.ax = profile_ax
        self.trajectory = []
        self.robot_size = 12.0
        self._artists = []
        self.playhead = None
        self.robot = None
        self.heading = None
        self.readout = None

        ax = profile_ax
        ax.set_facecolor(SURFACE)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.grid(True, color=GRID, linewidth=0.5)
        ax.set_xlabel("time (s)", color=INK, fontsize=8)
        ax.set_ylabel("speed (in/s)", color=INK, fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

    def clear(self):
        for artist in self._artists:
            artist.remove()
        self._artists = []
        self.playhead = self.robot = self.heading = self.readout = None

    def update(self, trajectory, v_max, robot_size=0.0):
        """Redraw for a new trajectory. robot_size <= 0 uses a 12 in default square."""
        self.clear()
        self.trajectory = trajectory
        self.robot_size = robot_size if robot_size > 0 else 12.0
        if len(trajectory) < 2:
            self.ax.set_xlim(0, 1)
            self.ax.set_ylim(0, 1)
            return

        xs = np.array([p.x for p in trajectory])
        ys = np.array([p.y for p in trajectory])
        vs = np.array([p.velocity for p in trajectory])   # negative while driving backwards
        ts = np.array([p.timestamp for p in trajectory])
        mid_v = (vs[:-1] + vs[1:]) / 2
        mid_speed = np.abs(mid_v)                         # color encodes speed, not direction
        norm = Normalize(0, v_max)

        path = LineCollection(_segments(xs, ys), cmap=SPEED_CMAP, norm=norm,
                              linewidths=2.5, capstyle='round', zorder=2)
        path.set_array(mid_speed)
        self.field_ax.add_collection(path)
        extra = []

        # Reversed runs: cut surface-colored gaps into the line so it reads as dashed.
        backwards = mid_v < 0
        i = 0
        while i < len(backwards):
            if backwards[i]:
                j = i
                while j < len(backwards) and backwards[j]:
                    j += 1
                gaps = self.field_ax.plot(xs[i:j + 1], ys[i:j + 1], color=SURFACE, linewidth=3.5,
                                          dashes=(2, 3), zorder=2.1)[0]
                extra.append(gaps)
                i = j
            else:
                i += 1

        profile = LineCollection(_segments(ts, vs), cmap=SPEED_CMAP, norm=norm, linewidths=2, capstyle='round')
        profile.set_array(mid_speed)
        self.ax.add_collection(profile)
        self.ax.set_xlim(0, max(ts[-1], 1e-3))
        if backwards.any():
            self.ax.set_ylim(-v_max * 1.05, v_max * 1.05)
            extra.append(self.ax.axhline(0, color=MUTED, linewidth=0.8))
        else:
            self.ax.set_ylim(0, v_max * 1.05)

        self.playhead = self.ax.axvline(0, color=INK, linewidth=1, alpha=0.7, visible=False)
        self.readout = self.ax.text(0.99, 0.92, "", transform=self.ax.transAxes, ha='right', va='top',
                                    color=INK, fontsize=8, family='monospace')
        self.robot = Polygon(np.zeros((4, 2)), closed=True, fill=False, edgecolor=ROBOT,
                             linewidth=1.5, zorder=5, visible=False)
        self.field_ax.add_patch(self.robot)
        self.heading = self.field_ax.plot([], [], '-', color=ROBOT, linewidth=1.5, zorder=5, visible=False)[0]

        self._artists = [path, profile, self.playhead, self.readout, self.robot, self.heading] + extra

    @property
    def duration(self):
        return self.trajectory[-1].timestamp if len(self.trajectory) >= 2 else 0.0

    def set_time(self, t):
        """Show the robot and playhead at time t; None hides them."""
        if self.robot is None:
            return
        visible = t is not None
        for artist in (self.playhead, self.robot, self.heading, self.readout):
            artist.set_visible(visible)
        if not visible:
            return

        t = min(max(t, 0.0), self.duration)
        x, y, theta, v = state_at(self.trajectory, t)
        h = self.robot_size / 2
        c, s = math.cos(theta), math.sin(theta)
        corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
        self.robot.set_xy([(x + cx * c - cy * s, y + cx * s + cy * c) for cx, cy in corners])
        self.heading.set_data([x, x + h * c], [y, y + h * s])
        self.playhead.set_xdata([t, t])
        self.readout.set_text(f"t {t:5.2f} s   v {v:5.1f} in/s")
