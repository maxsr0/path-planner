import json

import pytest

from exporter.path_file import load_path, save_path
from planner.waypoint import Waypoint


def wp(x, y, dx, dy, manual=False, reversed=False, v_cap=None):
    return Waypoint(x, y, dx, dy, manual, reversed, v_cap)


def test_roundtrip(tmp_path):
    path = tmp_path / "red.path.json"
    save_path(path, [wp(1.5, 2, 3, 4, reversed=True, v_cap=30), wp(10, 20, -1, 0.25, manual=True)])
    assert load_path(path) == [
        {"x": 1.5, "y": 2, "dx": 3, "dy": 4, "manual_tangent": False, "reversed": True, "v_cap": 30},
        {"x": 10, "y": 20, "dx": -1, "dy": 0.25, "manual_tangent": True, "reversed": False, "v_cap": None},
    ]


def test_files_without_segment_options_still_load(tmp_path):
    path = tmp_path / "old.path.json"
    path.write_text(json.dumps({"format": "prism-path", "version": 1,
                                "waypoints": [{"x": 0, "y": 0, "dx": 1, "dy": 0}]}))
    assert load_path(path)[0]["reversed"] is False
    assert load_path(path)[0]["v_cap"] is None


@pytest.mark.parametrize("content,message", [
    ("{oops", "not valid JSON"),
    (json.dumps({"format": "other", "version": 1, "waypoints": []}), "not a PRISM path"),
    (json.dumps({"format": "prism-path", "version": 99, "waypoints": []}), "version"),
    (json.dumps({"format": "prism-path", "version": 1}), "missing waypoint"),
    (json.dumps({"format": "prism-path", "version": 1, "waypoints": [{"x": 1, "y": 2}]}), "waypoint 1"),
    (json.dumps({"format": "prism-path", "version": 1,
                 "waypoints": [{"x": "nan", "y": 0, "dx": 0, "dy": 0}]}), "non-finite"),
    (json.dumps({"format": "prism-path", "version": 1,
                 "waypoints": [{"x": 0, "y": 0, "dx": 0, "dy": 0, "v_cap": -5}]}), "speed cap"),
])
def test_rejects_bad_files(tmp_path, content, message):
    path = tmp_path / "bad.path.json"
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        load_path(path)


# ---------- App integration ----------
