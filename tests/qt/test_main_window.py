"""MainWindow: toolbar, sidebars, field picker, theme, playback and file prompts.

Dialogs go through MainWindow.ask_* / show_error, which tests replace.
"""
import gc
import json

import shiboken6

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from exporter.binary_exporter import import_trajectory
from planner.fields import DEFAULT_FIELD, FIELDS_DIR, NO_FIELD
from qt_ui.main_window import MainWindow
from qt_ui.theme import THEMES


@pytest.fixture
def win(qtbot, tmp_path):
    w = MainWindow(prefs_path=str(tmp_path / "prefs.json"), config_path=str(tmp_path / "robot.json"),
                   fields_dir=FIELDS_DIR)
    w.errors = []
    w.show_error = lambda title, msg: w.errors.append((title, msg))
    w.ask_discard = lambda: "discard"  # teardown closes the window; never open a real modal
    w.resize(1600, 900)
    # (not qtbot.addWidget: dispose() destroys the window itself)
    w.show()
    qtbot.waitExposed(w)
    for p in [(24, 24), (72, 100), (120, 40)]:
        w.editor.add_waypoint(*p)
    yield w
    dispose(w)


def dispose(w):
    """Close and really destroy a test window, and reset the app-wide theme.

    Leaked windows keep thousands of Qt items alive, which slows every later test.
    """
    w.ask_discard = lambda: "discard"
    w.close()
    w.timer.stop()
    shiboken6.delete(w)  # deleteLater never runs outside a real event loop
    gc.collect()
    QApplication.instance().setStyleSheet("")


def commit(spin, value):
    spin.setValue(value)
    spin.editingFinished.emit()


# ---------- layout ----------

def test_layout_field_is_the_biggest_thing(win):
    fv = win.field_view
    assert fv.width() > win.waypoint_panel.width() + win.robot_panel.width()
    assert fv.height() > win.speed_plot.height() * 2
    assert win.waypoint_panel.x() < fv.x() < win.robot_panel.x()


def test_title_tracks_file_and_changes(win, tmp_path):
    assert win.windowTitle() == "*untitled - PRISM Path Planner"
    win.ask_save_path = lambda kind: str(tmp_path / "auton")
    win.actions["save"].trigger()
    assert win.windowTitle() == "auton - PRISM Path Planner"


# ---------- waypoint list / editor ----------

def test_list_shows_waypoints_and_syncs_selection(win):
    lst = win.waypoint_panel.list
    assert lst.count() == 3
    assert lst.item(1).text().startswith("2")
    lst.setCurrentRow(0)
    assert win.editor.selected is win.editor.waypoints[0]
    win.editor.select(win.editor.waypoints[2])
    assert lst.currentRow() == 2


def test_inspector_disabled_without_selection(win):
    win.editor.select(None)
    assert not win.waypoint_panel.x_spin.isEnabled()
    win.editor.select(win.editor.waypoints[0])
    assert win.waypoint_panel.x_spin.isEnabled()
    assert win.waypoint_panel.x_spin.value() == pytest.approx(24)


def test_spin_commit_is_one_undo_step(win):
    ed = win.editor
    ed.select(ed.waypoints[1])
    depth = len(ed.undo_stack)
    commit(win.waypoint_panel.y_spin, 110)
    assert ed.waypoints[1].y == 110 and len(ed.undo_stack) == depth + 1
    assert not ed.waypoints[1].manual_tangent
    commit(win.waypoint_panel.dy_spin, 25)
    assert ed.waypoints[1].manual_tangent


def test_unchanged_commit_adds_no_history(win):
    ed = win.editor
    ed.select(ed.waypoints[1])
    depth = len(ed.undo_stack)
    win.waypoint_panel.x_spin.editingFinished.emit()
    assert len(ed.undo_stack) == depth


def test_segment_options(win):
    ed, panel = win.editor, win.waypoint_panel
    ed.select(ed.waypoints[0])
    panel.reverse_box.setChecked(True)
    assert ed.waypoints[0].reversed
    commit(panel.cap_spin, 30)
    assert ed.waypoints[0].v_cap == 30
    commit(panel.cap_spin, 0)          # 0 shows "none"
    assert ed.waypoints[0].v_cap is None
    assert "R" in panel.list.item(0).text()


def test_auto_tangent_and_delete_buttons(win):
    ed, panel = win.editor, win.waypoint_panel
    ed.select(ed.waypoints[1])
    commit(panel.dx_spin, 5)
    assert ed.waypoints[1].manual_tangent
    panel.auto_button.click()
    assert not ed.waypoints[1].manual_tangent
    panel.delete_button.click()
    assert len(ed.waypoints) == 2


# ---------- robot panel ----------

def test_robot_settings_apply_and_stats(win, tmp_path):
    rp = win.robot_panel
    before = rp.time_label.text()
    rp.spins["v_max"].setValue(30)
    rp.spins["a_lat_max"].setValue(0)   # "same as accel"
    rp.apply_button.click()
    assert win.editor.config.v_max == 30 and win.editor.config.a_lat_max is None
    assert rp.time_label.text() != before and rp.time_label.text().endswith("s")
    assert json.loads((tmp_path / "robot.json").read_text())["v_max"] == 30


def test_stats_empty_state(qtbot, tmp_path):
    w = MainWindow(prefs_path=str(tmp_path / "p.json"), fields_dir=str(tmp_path / "none"))
    # (not qtbot.addWidget: dispose() destroys the window itself)
    assert w.robot_panel.time_label.text() == "—"
    dispose(w)


