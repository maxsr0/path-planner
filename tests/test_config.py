import json

import matplotlib
matplotlib.use("Agg")
import pytest

import ui.app as app_module
from profiler.config import RobotConfig, load_config, save_config
from ui.app import App
from ui.field import create_field_figure


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_):
        self.value = ""

    def insert(self, _, value):
        self.value = str(value)


class FakeVar:
    value = None

    def set(self, value):
        self.value = value


class FakeCanvas:
    def draw(self):
        pass


class Click:
    def __init__(self, x, y, button=1):
        self.xdata, self.ydata, self.button = x, y, button


@pytest.fixture
def errors(monkeypatch):
    shown = []
    monkeypatch.setattr(app_module.messagebox, "showerror", lambda *a: shown.append(a))
    monkeypatch.setattr(app_module.messagebox, "showwarning", lambda *a: shown.append(a))
    return shown


def make_app(config_path=None):
    fig, ax = create_field_figure()
    entries = {k: FakeEntry() for k in ("x", "y", "dx", "dy")}
    settings = {name: FakeEntry() for name, _ in App.SETTINGS_FIELDS}
    stats = FakeVar()
    return App(None, fig, ax, FakeCanvas(), entries, settings, stats, config_path), settings, stats


@pytest.mark.parametrize("kwargs", [
    {"v_max": 0}, {"a_max": -1}, {"spacing": 0}, {"track_width": -2},
    {"a_lat_max": 0}, {"v_max": float("nan")}, {"v_max": "fast"},
])
def test_validate_rejects_bad_values(kwargs):
    with pytest.raises(ValueError):
        RobotConfig(**kwargs).validate()


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "robot.json"
    cfg = RobotConfig(v_max=70, a_max=45, a_lat_max=None, track_width=11.5, spacing=0.25)
    save_config(cfg, path)
    loaded, error = load_config(path)
    assert error is None
    assert loaded == cfg


def test_load_missing_uses_defaults(tmp_path):
    cfg, error = load_config(tmp_path / "nope.json")
    assert cfg == RobotConfig() and error is None


def test_load_corrupt_falls_back_with_message(tmp_path):
    path = tmp_path / "robot.json"
    path.write_text("{not json")
    cfg, error = load_config(path)
    assert cfg == RobotConfig() and "Using defaults" in error

    path.write_text(json.dumps({"v_max": -5}))
    cfg, error = load_config(path)
    assert cfg == RobotConfig() and error


def test_panel_loads_saved_config(tmp_path, errors):
    path = tmp_path / "robot.json"
    save_config(RobotConfig(v_max=70, track_width=12), path)
    app, settings, _ = make_app(str(path))
    assert settings["v_max"].value == "70"
    assert settings["track_width"].value == "12"
    assert settings["a_lat_max"].value == ""
    assert not errors


def test_apply_settings_updates_and_saves(tmp_path, errors):
    path = tmp_path / "robot.json"
    app, settings, stats = make_app(str(path))
    for p in [(10, 10), (70, 80), (130, 20)]:
        app.on_click(Click(*p))
    slow_time = None

    settings["v_max"].value = "30"
    settings["a_lat_max"].value = ""
    settings["track_width"].value = "12"
    app.on_apply_settings()
    assert not errors
    assert app.config.v_max == 30 and app.config.a_lat_max is None and app.config.track_width == 12
    assert json.loads(path.read_text())["v_max"] == 30
    slow_time = float(stats.value.split("time")[1].split("s")[0])

    settings["v_max"].value = "90"
    app.on_apply_settings()
    fast_time = float(stats.value.split("time")[1].split("s")[0])
    assert fast_time < slow_time


def test_apply_settings_rejects_bad_input_and_keeps_config(tmp_path, errors):
    path = tmp_path / "robot.json"
    app, settings, _ = make_app(str(path))
    before = app.config
    settings["a_max"].value = "abc"
    app.on_apply_settings()
    assert errors and "max accel" in errors[0][1]
    assert app.config == before
    assert not path.exists()


def test_stats_placeholder_with_few_waypoints(errors):
    app, _, stats = make_app()
    app.draw_all()
    assert stats.value == "place 2+ waypoints"
