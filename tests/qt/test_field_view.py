"""FieldView: the big interactive field (QGraphicsView), driven with real Qt mouse events."""
import math

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from planner.fields import FIELDS_DIR, load_builtin_fields
from qt_ui.field_view import FieldView
from qt_ui.theme import THEMES, speed_color

TOL = 0.75  # inches: one screen pixel is ~0.2 in at this size, plus rounding


@pytest.fixture
def view(qtbot, editor):
    v = FieldView(editor, THEMES["dark"])
    v.resize(800, 800)
    qtbot.addWidget(v)
    v.show()
    qtbot.waitExposed(v)
    v.fit_field()
    return v


def vp(view, x, y):
    """Viewport pixel for a field position in inches."""
    return view.mapFromScene(view.to_scene(x, y))


def click(view, x, y, button=Qt.LeftButton, mods=Qt.NoModifier):
    QTest.mouseClick(view.viewport(), button, mods, vp(view, x, y))


def drag(view, start, end, steps=4):
    vpw = view.viewport()
    QTest.mousePress(vpw, Qt.LeftButton, Qt.NoModifier, vp(view, *start))
    for i in range(1, steps + 1):
        f = i / steps
        QTest.mouseMove(vpw, vp(view, start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f))
    QTest.mouseRelease(vpw, Qt.LeftButton, Qt.NoModifier, vp(view, *end))


# ---------- coordinates ----------

def test_scene_mapping_has_y_up(view):
    assert view.to_field(view.to_scene(10, 20)) == pytest.approx((10, 20))
    top = view.to_scene(72, 144)
    bottom = view.to_scene(72, 0)
    assert top.y() < bottom.y()  # +y is up on screen


def test_fit_shows_whole_field_and_fills_view(view):
    corners = [vp(view, 0, 0), vp(view, 144, 144)]
    for p in corners:
        assert 0 <= p.x() <= 800 and 0 <= p.y() <= 800
    side = abs(corners[1].x() - corners[0].x())
    assert side > 700  # the field fills the view


# ---------- mouse editing ----------

def test_click_adds_waypoint(view, editor):
    click(view, 30, 120)
    w = editor.waypoints[-1]
    assert (w.x, w.y) == pytest.approx((30, 120), abs=TOL)
    assert editor.selected is w


def test_click_existing_selects_without_adding(view, editor):
    click(view, 72, 100)
    assert len(editor.waypoints) == 3
    assert editor.selected is editor.waypoints[1]


def test_drag_moves_waypoint_one_undo_step(view, editor):
    depth = len(editor.undo_stack)
    drag(view, (72, 100), (80, 110))
    w = editor.waypoints[1]
    assert (w.x, w.y) == pytest.approx((80, 110), abs=TOL)
    assert len(editor.undo_stack) == depth + 1
    assert not editor.dragging


def test_shift_click_inserts(view, editor):
    seg, _ = editor.nearest_segment(48, 62)
    on_path = editor.preview_path(per_segment=100)
    px, py = min(on_path, key=lambda p: math.hypot(p[0] - 48, p[1] - 62))
    click(view, px, py, mods=Qt.ShiftModifier)
    assert len(editor.waypoints) == 4
    assert (editor.waypoints[1].x, editor.waypoints[1].y) == pytest.approx((px, py), abs=TOL)


def test_right_click_deletes(view, editor):
    click(view, 72, 100, button=Qt.RightButton)
    assert len(editor.waypoints) == 2


def test_right_click_empty_does_nothing(view, editor):
    click(view, 10, 140, button=Qt.RightButton)
    assert len(editor.waypoints) == 3


def test_ctrl_click_snaps(view, editor):
    click(view, 30.4, 120.6, mods=Qt.ControlModifier)
    w = editor.waypoints[-1]
    assert (w.x, w.y) == (round(w.x), round(w.y))
    assert (w.x, w.y) == pytest.approx((30, 121), abs=1)


def test_drag_tangent_handle(view, editor):
    w = editor.waypoints[1]
    editor.select(w)
    hx, hy = editor.handle_pos(w)
    drag(view, (hx, hy), (w.x, w.y + 20))
    assert w.manual_tangent
    assert (w.dx, w.dy) == pytest.approx((0, 60), abs=3 * TOL)
    assert (w.x, w.y) == (72, 100)


def test_cursor_signal_reports_inches(view, qtbot):
    with qtbot.waitSignal(view.cursor_moved) as sig:
        QTest.mouseMove(view.viewport(), vp(view, 50, 60))
    x, y = sig.args
    assert (x, y) == pytest.approx((50, 60), abs=TOL)


# ---------- zoom ----------

def test_zoom_and_fit(view):
    before = view.transform().m11()
    view.zoom_by(2.0)
    assert view.transform().m11() == pytest.approx(before * 2)
    view.fit_field()
    assert view.transform().m11() == pytest.approx(before)


def test_wheel_zooms(view, qtbot):
    before = view.transform().m11()
    view.zoom_at(vp(view, 72, 72), 120)  # one wheel notch in
    assert view.transform().m11() > before


# ---------- drawing ----------

def test_waypoints_are_numbered(view, editor):
    assert [item.label for item in view.waypoint_items] == ["1", "2", "3"]


def test_path_colored_by_speed(view, editor):
    segs = view.path_items
    assert len(segs) == len(editor.trajectory) - 1
    theme = THEMES["dark"]
    fastest = max(range(len(segs)), key=lambda i: abs(editor.trajectory[i].velocity))
    expected = QColor(speed_color(theme, (editor.trajectory[fastest].velocity
                                          + editor.trajectory[fastest + 1].velocity) / 2,
                                  editor.config.v_max))
    assert segs[fastest].pen().color().name() == expected.name()


def test_reversed_segment_is_dashed(view, editor):
    assert not view.reverse_items
    editor.update_waypoint(editor.waypoints[0], reversed=True)
    assert view.reverse_items
    assert all(item.pen().style() == Qt.DashLine for item in view.reverse_items)


def test_handle_only_on_selected(view, editor):
    assert not view.handle_item.isVisible()
    editor.select(editor.waypoints[1])
    assert view.handle_item.isVisible()


def test_start_and_end_footprints(view, editor):
    assert view.start_ghost.isVisible() and view.end_ghost.isVisible()
    editor.set_config(type(editor.config)(track_width=16))
    rect = view.start_ghost.polygon().boundingRect()
    assert max(rect.width(), rect.height()) >= 16 - 1e-6


def test_robot_marker_follows_time(view, editor):
    assert not view.robot_item.isVisible()
    t = editor.trajectory[-1].timestamp / 2
    view.set_robot_time(t)
    assert view.robot_item.isVisible()
    x, y, _, _ = editor.pose_at(t)
    c = view.robot_item.polygon().boundingRect().center()
    assert view.to_field(c) == pytest.approx((x, y), abs=0.5)
    view.set_robot_time(None)
    assert not view.robot_item.isVisible()


def test_field_image_extent(view):
    preset = load_builtin_fields(FIELDS_DIR)[0]
    view.set_field(preset)
    rect = view.image_item.sceneBoundingRect()
    lo, hi, _, _ = preset.extent
    assert rect.width() == pytest.approx(hi - lo, abs=0.01)
    assert view.to_field(rect.bottomLeft()) == pytest.approx((lo, lo), abs=0.01)
    view.set_field(None)
    assert view.image_item is None


def test_theme_switch_recolors(view):
    view.set_theme(THEMES["light"])
    assert view.backgroundBrush().color().name() == THEMES["light"].surface
    assert view.waypoint_items[0].brush().color().name() == THEMES["light"].waypoint
