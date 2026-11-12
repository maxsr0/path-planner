import json

import pytest

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