# ---------- toolbar ----------

def test_undo_redo_actions(win):
    win.actions["undo"].trigger()
    assert len(win.editor.waypoints) == 2
    win.actions["redo"].trigger()
    assert len(win.editor.waypoints) == 3


def test_delete_action(win):
    win.editor.select(win.editor.waypoints[0])
    win.actions["delete"].trigger()
    assert len(win.editor.waypoints) == 2


def test_export_bin(win, tmp_path):
    target = tmp_path / "red.bin"
    win.ask_save_path = lambda kind: str(target)
    win.actions["export_bin"].trigger()
    assert len(import_trajectory(target)) == len(win.editor.trajectory)


def test_open_bad_file_shows_error(win, tmp_path):
    bad = tmp_path / "bad.path.json"
    bad.write_text("{nope")
    win.ask_discard = lambda: "discard"
    win.ask_open_path = lambda: str(bad)
    win.actions["open"].trigger()
    assert win.errors and len(win.editor.waypoints) == 3


# ---------- field picker ----------

def test_field_picker_default_and_switch(win, tmp_path):
    combo = win.field_combo
    assert combo.currentText() == DEFAULT_FIELD
    assert win.field_view.image_item is not None
    combo.setCurrentText(NO_FIELD)
    assert win.field_view.image_item is None
    assert json.loads((tmp_path / "prefs.json").read_text())["field"] == NO_FIELD


def test_field_picker_add_custom(win, tmp_path):
    import PIL.Image
    img = tmp_path / "practice.png"
    PIL.Image.fromarray((np.random.rand(8, 8, 3) * 255).astype("uint8")).save(img)
    win.ask_image_path = lambda: str(img)
    win.field_combo.setCurrentIndex(win.field_combo.count() - 1)  # "+ Add image…"
    assert win.field_combo.currentText() == "practice"
    assert win.field_view.image_item is not None


# ---------- theme ----------

def test_theme_toggle_applies_and_persists(win, tmp_path):
    assert win.theme_name == "dark"
    win.actions["theme"].trigger()
    assert win.theme_name == "light"
    assert THEMES["light"].panel in QApplication.instance().styleSheet()
    assert win.field_view.theme is THEMES["light"] and win.speed_plot.theme is THEMES["light"]
    assert json.loads((tmp_path / "prefs.json").read_text())["theme"] == "light"


def test_theme_restored_on_start(qtbot, tmp_path):
    prefs = tmp_path / "prefs.json"
    prefs.write_text(json.dumps({"theme": "light"}))
    w = MainWindow(prefs_path=str(prefs), fields_dir=str(tmp_path / "none"))
    # (not qtbot.addWidget: dispose() destroys the window itself)
    assert w.theme_name == "light"
    dispose(w)


# ---------- playback / scrubbing / status ----------

def test_play_and_stop(win):
    win.actions["play"].trigger()
    assert win.playback.playing and win.actions["play"].text() == "Stop"
    win._play_tick(now=win.playback.start_time + 0.5)
    assert win.field_view.robot_item.isVisible()
    win._play_tick(now=win.playback.start_time + 1e6)
    assert not win.playback.playing and win.actions["play"].text() == "Play"
    assert not win.field_view.robot_item.isVisible()


def test_speed_hover_moves_robot(win):
    win.speed_plot.time_hovered.emit(1.0)
    assert win.field_view.robot_item.isVisible()
    win.speed_plot.time_hovered.emit(None)
    assert not win.field_view.robot_item.isVisible()


def test_status_bar_cursor_and_hint(win):
    win.field_view.cursor_moved.emit(12.34, 56.78)
    assert win.cursor_label.text() == "x 12.3   y 56.8"
    win.field_view.hint_changed.emit("hello")
    assert win.hint_label.text() == "hello"


def test_speed_strip_toggle(win):
    win.actions["toggle_speed"].trigger()
    assert not win.speed_plot.isVisible()
    win.actions["toggle_speed"].trigger()
    assert win.speed_plot.isVisible()


# ---------- closing ----------

@pytest.mark.parametrize("answer,accepted", [("cancel", False), ("discard", True)])
def test_close_prompt(win, answer, accepted):
    win.ask_discard = lambda: answer
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted() is accepted
    win.ask_discard = lambda: "discard"  # let teardown close it; a window left open steals later tests' mouse events


def test_close_save_writes_file(win, tmp_path):
    win.ask_discard = lambda: "save"
    win.ask_save_path = lambda kind: str(tmp_path / "keep")
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted() and (tmp_path / "keep.path.json").exists()


def test_no_prompt_when_clean(win, tmp_path):
    win.ask_save_path = lambda kind: str(tmp_path / "a")
    win.actions["save"].trigger()
    win.ask_discard = lambda: pytest.fail("should not ask")
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()


def test_cancelled_save_dialog_keeps_work(win):
    win.ask_discard = lambda: "save"
    win.ask_save_path = lambda kind: None   # user closed the save dialog
    win.actions["new"].trigger()
    assert len(win.editor.waypoints) == 3


def test_broken_custom_field_image_shows_error(win, tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_text("not an image")
    win.ask_image_path = lambda: str(bad)
    win.field_combo.setCurrentIndex(win.field_combo.count() - 1)
    assert win.errors and "Could not load" in win.errors[-1][1]
    assert win.field_view.image_item is None
