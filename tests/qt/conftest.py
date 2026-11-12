import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from planner.editor import Editor


@pytest.fixture
def editor():
    e = Editor()
    for p in [(24, 24), (72, 100), (120, 40)]:
        e.add_waypoint(*p)
    e.select(None)
    return e

