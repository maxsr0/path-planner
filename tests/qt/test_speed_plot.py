"""SpeedPlot: speed vs time strip with hover scrubbing and a playhead."""
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from planner.editor import Editor
from qt_ui.speed_plot import SpeedPlot
from qt_ui.theme import THEMES


@pytest.fixture
def plot(qtbot, editor):
    p = SpeedPlot(editor, THEMES["dark"])
    p.resize(900, 160)
    qtbot.addWidget(p)
    p.show()
    qtbot.waitExposed(p)
    return p


def test_time_pixel_mapping_roundtrip(plot, editor):
    end = editor.trajectory[-1].timestamp
    for t in (0.0, end / 3, end):
        assert plot.time_at_x(plot.x_for_time(t)) == pytest.approx(t, abs=end / 400)


def test_hover_emits_time(plot, qtbot, editor):
    t = editor.trajectory[-1].timestamp / 2
    QTest.mouseMove(plot, plot.point_for_time(t / 3))  # a move to the cursor's current spot sends nothing
    with qtbot.waitSignal(plot.time_hovered) as sig:
        QTest.mouseMove(plot, plot.point_for_time(t))
    assert sig.args[0] == pytest.approx(t, abs=editor.trajectory[-1].timestamp / 100)


def test_leave_emits_none(plot, qtbot):
    with qtbot.waitSignal(plot.time_hovered) as sig:
        QApplication.sendEvent(plot, QEvent(QEvent.Leave))
    assert sig.args[0] is None


def test_playhead_readout(plot, editor):
    plot.set_playhead(1.0)
    v = editor.pose_at(1.0)[3]
    assert plot.readout == f"t {1.0:5.2f} s   v {v:6.1f} in/s"
    plot.set_playhead(None)
    assert plot.readout == ""


def test_range_positive_then_negative_when_reversing(plot, editor):
    lo, hi = plot.v_range()
    assert lo == 0 and hi == pytest.approx(editor.config.v_max * 1.05)
    editor.update_waypoint(editor.waypoints[0], reversed=True)
    lo, hi = plot.v_range()
    assert lo == pytest.approx(-editor.config.v_max * 1.05)


def test_empty_path(qtbot):
    p = SpeedPlot(Editor(), THEMES["light"])
    qtbot.addWidget(p)
    p.resize(400, 120)
    p.show()
    p.set_playhead(1.0)
    p.repaint()  # must not raise
    assert p.readout == ""
    assert p.time_at_x(200) is None


def test_repaint_is_linear_in_path_length(qtbot, monkeypatch):
    """Regression: the axis range was rescanned for every point drawn (O(n^2), ~5 s for long paths).

    Counted rather than timed so machine load can't make it flaky.
    """
    from profiler.config import RobotConfig
    e = Editor(config=RobotConfig(spacing=0.1))
    for p in [(5, 5), (140, 20), (10, 70), (140, 130), (5, 140)]:
        e.add_waypoint(*p)
    assert len(e.trajectory) > 3000
    p = SpeedPlot(e, THEMES["dark"])
    qtbot.addWidget(p)
    p.resize(1400, 160)
    calls = []
    original = SpeedPlot.v_range
    monkeypatch.setattr(SpeedPlot, "v_range", lambda self: (calls.append(1), original(self))[1])
    p.grab()  # grab() forces a real paint even before the window is exposed
    assert 1 <= len(calls) <= 3


def test_theme_switch(plot):
    plot.set_theme(THEMES["light"])
    assert plot.theme is THEMES["light"]
    plot.repaint()
