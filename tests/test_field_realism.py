import json
import math

import numpy as np
import pytest

import ui.app as app_module
from conftest import Click
from profiler.config import RobotConfig
from profiler.trajectory import generate_trajectory

CFG = RobotConfig(v_max=60, a_max=60, spacing=0.25)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def heading_rate_matches_omega(traj):
    """d(theta)/dt from consecutive points should match the exported omega."""
    for a, b in zip(traj[1:-2], traj[2:-1]):
        dt = b.timestamp - a.timestamp
        if dt <= 1e-6 or a.velocity == 0 or b.velocity == 0:
            continue
        rate = wrap(b.theta - a.theta) / dt
        assert rate == pytest.approx((a.omega + b.omega) / 2, abs=0.05)


# ---------- trajectory ----------

def test_reversed_straight_line_drives_backwards():
    # Robot faces -x (heading tangents point -x) and backs up toward +x.
    traj = generate_trajectory([(0, 0), (48, 0)], [(-48, 0), (-48, 0)], CFG, reversed_segments=[True])
    assert traj[-1].x == pytest.approx(48)
    assert all(p.velocity <= 1e-9 for p in traj)
    assert min(p.velocity for p in traj) < -10
    for p in traj:
        assert abs(wrap(p.theta - math.pi)) < 1e-6
        assert p.omega == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("reverse", [False, True])
def test_omega_matches_heading_rate_on_curves(reverse):
    s = -1 if reverse else 1
    traj = generate_trajectory([(0, 0), (40, 40), (80, 0)], [(s * 40, 0), (s * 40, 0), (s * 40, 0)], CFG,
                               reversed_segments=[reverse, reverse])
    for p in traj:
        assert p.omega == pytest.approx(p.velocity * p.curvature)
    heading_rate_matches_omega(traj)


def test_direction_change_stops_at_cusp():
    # Drive forward to (48, 0), then back up to (24, 24).
    wps = [(0, 0), (48, 0), (24, 24)]
    tangents = [(48, 0), (48, 0), (24, -24)]  # robot keeps facing roughly +x while backing up
    traj = generate_trajectory(wps, tangents, CFG, reversed_segments=[False, True])
    cusp = min(range(len(traj)), key=lambda i: math.hypot(traj[i].x - 48, traj[i].y))
    assert (traj[cusp].x, traj[cusp].y) == pytest.approx((48, 0))
    assert traj[cusp].velocity == pytest.approx(0, abs=1e-9)
    assert all(p.velocity >= -1e-9 for p in traj[:cusp])
    assert all(p.velocity <= 1e-9 for p in traj[cusp:])
    assert all(b.timestamp > a.timestamp for a, b in zip(traj, traj[1:]))
    # heading is continuous through the cusp (no instant 180-degree flip)
    assert abs(wrap(traj[cusp + 1].theta - traj[cusp - 1].theta)) < math.radians(20)


def test_segment_speed_cap():
    wps = [(0, 0), (60, 0), (120, 0)]
    tangents = [(60, 0), (60, 0), (60, 0)]
    traj = generate_trajectory(wps, tangents, CFG, speed_caps=[20, None])
    first = [p for p in traj if p.x < 60]
    second = [p for p in traj if p.x > 70]
    assert max(p.velocity for p in first) <= 20 + 1e-9
    assert max(p.velocity for p in second) > 30


def test_no_options_matches_plain_call():
    wps, tangents = [(0, 0), (30, 40), (90, 10)], [(30, 40), (45, -15), (60, -30)]
    plain = generate_trajectory(wps, tangents, CFG)
    explicit = generate_trajectory(wps, tangents, CFG, reversed_segments=[False, False], speed_caps=[None, None])
    assert plain == explicit


# ---------- app ----------

@pytest.fixture
def app(make_app):
    a, _, _ = make_app()
    for p in [(10, 10), (70, 70), (130, 10)]:
        a.on_click(Click(*p))
    a.on_release(None)
    return a


def select(app, x, y):
    app.on_click(Click(x, y))
    app.on_release(None)


def test_apply_reverse_flips_auto_tangents_and_velocity(app):
    select(app, 10, 10)
    app.entries['reverse'].set(True)
    app.on_apply()
    first = app.waypoints[0]
    assert first.reversed
    assert (first.dx, first.dy) == (-60, -60)       # faces away from the next waypoint
    seg0 = [p for p in app.trajectory if p.x < 69]
    assert all(p.velocity <= 1e-9 for p in seg0)
    assert any(p.velocity > 0 for p in app.trajectory if p.x > 72)  # segment 2 still forward


def test_peak_speed_counts_reverse(app):
    for w in app.waypoints[:2]:
        w.reversed = True
    app.compute_tangents()
    app.draw_all()
    peak = float(app.stats_var.value.split("peak v")[1].split("in/s")[0])
    assert peak == pytest.approx(max(abs(p.velocity) for p in app.trajectory), abs=0.05)
    assert peak > 0


def test_apply_speed_cap_and_undo(app):
    select(app, 10, 10)
    app.entries['cap'].value = "15"
    app.on_apply()
    assert app.waypoints[0].v_cap == 15
    assert max(p.velocity for p in app.trajectory if p.x < 69) <= 15 + 1e-9
    app.undo()
    assert app.waypoints[0].v_cap is None


