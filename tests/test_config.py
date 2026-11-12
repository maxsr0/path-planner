import json

import pytest

from conftest import Click
from profiler.config import RobotConfig, load_config, save_config


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


def test_panel_loads_saved_config(tmp_path, make_app, dialogs):
    path = tmp_path / "robot.json"
    save_config(RobotConfig(v_max=70, track_width=12), path)
    app, settings, _ = make_app(str(path))
    assert settings["v_max"].value == "70"
    assert settings["track_width"].value == "12"
    assert settings["a_lat_max"].value == ""
    assert not dialogs


def test_apply_settings_updates_and_saves(tmp_path, make_app, dialogs):
    path = tmp_path / "robot.json"
    app, settings, stats = make_app(str(path))
    for p in [(10, 10), (70, 80), (130, 20)]:
        app.on_click(Click(*p))
    slow_time = None

    settings["v_max"].value = "30"
    settings["a_lat_max"].value = ""
    settings["track_width"].value = "12"
    app.on_apply_settings()
    assert not dialogs
    assert app.config.v_max == 30 and app.config.a_lat_max is None and app.config.track_width == 12
    assert json.loads(path.read_text())["v_max"] == 30
    slow_time = float(stats.value.split("time")[1].split("s")[0])

    settings["v_max"].value = "90"
    app.on_apply_settings()
    fast_time = float(stats.value.split("time")[1].split("s")[0])
    assert fast_time < slow_time


def test_apply_settings_rejects_bad_input_and_keeps_config(tmp_path, make_app, dialogs):
    path = tmp_path / "robot.json"
    app, settings, _ = make_app(str(path))
    before = app.config
    settings["a_max"].value = "abc"
    app.on_apply_settings()
    assert dialogs and "max accel" in dialogs[0][1]
    assert app.config == before
    assert not path.exists()


def test_stats_placeholder_with_few_waypoints(make_app, dialogs):
    app, _, stats = make_app()
    app.draw_all()
    assert stats.value == "place 2+ waypoints"
