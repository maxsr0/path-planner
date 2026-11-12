"""Editor: the toolkit-free path editing model (no Tk, no Qt)."""
import json
import math

import pytest

from planner.editor import Editor, Playback
from planner.waypoint import Waypoint
from exporter.path_file import load_path, save_path
from profiler.config import RobotConfig


def coords(ed):
    return [(round(w.x, 6), round(w.y, 6)) for w in ed.waypoints]


@pytest.fixture
def ed():
    e = Editor()
    for p in [(10, 10), (70, 70), (130, 10)]:
        e.add_waypoint(*p)
    return e


# ---------- adding / selecting ----------

def test_add_appends_and_selects(ed):
    assert coords(ed) == [(10, 10), (70, 70), (130, 10)]
    assert ed.selected is ed.waypoints[-1]


def test_add_with_snap():
    e = Editor()
    e.add_waypoint(100.4, 100.6, snap=True)
    assert coords(e) == [(100, 101)]


def test_select_adds_no_history(ed):
    depth = len(ed.undo_stack)
    ed.select(ed.waypoints[0])
    assert ed.selected is ed.waypoints[0]
    assert len(ed.undo_stack) == depth


def test_change_listeners_are_notified(ed):
    seen = []
    ed.subscribe(seen.append)
    ed.select(ed.waypoints[0])
    ed.add_waypoint(20, 120)
    assert "selection" in seen and "path" in seen


# ---------- hit testing ----------

def test_hit_test_point_and_handle(ed):
    w = ed.waypoints[1]
    assert ed.hit_test(71, 71) == ("point", w)
    ed.select(w)
    hx, hy = ed.handle_pos(w)
    assert ed.hit_test(hx, hy) == ("handle", w)
    assert ed.hit_test(40, 130) is None


def test_hit_test_custom_radius(ed):
    assert ed.hit_test(73.5, 70) == ("point", ed.waypoints[1])
    assert ed.hit_test(73.5, 70, radius=1.0) is None


def test_handle_only_for_selected(ed):
    ed.select(None)
    hx, hy = ed.handle_pos(ed.waypoints[1])
    assert ed.hit_test(hx, hy) != ("handle", ed.waypoints[1])


# ---------- tangents ----------

def test_auto_tangents_catmull_rom(ed):
    first, mid, last = ed.waypoints
    assert (first.dx, first.dy) == (60, 60)
    assert (mid.dx, mid.dy) == pytest.approx((60, 0))
    assert (last.dx, last.dy) == (60, -60)


def test_manual_endpoint_tangent_survives_moves(ed):
    first = ed.waypoints[0]
    ed.update_waypoint(first, dx=0, dy=50)
    assert first.manual_tangent
    ed.begin_drag(ed.waypoints[1], "point")
    ed.drag_to(80, 90)
    ed.end_drag()
    assert (first.dx, first.dy) == (0, 50)


def test_update_position_only_keeps_auto_tangent(ed):
    mid = ed.waypoints[1]
    ed.update_waypoint(mid, y=100)
    assert mid.y == 100 and not mid.manual_tangent


def test_reset_tangent(ed):
    mid = ed.waypoints[1]
    ed.update_waypoint(mid, dx=0, dy=50)
    ed.reset_tangent(mid)
    assert not mid.manual_tangent
    assert (mid.dx, mid.dy) == pytest.approx((60, 0))


# ---------- drag ----------

def test_drag_point_is_one_undo_step(ed):
    depth = len(ed.undo_stack)
    ed.begin_drag(ed.waypoints[1], "point")
    ed.drag_to(75, 80)
    ed.drag_to(80, 90)
    ed.end_drag()
    assert len(ed.undo_stack) == depth + 1
    assert coords(ed)[1] == (80, 90)
    ed.undo()
    assert coords(ed)[1] == (70, 70)


def test_click_without_move_adds_no_history(ed):
    depth = len(ed.undo_stack)
    ed.begin_drag(ed.waypoints[1], "point")
    ed.end_drag()
    assert len(ed.undo_stack) == depth


def test_drag_with_snap(ed):
    ed.begin_drag(ed.waypoints[1], "point")
    ed.drag_to(55.7, 60.2, snap=True)
    ed.end_drag()
    assert coords(ed)[1] == (56, 60)


def test_drag_handle_sets_manual_tangent(ed):
    w = ed.waypoints[1]
    ed.begin_drag(w, "handle")
    ed.drag_to(70, 90)
    ed.end_drag()
    assert w.manual_tangent
    assert (w.dx, w.dy) == pytest.approx((0, 60))
    assert (w.x, w.y) == (70, 70)
    ed.undo()
    assert not ed.waypoints[1].manual_tangent


# ---------- insert / delete ----------

def test_insert_into_nearest_segment(ed):
    w = ed.insert_waypoint(40, 40)
    assert w is not None and coords(ed)[1] == (40, 40) and len(ed.waypoints) == 4
    assert ed.selected is w


def test_insert_far_from_path_is_ignored(ed):
    assert ed.insert_waypoint(10, 140) is None
    assert len(ed.waypoints) == 3


def test_delete_retangents_neighbors(ed):
    ed.delete_waypoint(ed.waypoints[1])
    assert coords(ed) == [(10, 10), (130, 10)]
    assert (ed.waypoints[0].dx, ed.waypoints[0].dy) == (120, 0)


def test_delete_selected_clears_selection(ed):
    ed.delete_waypoint()
    assert ed.selected is None and len(ed.waypoints) == 2


# ---------- undo / redo ----------

