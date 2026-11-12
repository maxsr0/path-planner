"""Light/dark theme tokens, stylesheet, speed ramp and persistence (no Qt needed)."""
import json
import re

import pytest

from qt_ui.theme import (THEMES, Theme, contrast, load_theme_name, relative_luminance,
                         save_theme_name, speed_color, stylesheet, toggled)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@pytest.mark.parametrize("name", ["dark", "light"])
def test_every_token_is_a_hex_color(name):
    theme = THEMES[name]
    for field, value in vars(theme).items():
        if field in ("name", "speed_ramp"):
            continue
        assert HEX.match(value), f"{name}.{field} = {value!r}"
    assert len(theme.speed_ramp) >= 4 and all(HEX.match(c) for c in theme.speed_ramp)


def test_both_themes_define_the_same_tokens():
    assert set(vars(THEMES["dark"])) == set(vars(THEMES["light"]))


@pytest.mark.parametrize("name", ["dark", "light"])
def test_text_is_readable(name):
    t = THEMES[name]
    assert contrast(t.text, t.panel) >= 4.5
    assert contrast(t.text, t.surface) >= 4.5
    assert contrast(t.muted, t.panel) >= 3.0
    assert contrast(t.accent_text, t.accent) >= 4.5   # text on accent buttons


def test_dark_ramp_gets_lighter_with_speed():
    lum = [relative_luminance(c) for c in THEMES["dark"].speed_ramp]
    assert lum == sorted(lum) and lum[0] < lum[-1]


def test_light_ramp_gets_darker_with_speed():
    lum = [relative_luminance(c) for c in THEMES["light"].speed_ramp]
    assert lum == sorted(lum, reverse=True) and lum[0] > lum[-1]


@pytest.mark.parametrize("name", ["dark", "light"])
def test_speed_color_endpoints_and_clamping(name):
    t = THEMES[name]
    assert speed_color(t, 0, 60).lower() == t.speed_ramp[0].lower()
    assert speed_color(t, 60, 60).lower() == t.speed_ramp[-1].lower()
    assert speed_color(t, 999, 60).lower() == t.speed_ramp[-1].lower()
    assert speed_color(t, -60, 60).lower() == t.speed_ramp[-1].lower()  # reverse speed uses |v|
    assert HEX.match(speed_color(t, 17, 60))


@pytest.mark.parametrize("name", ["dark", "light"])
def test_stylesheet_uses_theme_colors(name):
    t = THEMES[name]
    qss = stylesheet(t)
    for selector in ("QMainWindow", "QToolBar", "QPushButton", "QDoubleSpinBox", "QListWidget", "QStatusBar"):
        assert selector in qss
    for color in (t.panel, t.text, t.accent, t.border):
        assert color.lower() in qss.lower()


def test_toggle():
    assert toggled("dark") == "light" and toggled("light") == "dark"


def test_theme_name_persists(tmp_path):
    prefs = tmp_path / "prefs.json"
    prefs.write_text(json.dumps({"field": "VURC 2027 - Override"}))
    save_theme_name(str(prefs), "light")
    assert load_theme_name(str(prefs)) == "light"
    assert json.loads(prefs.read_text())["field"] == "VURC 2027 - Override"  # other prefs kept


@pytest.mark.parametrize("content", [None, "{bad json", json.dumps({"theme": "neon"}), json.dumps([1, 2])])
def test_theme_name_defaults_to_dark(tmp_path, content):
    prefs = tmp_path / "prefs.json"
    if content is not None:
        prefs.write_text(content)
    assert load_theme_name(str(prefs)) == "dark"
    assert load_theme_name(None) == "dark"
