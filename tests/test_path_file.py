import json

import pytest

import ui.app as app_module
from conftest import Click
from exporter.path_file import load_path, save_path
from ui.waypoint import Waypoint


def wp(x, y, dx, dy, manual=False):
    w = Waypoint(x, y, dx, dy)
    w.manual_tangent = manual
    return w


def test_roundtrip(tmp_path):
    path = tmp_path / "red.path.json"
    save_path(path, [wp(1.5, 2, 3, 4), wp(10, 20, -1, 0.25, manual=True)])
    assert load_path(path) == [
        {"x": 1.5, "y": 2, "dx": 3, "dy": 4, "manual_tangent": False},
        {"x": 10, "y": 20, "dx": -1, "dy": 0.25, "manual_tangent": True},
    ]


@pytest.mark.parametrize("content,message", [
    ("{oops", "not valid JSON"),
    (json.dumps({"format": "other", "version": 1, "waypoints": []}), "not a PRISM path"),
    (json.dumps({"format": "prism-path", "version": 99, "waypoints": []}), "version"),
    (json.dumps({"format": "prism-path", "version": 1}), "missing waypoint"),
    (json.dumps({"format": "prism-path", "version": 1, "waypoints": [{"x": 1, "y": 2}]}), "waypoint 1"),
    (json.dumps({"format": "prism-path", "version": 1,
                 "waypoints": [{"x": "nan", "y": 0, "dx": 0, "dy": 0}]}), "non-finite"),
])
def test_rejects_bad_files(tmp_path, content, message):
    path = tmp_path / "bad.path.json"
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        load_path(path)


# ---------- App integration ----------

@pytest.fixture
def ui(make_app, monkeypatch, tmp_path):
    """App plus controllable file dialogs and the yes/no/cancel prompt."""
    state = {"save_as": str(tmp_path / "auton"), "open": None, "answer": True, "prompts": 0}

    def ask(*_):
        state["prompts"] += 1
        return state["answer"]

    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **kw: state["save_as"])
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **kw: state["open"])
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", ask)
    app, _, _ = make_app()
    return app, state


def add_points(app, pts=((10, 10), (70, 70), (130, 10))):
    for p in pts:
        app.on_click(Click(*p))
    app.on_release(None)


def test_new_app_is_clean(ui):
    app, _ = ui
    assert not app.is_dirty()


def test_save_as_adds_extension_and_marks_clean(ui, tmp_path):
    app, state = ui
    add_points(app)
    assert app.is_dirty()
    assert app.save() is True
    assert app.file_path == str(tmp_path / "auton.path.json")
    assert not app.is_dirty()
    assert len(load_path(app.file_path)) == 3


def test_undo_back_to_saved_state_is_clean(ui):
    app, _ = ui
    add_points(app)
    app.save()
    app.on_click(Click(20, 120))
    assert app.is_dirty()
    app.undo()
    assert not app.is_dirty()


def test_selection_alone_is_not_a_change(ui):
    app, _ = ui
    add_points(app)
    app.save()
    app.on_click(Click(70, 70))
    app.on_release(None)
    assert not app.is_dirty()


def test_open_replaces_waypoints_and_clears_history(ui, tmp_path):
    app, state = ui
    path = tmp_path / "skills.path.json"
    save_path(path, [wp(5, 5, 1, 0), wp(50, 5, 1, 0, manual=True)])
    add_points(app)
    app.save()

    state["open"] = str(path)
    app.open_path()
    assert [(w.x, w.y, w.manual_tangent) for w in app.waypoints] == [(5, 5, False), (50, 5, True)]
    assert app.file_path == str(path)
    assert not app.undo_stack and not app.redo_stack
    assert not app.is_dirty()
    assert app._path_stem() == "skills"


def test_open_bad_file_shows_error_and_keeps_work(ui, tmp_path, dialogs):
    app, state = ui
    add_points(app)
    app.save()
    bad = tmp_path / "bad.path.json"
    bad.write_text("{nope")
    state["open"] = str(bad)
    app.open_path()
    assert dialogs and "Could not open" in dialogs[0][1]
    assert len(app.waypoints) == 3


def test_cancel_on_unsaved_prompt_keeps_work(ui):
    app, state = ui
    add_points(app)
    state["answer"] = None  # Cancel
    app.new_path()
    assert len(app.waypoints) == 3 and state["prompts"] == 1


def test_dont_save_discards(ui):
    app, state = ui
    add_points(app)
    state["answer"] = False  # No
    app.new_path()
    assert app.waypoints == [] and app.file_path is None and not app.is_dirty()


def test_yes_saves_before_new(ui, tmp_path):
    app, state = ui
    add_points(app)
    state["answer"] = True
    app.new_path()
    assert app.waypoints == []
    assert len(load_path(tmp_path / "auton.path.json")) == 3


def test_cancelled_save_dialog_aborts_new(ui):
    app, state = ui
    add_points(app)
    state["answer"] = True
    state["save_as"] = ""  # user closed the save dialog
    app.new_path()
    assert len(app.waypoints) == 3


def test_no_prompt_when_clean(ui):
    app, state = ui
    app.new_path()
    assert state["prompts"] == 0


def test_export_defaults_to_path_name(ui, monkeypatch, tmp_path):
    app, state = ui
    add_points(app)
    app.save()
    seen = {}
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **kw: seen.update(kw) or "")
    app.on_export_header()
    assert seen["initialfile"] == "auton.hpp"
