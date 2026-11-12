import matplotlib

matplotlib.use("Agg")

import pytest


class FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_):
        self.value = ""

    def insert(self, _, value):
        self.value = str(value)


class FakeVar:
    value = None

    def set(self, value):
        self.value = value


class FakeCanvas:
    def draw(self):
        pass


class Click:
    """Stand-in for a matplotlib mouse event. key is e.g. 'shift' or 'control'."""

    def __init__(self, x, y, button=1, key=None):
        self.xdata, self.ydata, self.button, self.key = x, y, button, key


class Key:
    def __init__(self, key):
        self.key = key


@pytest.fixture
def dialogs(monkeypatch):
    """Capture messagebox calls instead of opening dialogs."""
    import ui.app as app_module
    shown = []
    monkeypatch.setattr(app_module.messagebox, "showerror", lambda *a: shown.append(a))
    monkeypatch.setattr(app_module.messagebox, "showwarning", lambda *a: shown.append(a))
    return shown


@pytest.fixture
def make_app(dialogs):
    """Factory returning (app, settings_entries, stats_var) wired to fakes."""
    from ui.app import App
    from ui.field import create_field_figure

    def factory(config_path=None):
        fig, ax = create_field_figure()
        entries = {k: FakeEntry() for k in ("x", "y", "dx", "dy")}
        settings = {name: FakeEntry() for name, _ in App.SETTINGS_FIELDS}
        stats = FakeVar()
        return App(None, fig, ax, FakeCanvas(), entries, settings, stats, config_path), settings, stats

    yield factory

    import matplotlib.pyplot as plt
    plt.close('all')