def test_undo_redo_sequence(ed):
    start = coords(ed)
    ed.add_waypoint(20, 120)
    ed.delete_waypoint(ed.waypoints[0])
    after = coords(ed)
    ed.undo()
    ed.undo()
    assert coords(ed) == start
    ed.redo()
    ed.redo()
    assert coords(ed) == after
    ed.redo()  # nothing left
    assert coords(ed) == after


def test_new_edit_clears_redo(ed):
    ed.undo()
    assert ed.redo_stack
    ed.add_waypoint(20, 120)
    assert not ed.redo_stack


# ---------- segment options ----------

def test_reverse_flips_auto_tangent_and_velocity(ed):
    first = ed.waypoints[0]
    ed.update_waypoint(first, reversed=True)
    assert (first.dx, first.dy) == (-60, -60)
    assert all(p.velocity <= 1e-9 for p in ed.trajectory if p.x < 69)


def test_speed_cap_and_clear(ed):
    first = ed.waypoints[0]
    ed.update_waypoint(first, v_cap=15)
    assert max(p.velocity for p in ed.trajectory if p.x < 69) <= 15 + 1e-9
    ed.update_waypoint(first, v_cap=None)
    assert first.v_cap is None


@pytest.mark.parametrize("cap", [0, -3, float("nan")])
def test_bad_speed_cap_rejected(ed, cap):
    with pytest.raises(ValueError):
        ed.update_waypoint(ed.waypoints[0], v_cap=cap)
    assert ed.waypoints[0].v_cap is None


def test_update_is_one_undo_step(ed):
    depth = len(ed.undo_stack)
    ed.update_waypoint(ed.waypoints[0], x=12, y=14, reversed=True, v_cap=20)
    assert len(ed.undo_stack) == depth + 1


# ---------- trajectory / stats ----------

def test_trajectory_empty_until_two_points():
    e = Editor()
    assert e.trajectory == [] and e.stats() is None
    e.add_waypoint(0, 0)
    assert e.trajectory == []


def test_stats(ed):
    s = ed.stats()
    assert s["time"] == pytest.approx(ed.trajectory[-1].timestamp)
    assert s["length"] > 0
    assert s["peak"] == pytest.approx(max(abs(p.velocity) for p in ed.trajectory))


def test_set_config_validates_and_updates(ed):
    before = ed.stats()["time"]
    ed.set_config(RobotConfig(v_max=30, a_max=10))
    assert ed.stats()["time"] > before
    with pytest.raises(ValueError):
        ed.set_config(RobotConfig(v_max=-1))
    assert ed.config.v_max == 30


def test_config_file_roundtrip(tmp_path):
    path = tmp_path / "robot.json"
    e = Editor(config_path=str(path))
    e.set_config(RobotConfig(v_max=70, track_width=12))
    again = Editor(config_path=str(path))
    assert again.config.v_max == 70 and again.config.track_width == 12
    assert again.config_error is None


def test_corrupt_config_reports_error(tmp_path):
    path = tmp_path / "robot.json"
    path.write_text("{oops")
    e = Editor(config_path=str(path))
    assert e.config == RobotConfig() and "Using defaults" in e.config_error


# ---------- files / dirty ----------

def test_dirty_tracking(ed, tmp_path):
    assert ed.is_dirty()
    ed.save(str(tmp_path / "a.path.json"))
    assert not ed.is_dirty()
    ed.select(ed.waypoints[0])
    assert not ed.is_dirty()           # selection is not a change
    ed.add_waypoint(20, 120)
    assert ed.is_dirty()
    ed.undo()
    assert not ed.is_dirty()           # back to saved state


def test_save_adds_extension_and_stem(ed, tmp_path):
    ed.save(str(tmp_path / "auton"))
    assert ed.file_path.endswith("auton.path.json")
    assert ed.path_stem() == "auton"
    assert len(load_path(ed.file_path)) == 3


def test_load_replaces_and_clears_history(ed, tmp_path):
    path = tmp_path / "skills.path.json"
    save_path(path, [Waypoint(5, 5, 1, 0), Waypoint(50, 5, 1, 0, True, True, 20)])
    ed.load(str(path))
    assert [(w.x, w.manual_tangent, w.reversed, w.v_cap) for w in ed.waypoints] == \
        [(5, False, False, None), (50, True, True, 20)]
    assert not ed.undo_stack and not ed.redo_stack and not ed.is_dirty()
    assert ed.selected is None and ed.path_stem() == "skills"


def test_load_bad_file_raises_and_keeps_work(ed, tmp_path):
    bad = tmp_path / "bad.path.json"
    bad.write_text("{nope")
    with pytest.raises(ValueError):
        ed.load(str(bad))
    assert len(ed.waypoints) == 3


def test_new_clears(ed):
    ed.new()
    assert ed.waypoints == [] and ed.file_path is None and not ed.is_dirty()
    assert ed.path_stem() == "untitled"


# ---------- playback ----------

def test_playback_clock(ed):
    pb = Playback(ed)
    assert not pb.playing
    pb.start(now=100.0)
    assert pb.playing
    assert pb.time(now=100.5) == pytest.approx(0.5)
    assert pb.time(now=100.0 + ed.trajectory[-1].timestamp + 1) is None   # finished
    assert not pb.playing


def test_playback_needs_a_path():
    pb = Playback(Editor())
    pb.start(now=0)
    assert not pb.playing


def test_robot_pose_at(ed):
    x, y, theta, v = ed.pose_at(0.0)
    assert (x, y) == pytest.approx((10, 10))
    assert ed.pose_at(1e9)[:2] == pytest.approx((130, 10))