@pytest.mark.parametrize("text", ["fast", "0", "-3"])
def test_bad_speed_cap_rejected(app, dialogs, text):
    select(app, 10, 10)
    app.entries['cap'].value = text
    app.on_apply()
    assert dialogs and "max speed" in dialogs[-1][1]
    assert app.waypoints[0].v_cap is None


def test_panel_shows_segment_options(app):
    select(app, 10, 10)
    app.entries['cap'].value = "25"
    app.entries['reverse'].set(True)
    app.on_apply()
    select(app, 70, 70)
    assert app.entries['cap'].value == "" and app.entries['reverse'].get() is False
    select(app, 10, 10)
    assert app.entries['cap'].value == "25" and app.entries['reverse'].get() is True


def test_segment_options_survive_save_and_open(app, monkeypatch, tmp_path):
    select(app, 70, 70)
    app.entries['reverse'].set(True)
    app.entries['cap'].value = "20"
    app.on_apply()
    target = tmp_path / "rev.path.json"
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **kw: str(target))
    assert app.save()
    app.new_path()  # clean after saving, so no prompt
    assert app.waypoints == []
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **kw: str(target))
    app.open_path()
    assert [(w.reversed, w.v_cap) for w in app.waypoints] == [(False, None), (True, 20), (False, None)]


def test_reversed_segment_drawn_dashed_and_profile_goes_negative(app):
    select(app, 70, 70)
    app.entries['reverse'].set(True)
    app.on_apply()
    from ui.velocity_view import SURFACE
    gaps = [a for a in app.view._artists
            if a.axes is app.ax and hasattr(a, 'get_color') and not hasattr(a, 'get_array')
            and a.get_color() == SURFACE]
    assert gaps, "expected a dashed overlay on the reversed segment"
    assert app.profile_ax.get_ylim()[0] < 0


# ---------- field picker ----------

from ui.fields import DEFAULT_FIELD, FIELDS_DIR, NO_FIELD, load_builtin_fields


@pytest.fixture
def image(tmp_path):
    import matplotlib.image as mpimg
    path = tmp_path / "practice field.png"
    mpimg.imsave(path, np.random.rand(20, 20, 3))
    return str(path)


def test_builtin_override_fields_present():
    names = [f.name for f in load_builtin_fields()]
    assert names == ["VURC 2027 - Override", "VURC 2027 - Override (Skills)", "V5RC 2027 - Override",
                     "V5RC 2027 - Override (Skills)", "V5RC Field Perimeter"]
    f = load_builtin_fields()[0]
    assert f.size_in == pytest.approx(3690 / 25.4)
    lo, hi, _, _ = f.extent
    assert (lo + hi) / 2 == pytest.approx(72) and hi - lo == pytest.approx(145.28, abs=0.01)


def test_default_field_is_vurc_override(make_app, tmp_path):
    app, _, _ = make_app(prefs_path=str(tmp_path / "prefs.json"), fields_dir=FIELDS_DIR)
    assert app.field_name == DEFAULT_FIELD
    assert app.field_image is not None
    assert app.ax.get_xlim()[0] < 0 < 144 < app.ax.get_xlim()[1]  # wall visible around the tiles


def test_switching_fields_is_remembered(make_app, tmp_path):
    prefs = tmp_path / "prefs.json"
    app, _, _ = make_app(prefs_path=str(prefs), fields_dir=FIELDS_DIR)
    changes = []
    app.on_field_change = changes.append
    assert app.select_field("V5RC 2027 - Override (Skills)")
    assert changes == ["V5RC 2027 - Override (Skills)"]
    assert json.loads(prefs.read_text())["field"] == "V5RC 2027 - Override (Skills)"

    again, _, _ = make_app(prefs_path=str(prefs), fields_dir=FIELDS_DIR)
    assert again.field_name == "V5RC 2027 - Override (Skills)"

    assert app.select_field(NO_FIELD)
    assert app.field_image is None and app.ax.get_xlim() == (0, 144)


def test_unknown_field_is_rejected(make_app, tmp_path):
    app, _, _ = make_app(prefs_path=str(tmp_path / "p.json"), fields_dir=FIELDS_DIR)
    assert app.select_field("VEX IQ 1999") is False
    assert app.field_name == DEFAULT_FIELD


def test_add_and_remove_custom_field(make_app, tmp_path, image, monkeypatch):
    prefs = tmp_path / "prefs.json"
    app, _, _ = make_app(prefs_path=str(prefs), fields_dir=FIELDS_DIR)
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **kw: image)
    assert app.add_custom_field()
    assert app.field_name == "practice field"
    assert "practice field" in app.field_names()
    assert app.field_image[1].get_extent() == [0, 144, 0, 144]  # custom images cover just the tiles

    again, _, _ = make_app(prefs_path=str(prefs), fields_dir=FIELDS_DIR)
    assert again.field_name == "practice field"

    app.remove_custom_field("practice field")
    assert app.field_name == NO_FIELD
    assert "practice field" not in app.field_names()


def test_old_single_image_preference_migrates(make_app, tmp_path, image):
    prefs = tmp_path / "prefs.json"
    prefs.write_text(json.dumps({"field_image": image}))
    app, _, _ = make_app(prefs_path=str(prefs), fields_dir=FIELDS_DIR)
    assert app.field_name == "practice field"


def test_bad_custom_image_shows_error(make_app, tmp_path, dialogs):
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    app, _, _ = make_app(prefs_path=str(tmp_path / "p.json"))
    assert app.add_custom_field(str(bad)) is False
    assert app.field_image is None
    assert dialogs and "Could not load" in dialogs[-1][1]
