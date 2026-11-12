"""The interactive field: a QGraphicsView in inches with +y up.

Scene units are inches; the scene's y axis is flipped (scene_y = 144 - y) so the
field reads like the robot's coordinate frame. Waypoints, handles and labels ignore
the view transform so they stay the same pixel size at any zoom.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView)

from planner.fields import FIELD_IN
from qt_ui.theme import speed_color

WAYPOINT_PX = 9         # waypoint radius in screen pixels
HIT_PX = 14             # grab distance in screen pixels
MAX_IMAGE_PX = 1600     # field images are downscaled to this for smooth panning
FIT_MARGIN_IN = 2.0
ZOOM_RANGE = (0.5, 12.0)  # relative to the fitted zoom


def _pen(color, width, style=Qt.SolidLine, cap=Qt.RoundCap):
    pen = QPen(QColor(color), width, style, cap, Qt.RoundJoin)
    pen.setCosmetic(True)  # width in pixels, independent of zoom
    return pen


class WaypointItem(QGraphicsEllipseItem):
    def __init__(self, label):
        r = WAYPOINT_PX
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.label = label
        self.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations)
        self.setZValue(10)
        self.text = QGraphicsSimpleTextItem(label, self)
        font = QFont()
        font.setPointSizeF(7.5)
        font.setBold(True)
        self.text.setFont(font)
        br = self.text.boundingRect()
        self.text.setPos(-br.width() / 2, -br.height() / 2)

    def style(self, fill, outline, text_color, selected):
        self.setBrush(QBrush(QColor(fill)))
        self.setPen(QPen(QColor(outline), 2 if selected else 1.5))
        self.text.setBrush(QBrush(QColor(text_color)))
        self.setScale(1.2 if selected else 1.0)


class FieldView(QGraphicsView):
    cursor_moved = Signal(float, float)   # field inches
    hint_changed = Signal(str)

    def __init__(self, editor, theme, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.theme = theme
        self.preset = None
        self.image_item = None
        self.waypoint_items = []
        self.path_items = []
        self.reverse_items = []
        self._static = []
        self._dragging = False
        self._pan_from = None
        self._fit_scale = None
        self._robot_t = None

        self.setScene(QGraphicsScene(self))
        self.scene().setSceneRect(-400, -400, FIELD_IN + 800, FIELD_IN + 800)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.NoFrame)

        s = self.scene()
        self.field_rect = s.addRect(QRectF(0, 0, FIELD_IN, FIELD_IN))
        self.field_rect.setZValue(0)
        self.grid_items = []
        for k in range(1, 6):
            v = 24 * k
            self.grid_items.append(s.addLine(v, 0, v, FIELD_IN))
            self.grid_items.append(s.addLine(0, v, FIELD_IN, v))
        for g in self.grid_items:
            g.setZValue(1)
        self.casing_item = s.addPath(QPainterPath())
        self.casing_item.setZValue(2)
        self.handle_line = s.addLine(0, 0, 0, 0)
        self.handle_line.setZValue(11)
        self.handle_item = QGraphicsRectItem(-5, -5, 10, 10)
        self.handle_item.setFlag(QGraphicsRectItem.ItemIgnoresTransformations)
        self.handle_item.setZValue(12)
        s.addItem(self.handle_item)
        self.start_ghost = s.addPolygon(QPolygonF())
        self.end_ghost = s.addPolygon(QPolygonF())
        self.robot_item = s.addPolygon(QPolygonF())
        self.robot_heading = s.addLine(0, 0, 0, 0)
        for item, z in ((self.start_ghost, 4), (self.end_ghost, 4), (self.robot_item, 20), (self.robot_heading, 20)):
            item.setZValue(z)
        self.robot_item.setVisible(False)
        self.robot_heading.setVisible(False)

        editor.subscribe(self._on_editor_change)
        self.set_theme(theme)

    # ---------- coordinates ----------

    @staticmethod
    def to_scene(x, y):
        return QPointF(x, FIELD_IN - y)

    @staticmethod
    def to_field(point):
        return point.x(), FIELD_IN - point.y()

    def _event_field(self, event):
        return self.to_field(self.mapToScene(event.position().toPoint()))

    def _px_to_in(self, px):
        scale = self.transform().m11() or 1.0
        return px / scale

    # ---------- view ----------

    def fit_field(self):
        m = FIT_MARGIN_IN
        lo, hi = 0.0, FIELD_IN
        if self.preset is not None:
            lo, hi, _, _ = self.preset.extent
            lo, hi = min(lo, 0.0), max(hi, FIELD_IN)
        self.resetTransform()
        self.fitInView(QRectF(lo - m, (FIELD_IN - hi) - m, (hi - lo) + 2 * m, (hi - lo) + 2 * m), Qt.KeepAspectRatio)
        self._fit_scale = self.transform().m11()

    def zoom_by(self, factor, anchor=None):
        if self._fit_scale:
            current = self.transform().m11() / self._fit_scale
            factor = max(ZOOM_RANGE[0] / current, min(ZOOM_RANGE[1] / current, factor))
        anchor = anchor if anchor is not None else self.viewport().rect().center()
        before = self.mapToScene(anchor)
        self.scale(factor, factor)
        after = self.mapToScene(anchor)
        d = after - before
        self.translate(d.x(), d.y())

    def zoom_at(self, viewport_pos, wheel_delta):
        self.zoom_by(1.15 ** (wheel_delta / 120), viewport_pos)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_scale is None or abs(self.transform().m11() - self._fit_scale) < 1e-9:
            self.fit_field()  # stay fitted while the window resizes, unless the user zoomed

    # ---------- theme / field ----------

    def set_theme(self, theme):
        self.theme = theme
        self.setBackgroundBrush(QBrush(QColor(theme.surface)))
        self.field_rect.setBrush(QBrush(QColor(theme.field_surface)))
        self.field_rect.setPen(_pen(theme.grid, 1))
        for g in self.grid_items:
            g.setPen(_pen(theme.grid, 1))
        self._rebuild()

    def set_field(self, preset):
        """Show a FieldPreset's image (None = plain grid). Returns False if the image can't load."""
        if self.image_item is not None:
            self.scene().removeItem(self.image_item)
            self.image_item = None
        self.preset = None
        if preset is not None:
            pix = QPixmap(preset.path)
            if pix.isNull():
                self._show_grid(True)
                return False
            if max(pix.width(), pix.height()) > MAX_IMAGE_PX:
                pix = pix.scaled(MAX_IMAGE_PX, MAX_IMAGE_PX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QGraphicsPixmapItem(pix)
            item.setTransformationMode(Qt.SmoothTransformation)
            lo, hi, _, _ = preset.extent
            item.setScale((hi - lo) / pix.width())
            item.setPos(self.to_scene(lo, hi))
            item.setZValue(0.5)
            self.scene().addItem(item)
            self.image_item = item
            self.preset = preset
        self._show_grid(self.image_item is None)
        self.fit_field()
        return True

    def _show_grid(self, show):
        for g in self.grid_items:
            g.setVisible(show)

    # ---------- drawing ----------

    def _on_editor_change(self, kind):
        if kind in ("path", "config", "selection"):
            self._rebuild()

    def _clear(self, items):
        for item in items:
            self.scene().removeItem(item)
        items.clear()

    def _rebuild(self):
        t, ed = self.theme, self.editor
        traj = ed.trajectory
        self._clear(self.path_items)
        self._clear(self.reverse_items)

        casing = QPainterPath()
        if len(traj) >= 2:
            casing.moveTo(self.to_scene(traj[0].x, traj[0].y))
            for p in traj[1:]:
                casing.lineTo(self.to_scene(p.x, p.y))
        self.casing_item.setPath(casing)
        self.casing_item.setPen(_pen(t.path_casing, 7))

        v_max = ed.config.v_max
        run = None
        for a, b in zip(traj, traj[1:]):
            mid_v = (a.velocity + b.velocity) / 2
            line = QGraphicsLineItem(a.x, FIELD_IN - a.y, b.x, FIELD_IN - b.y)
            line.setPen(_pen(speed_color(t, mid_v, v_max), 4))
            line.setZValue(3)
            self.scene().addItem(line)
            self.path_items.append(line)
            if mid_v < 0:  # reversed: collect runs for the dashed overlay
                if run is None:
                    run = QPainterPath(self.to_scene(a.x, a.y))
                run.lineTo(self.to_scene(b.x, b.y))
            elif run is not None:
                self._add_reverse(run)
                run = None
        if run is not None:
            self._add_reverse(run)

        self._clear(self.waypoint_items)
        for i, w in enumerate(ed.waypoints):
            item = WaypointItem(str(i + 1))
            selected = w is ed.selected
            item.style(t.selected if selected else t.waypoint, t.waypoint_outline,
                       t.accent_text if selected else t.waypoint_outline, selected)
            item.setPos(self.to_scene(w.x, w.y))
            item.setToolTip(f"#{i + 1}  ({w.x:.1f}, {w.y:.1f})")
            self.scene().addItem(item)
            self.waypoint_items.append(item)

        sel = ed.selected
        self.handle_item.setVisible(sel is not None)
        self.handle_line.setVisible(sel is not None)
        if sel is not None:
            hx, hy = ed.handle_pos(sel)
            color = t.selected if sel.manual_tangent else t.handle
            self.handle_item.setPos(self.to_scene(hx, hy))
            self.handle_item.setBrush(QBrush(QColor(color)))
            self.handle_item.setPen(QPen(QColor(t.waypoint_outline), 1))
            self.handle_line.setLine(sel.x, FIELD_IN - sel.y, hx, FIELD_IN - hy)
            self.handle_line.setPen(_pen(color, 1.5))

        has_path = len(traj) >= 2
        for ghost, p in ((self.start_ghost, traj[0] if has_path else None),
                         (self.end_ghost, traj[-1] if has_path else None)):
            ghost.setVisible(p is not None)
            if p is not None:
                ghost.setPolygon(self._footprint(p.x, p.y, p.theta))
                ghost.setPen(_pen(t.muted, 1.2, Qt.DashLine))
                ghost.setBrush(Qt.NoBrush)
        self.robot_item.setPen(_pen(t.robot, 2))
        self.robot_heading.setPen(_pen(t.robot, 2))
        self.set_robot_time(self._robot_t)

    def _add_reverse(self, run):
        item = QGraphicsPathItem(run)
        item.setPen(_pen(self.theme.path_casing, 2.5, Qt.DashLine, Qt.FlatCap))
        item.setZValue(3.5)
        self.scene().addItem(item)
        self.reverse_items.append(item)

    def _robot_size(self):
        tw = self.editor.config.track_width
        return tw if tw > 0 else 12.0

    def _footprint(self, x, y, theta):
        h = self._robot_size() / 2
        c, s = math.cos(theta), math.sin(theta)
        return QPolygonF([self.to_scene(x + cx * c - cy * s, y + cx * s + cy * c)
                          for cx, cy in ((-h, -h), (h, -h), (h, h), (-h, h))])

    def set_robot_time(self, t):
        """Show the robot at time t along the trajectory (None hides it)."""
        self._robot_t = t
        traj = self.editor.trajectory
        visible = t is not None and len(traj) >= 2
        self.robot_item.setVisible(visible)
        self.robot_heading.setVisible(visible)
        if not visible:
            return
        x, y, theta, _ = self.editor.pose_at(t)
        self.robot_item.setPolygon(self._footprint(x, y, theta))
        h = self._robot_size() / 2
        self.robot_heading.setLine(x, FIELD_IN - y, x + h * math.cos(theta), FIELD_IN - (y + h * math.sin(theta)))

    # ---------- mouse ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_from = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        x, y = self._event_field(event)
        mods = event.modifiers()
        hit = self.editor.hit_test(x, y, radius=self._px_to_in(HIT_PX))
        if event.button() == Qt.RightButton:
            if hit is not None and hit[0] == "point":
                self.editor.delete_waypoint(hit[1])
            return
        if event.button() != Qt.LeftButton:
            return
        snap = bool(mods & Qt.ControlModifier)
        if hit is not None:
            mode, w = hit
            self.editor.begin_drag(w, mode)
            self._dragging = True
        elif mods & Qt.ShiftModifier:
            self.editor.insert_waypoint(x, y, snap=snap)
        else:
            self.editor.add_waypoint(x, y, snap=snap)

    def mouseMoveEvent(self, event):
        if self._pan_from is not None:
            d = event.position() - self._pan_from
            self._pan_from = event.position()
            scale = self.transform().m11() or 1.0
            self.translate(d.x() / scale, d.y() / scale)
            return
        x, y = self._event_field(event)
        self.cursor_moved.emit(x, y)
        if self._dragging:
            self.editor.drag_to(x, y, snap=bool(event.modifiers() & Qt.ControlModifier))
            return
        hit = self.editor.hit_test(x, y, radius=self._px_to_in(HIT_PX))
        if hit is None:
            hint = "Click to add a waypoint  ·  Shift+click the path to insert  ·  Ctrl snaps"
            self.viewport().setCursor(Qt.CrossCursor)
        elif hit[0] == "handle":
            hint = "Drag to bend the curve (sets a manual heading)"
            self.viewport().setCursor(Qt.SizeAllCursor)
        else:
            idx = next(i for i, w in enumerate(self.editor.waypoints) if w is hit[1]) + 1
            hint = f"Waypoint {idx}: drag to move  ·  right-click to delete"
            self.viewport().setCursor(Qt.OpenHandCursor)
        self.hint_changed.emit(hint)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_from = None
            self.unsetCursor()
            return
        if self._dragging:
            self._dragging = False
            self.editor.end_drag()

    def wheelEvent(self, event):
        self.zoom_at(event.position().toPoint(), event.angleDelta().y())
