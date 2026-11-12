import math

import pytest

from conftest import Click
from profiler.trajectory import TrajectoryPoint, state_at


def tp(x, y, theta, v, t):
    return TrajectoryPoint(x, y, theta, v, 0.0, 0.0, t)


def test_state_at_interpolates_and_clamps():
    traj = [tp(0, 0, 0, 0, 0), tp(10, 0, 0, 20, 1), tp(10, 10, math.pi / 2, 0, 2)]
    assert state_at(traj, -1) == (0, 0, 0, 0)
    assert state_at(traj, 0.5) == pytest.approx((5, 0, 0, 10))
    assert state_at(traj, 1.5) == pytest.approx((10, 5, math.pi / 4, 10))
    assert state_at(traj, 9) == (10, 10, math.pi / 2, 0)


def test_state_at_wraps_heading_the_short_way():
    traj = [tp(0, 0, math.radians(170), 1, 0), tp(1, 0, math.radians(-170), 1, 1)]
    theta = state_at(traj, 0.5)[2]
    assert math.cos(theta) == pytest.approx(-1, abs=1e-9)  # passes through 180, not 0


@pytest.fixture
def app(make_app):
    a, _, _ = make_app()
    for p in [(10, 10), (70, 90), (130, 20)]:
        a.on_click(Click(*p))
    a.on_release(None)
    return a


def test_path_colored_by_speed(app):
    view = app.view
    path = view._artists[0]
    speeds = path.get_array()
    assert len(speeds) == len(app.trajectory) - 1
    assert max(speeds) <= app.config.v_max + 1e-9
    # slow ends map to the dark end of the ramp, the fast middle to the light end
    colors = path.to_rgba(speeds)  # colormap is applied lazily at draw time, so map explicitly
    brightness = [sum(c[:3]) for c in colors]
    assert brightness[0] < max(brightness)


def test_profile_axes_span_trajectory(app):
    lo, hi = app.profile_ax.get_xlim()
    assert lo == 0 and hi == pytest.approx(app.trajectory[-1].timestamp)
    assert app.profile_ax.get_ylim()[1] == pytest.approx(app.config.v_max * 1.05)


def test_hover_on_profile_moves_robot_and_ignores_clicks(app):
    n = len(app.waypoints)
    hover = Click(1.0, 30)
    hover.inaxes = app.profile_ax
    app.on_drag(hover)
    assert app.view.robot.get_visible()
    assert "t  1.00 s" in app.view.readout.get_text()
    x, y, _, _ = state_at(app.trajectory, 1.0)
    cx, cy = app.view.robot.get_xy()[:4].mean(axis=0)
    assert (cx, cy) == pytest.approx((x, y))

    app.on_click(hover)  # clicking the speed plot must not add a waypoint
    assert len(app.waypoints) == n

    away = Click(50, 50)
    away.inaxes = app.ax
    app.on_drag(away)
    assert not app.view.robot.get_visible()


def test_robot_uses_track_width(app):
    app.config.track_width = 16
    app.draw_all()
    app.view.set_time(0.0)
    xy = app.view.robot.get_xy()[:4]
    side = math.dist(xy[0], xy[1])
    assert side == pytest.approx(16)


def test_playback_runs_and_stops_at_end(app):
    states = []
    app.on_play_state = states.append
    app.toggle_play()
    assert states == [True]
    start = app.play_start
    assert start is not None
    app.play_tick(now=start + 0.5)
    assert app.view.robot.get_visible()
    app.play_tick(now=start + app.view.duration + 1)
    assert app.play_start is None
    assert not app.view.robot.get_visible()
    assert states == [True, False]


def test_space_toggles_playback(app):
    from conftest import Key
    app.on_key(Key(' '))
    assert app.play_start is not None
    app.on_key(Key(' '))
    assert app.play_start is None


def test_no_trajectory_no_playback(make_app):
    a, _, _ = make_app()
    a.toggle_play()
    assert a.play_start is None
