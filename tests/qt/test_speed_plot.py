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
    with qtbot.waitSignal(plot.time_hovered) as sig:
        QTest.mouseMove(plot, plot.mapFromGlobal(plot.mapToGlobal(
            plot.rect().topLeft())) + plot.point_for_time(t))
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


def test_theme_switch(plot):
    plot.set_theme(THEMES["light"])
    assert plot.theme is THEMES["light"]
    plot.repaint()
