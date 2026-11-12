"""Speed vs time strip, drawn with QPainter.

One series in the speed colors (so its y axis doubles as the path's color key),
a zero line when the path reverses, hover scrubbing and a playhead with readout.
"""
from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from qt_ui.theme import speed_color

MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 48, 14, 12, 24


class SpeedPlot(QWidget):
    time_hovered = Signal(object)  # float seconds, or None when the mouse leaves

    def __init__(self, editor, theme, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.theme = theme
        self.playhead = None
        self.setMouseTracking(True)
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        editor.subscribe(lambda kind: self.update() if kind in ("path", "config") else None)

    # ---------- geometry ----------

    def _plot_rect(self):
        return QRectF(MARGIN_L, MARGIN_T, max(1, self.width() - MARGIN_L - MARGIN_R),
                      max(1, self.height() - MARGIN_T - MARGIN_B))

    def duration(self):
        traj = self.editor.trajectory
        return traj[-1].timestamp if len(traj) >= 2 else 0.0

    def v_range(self):
        top = self.editor.config.v_max * 1.05
        reverses = any(p.velocity < 0 for p in self.editor.trajectory)
        return (-top if reverses else 0.0), top

    def x_for_time(self, t):
        r = self._plot_rect()
        d = self.duration() or 1.0
        return r.left() + r.width() * t / d

    def time_at_x(self, x):
        if self.duration() <= 0:
            return None
        r = self._plot_rect()
        f = (x - r.left()) / r.width()
        return min(max(f, 0.0), 1.0) * self.duration()

    def y_for_v(self, v):
        r = self._plot_rect()
        lo, hi = self.v_range()
        return r.bottom() - r.height() * (v - lo) / ((hi - lo) or 1.0)

    def point_for_time(self, t):
        return QPoint(round(self.x_for_time(t)), round(self._plot_rect().center().y()))

    # ---------- state ----------

    @property
    def readout(self):
        if self.playhead is None or self.duration() <= 0:
            return ""
        v = self.editor.pose_at(self.playhead)[3]
        return f"t {self.playhead:5.2f} s   v {v:6.1f} in/s"

    def set_playhead(self, t):
        self.playhead = t
        self.update()

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    # ---------- events ----------

    def mouseMoveEvent(self, event):
        t = self.time_at_x(event.position().x())
        if t is not None and self._plot_rect().contains(event.position()):
            self.time_hovered.emit(t)

    def leaveEvent(self, event):
        self.time_hovered.emit(None)
        super().leaveEvent(event)

    # ---------- painting ----------

    def paintEvent(self, event):
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.panel))
        r = self._plot_rect()
        font = QFont()
        font.setPointSizeF(8)
        p.setFont(font)

        lo, hi = self.v_range()
        step = 25 if hi <= 130 else 50
        v = step * int(lo // step)
        while v <= hi:
            y = self.y_for_v(v)
            if r.top() - 1 <= y <= r.bottom() + 1:
                p.setPen(QPen(QColor(t.border if v else t.muted), 1))
                p.drawLine(QLineF(r.left(), y, r.right(), y))
                p.setPen(QColor(t.muted))
                p.drawText(QRectF(0, y - 8, MARGIN_L - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:g}")
            v += step

        traj = self.editor.trajectory
        dur = self.duration()
        if dur > 0:
            tick = 0.5 if dur <= 4 else 1 if dur <= 12 else 2 if dur <= 30 else 5
            k = 0.0
            while k <= dur + 1e-9:
                x = self.x_for_time(k)
                p.setPen(QColor(t.muted))
                p.drawText(QRectF(x - 20, r.bottom() + 4, 40, 16), Qt.AlignHCenter | Qt.AlignTop, f"{k:g}")
                k += tick
            p.drawText(QRectF(r.right() - 60, r.bottom() + 4, 60, 16), Qt.AlignRight | Qt.AlignTop, "s")

            v_max = self.editor.config.v_max
            for a, b in zip(traj, traj[1:]):
                pen = QPen(QColor(speed_color(t, (a.velocity + b.velocity) / 2, v_max)), 2.2)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(self.x_for_time(a.timestamp), self.y_for_v(a.velocity)),
                           QPointF(self.x_for_time(b.timestamp), self.y_for_v(b.velocity)))
        else:
            p.setPen(QColor(t.muted))
            p.drawText(r, Qt.AlignCenter, "Place two or more waypoints to see the speed profile")

        p.save()
        p.translate(12, r.center().y())
        p.rotate(-90)
        p.setPen(QColor(t.muted))
        p.drawText(QRectF(-60, -8, 120, 16), Qt.AlignCenter, "speed (in/s)")
        p.restore()

        if self.playhead is not None and dur > 0:
            x = self.x_for_time(min(max(self.playhead, 0.0), dur))
            p.setPen(QPen(QColor(t.text), 1))
            p.drawLine(QLineF(x, r.top(), x, r.bottom()))
            p.setPen(QColor(t.text))
            p.drawText(QRectF(r.right() - 260, r.top(), 256, 16), Qt.AlignRight | Qt.AlignTop, self.readout)
        p.end()
