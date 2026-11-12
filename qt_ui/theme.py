"""Light and dark themes: color tokens, the Qt stylesheet, and the speed color ramp.

Every color the UI uses comes from a Theme, so switching themes is just
re-applying stylesheet(theme) and redrawing with the new tokens.
"""
import json
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str           # window background
    panel: str             # sidebars, toolbar
    panel_alt: str         # inputs, list rows
    border: str
    text: str
    muted: str             # secondary text, axis labels
    grid: str              # field grid / plot grid
    accent: str            # primary buttons, selection
    accent_text: str       # text on accent
    field_surface: str     # field background when no image
    path_casing: str       # outline under the path so it reads on any field image
    waypoint: str
    waypoint_outline: str
    selected: str
    handle: str
    robot: str
    danger: str
    speed_ramp: Tuple[str, ...]  # slow -> fast, one blue hue


# One-hue blue ramp (dataviz sequential). Dark: slow is dark and recedes, fast is light.
# Light: flipped, so fast is the darkest; the lightest step still clears 2:1 on white.
DARK = Theme(
    name="dark",
    surface="#0f1115", panel="#171a21", panel_alt="#1f232c", border="#2c313c",
    text="#e6e8ec", muted="#9aa1ad", grid="#2a2f39",
    accent="#35c9a8", accent_text="#06231d",
    field_surface="#0d1117", path_casing="#0d1117",
    waypoint="#f2f4f7", waypoint_outline="#0f1115", selected="#35c9a8", handle="#9aa1ad",
    robot="#f2f4f7", danger="#ff6b6b",
    speed_ramp=("#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"),
)

LIGHT = Theme(
    name="light",
    surface="#eef0f3", panel="#ffffff", panel_alt="#f4f5f7", border="#d5d9e0",
    text="#1b1f27", muted="#5c6370", grid="#c9ced6",
    accent="#0b7a63", accent_text="#ffffff",
    field_surface="#e4e7ec", path_casing="#ffffff",
    waypoint="#ffffff", waypoint_outline="#1b1f27", selected="#0b7a63", handle="#5c6370",
    robot="#1b1f27", danger="#c62828",
    speed_ramp=("#86b6ef", "#5598e7", "#3987e5", "#256abf", "#184f95", "#0d366b"),
)

THEMES = {"dark": DARK, "light": LIGHT}
DEFAULT_THEME = "dark"


# ---------- color math ----------

def _rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def relative_luminance(hex_color):
    """WCAG 2 relative luminance."""
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 2 contrast ratio between two colors."""
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def speed_color(theme, velocity, v_max):
    """Ramp color for |velocity| (reverse speed colors like forward speed), clamped to v_max."""
    ramp = theme.speed_ramp
    f = 0.0 if v_max <= 0 else min(abs(velocity) / v_max, 1.0)
    pos = f * (len(ramp) - 1)
    i = min(int(pos), len(ramp) - 2)
    t = pos - i
    a, b = _rgb(ramp[i]), _rgb(ramp[i + 1])
    return _hex(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))


def toggled(name):
    return "light" if name == "dark" else "dark"


# ---------- persistence (shares ui_prefs.json with the field picker) ----------

def _read(prefs_path):
    if not prefs_path:
        return {}
    try:
        with open(prefs_path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_theme_name(prefs_path):
    name = _read(prefs_path).get("theme")
    return name if name in THEMES else DEFAULT_THEME


def save_theme_name(prefs_path, name):
    if not prefs_path:
        return
    data = _read(prefs_path)
    data["theme"] = name
    try:
        with open(prefs_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


# ---------- Qt stylesheet ----------

def stylesheet(t):
    return f"""
QMainWindow, QWidget#central {{ background: {t.surface}; color: {t.text}; }}
QWidget {{ color: {t.text}; font-size: 10pt; }}
QToolBar {{ background: {t.panel}; border: none; border-bottom: 1px solid {t.border}; spacing: 4px; padding: 4px 8px; }}
QToolBar::separator {{ background: {t.border}; width: 1px; margin: 4px 6px; }}
QToolButton {{ background: transparent; color: {t.text}; border: 1px solid transparent; border-radius: 6px; padding: 5px 10px; }}
QToolButton:hover {{ background: {t.panel_alt}; border-color: {t.border}; }}
QToolButton:checked {{ background: {t.accent}; color: {t.accent_text}; }}
QToolButton:disabled {{ color: {t.muted}; }}
QFrame#sidebar {{ background: {t.panel}; border: none; }}
QFrame#sidebar[side="left"] {{ border-right: 1px solid {t.border}; }}
QFrame#sidebar[side="right"] {{ border-left: 1px solid {t.border}; }}
QLabel#section {{ color: {t.muted}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; padding-top: 6px; }}
QLabel#stat {{ font-size: 15pt; font-weight: 600; }}
QLabel#statLabel {{ color: {t.muted}; font-size: 8pt; }}
QLabel#empty {{ color: {t.muted}; }}
QPushButton {{ background: {t.panel_alt}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px; padding: 6px 10px; }}
QPushButton:hover {{ border-color: {t.accent}; }}
QPushButton:disabled {{ color: {t.muted}; }}
QPushButton#primary {{ background: {t.accent}; color: {t.accent_text}; border-color: {t.accent}; font-weight: 600; }}
QDoubleSpinBox, QLineEdit, QComboBox {{ background: {t.panel_alt}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px; padding: 4px 6px; selection-background-color: {t.accent}; selection-color: {t.accent_text}; }}
QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {t.accent}; }}
QDoubleSpinBox:disabled, QLineEdit:disabled {{ color: {t.muted}; }}
QComboBox QAbstractItemView {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.border}; selection-background-color: {t.accent}; selection-color: {t.accent_text}; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {t.border}; border-radius: 3px; background: {t.panel_alt}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QListWidget {{ background: {t.panel_alt}; border: 1px solid {t.border}; border-radius: 6px; outline: none; }}
QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {t.accent}; color: {t.accent_text}; }}
QListWidget::item:hover:!selected {{ background: {t.panel}; }}
QStatusBar {{ background: {t.panel}; color: {t.muted}; border-top: 1px solid {t.border}; }}
QStatusBar QLabel {{ color: {t.muted}; padding: 0 8px; }}
QSplitter::handle {{ background: {t.border}; }}
QToolTip {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
QMenu {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.border}; }}
QMenu::item:selected {{ background: {t.accent}; color: {t.accent_text}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
