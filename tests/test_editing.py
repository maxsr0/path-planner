import pytest

from conftest import Click, Key


def coords(app):
    return [(round(w.x, 6), round(w.y, 6)) for w in app.waypoints]


@pytest.fixture
def app(make_app):
    a, _, _ = make_app()
    for p in [(10, 10), (70, 70), (130, 10)]:
        a.on_click(Click(*p))
    return a


def test_new_waypoint_is_selected(app):
    assert app.selected_waypoint is app.waypoints[-1]
    assert app.entries['x'].value == "130"


def test_right_click_deletes_and_neighbors_retangent(app):
    app.on_click(Click(70, 70, button=3))
    assert coords(app) == [(10, 10), (130, 10)]
    first = app.waypoints[0]
    assert (first.dx, first.dy) == (120, 0)  # auto endpoint tangent re-aimed at new neighbor


def test_right_click_empty_space_does_nothing(app):
    app.on_click(Click(40, 120, button=3))
    assert len(app.waypoints) == 3


def test_delete_key_removes_selected_and_clears_panel(app):
    app.on_click(Click(70, 70))
    app.on_release(None)
    app.on_key(Key('delete'))
    assert coords(app) == [(10, 10), (130, 10)]
    assert app.selected_waypoint is None
    assert app.entries['x'].value == ""


def test_shift_click_inserts_into_nearest_segment(app):
    # A point on the straight-ish first segment (10,10)->(70,70) should land between them.
    path_pt = (40, 40)
    seg, dist = app._nearest_segment(*path_pt)
    assert seg == 0 and dist < app.INSERT_RADIUS
    app.on_click(Click(*path_pt, key='shift'))
    assert coords(app)[1] == path_pt
    assert len(app.waypoints) == 4


def test_shift_click_far_from_path_is_ignored(app):
    app.on_click(Click(10, 140, key='shift'))
    assert len(app.waypoints) == 3


def test_ctrl_snaps_new_and_dragged_points(app):
    app.on_click(Click(100.4, 100.6, key='control'))
    assert coords(app)[-1] == (100, 101)
    app.on_release(None)
    app.on_click(Click(70, 70))
    app.on_drag(Click(55.7, 60.2, key='control'))
    assert coords(app)[1] == (56, 60)


def test_undo_redo_add_drag_delete(app):
    start = coords(app)
    app.on_click(Click(70, 70))
    app.on_drag(Click(75, 80))
    app.on_drag(Click(80, 90))   # one drag = one undo step
    app.on_release(None)
    app.on_click(Click(10, 10, button=3))
    after = coords(app)

    app.undo()
    assert coords(app) == [(10, 10), (80, 90), (130, 10)]
    app.undo()
    assert coords(app) == start
    app.undo()
    assert coords(app) == start[:2]  # undid the last add

    app.redo()
    app.redo()
    app.redo()
    assert coords(app) == after
    app.redo()  # nothing left: no-op
    assert coords(app) == after


def test_click_without_drag_adds_no_history(app):
    depth = len(app.undo_stack)
    app.on_click(Click(70, 70))
    app.on_release(None)
    assert len(app.undo_stack) == depth


def test_new_edit_clears_redo(app):
    app.undo()
    assert app.redo_stack
    app.on_click(Click(20, 120))
    assert not app.redo_stack


def test_drag_tangent_handle_sets_manual_tangent(app):
    app.on_click(Click(70, 70))
    app.on_release(None)
    w = app.selected_waypoint
    hx, hy = app._handle_pos(w)
    app.on_click(Click(hx, hy))
    assert app.drag_mode == 'handle'
    app.on_drag(Click(70, 90))
    app.on_release(None)
    assert w.manual_tangent
    assert (w.dx, w.dy) == pytest.approx((0, 60))
    assert (w.x, w.y) == (70, 70)  # the point itself did not move

    app.undo()
    restored = app.waypoints[1]
    assert not restored.manual_tangent


def test_reset_tangent_returns_to_auto(app):
    app.on_click(Click(70, 70))
    app.on_release(None)
    w = app.selected_waypoint
    app.entries['dx'].value, app.entries['dy'].value = "0", "50"
    app.on_apply()
    assert w.manual_tangent and (w.dx, w.dy) == (0, 50)
    app.reset_tangent()
    assert not w.manual_tangent
    assert (w.dx, w.dy) == pytest.approx((60, 0))  # Catmull-Rom: 0.5 * (next - prev)


def test_apply_position_only_keeps_auto_tangent(app):
    app.on_click(Click(70, 70))
    app.on_release(None)
    app.entries['y'].value = "100"
    app.on_apply()
    w = app.selected_waypoint
    assert w.y == 100 and not w.manual_tangent


def test_escape_deselects(app):
    app.on_key(Key('escape'))
    assert app.selected_waypoint is None
    assert not app.handle_artists


def test_handle_drawn_only_for_selection(app):
    assert len(app.handle_artists) == 2
    assert len(app.dot_artists) == 3
