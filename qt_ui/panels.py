"""Sidebars: waypoints + selected-waypoint editor (left), robot settings + path stats (right)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QPushButton, QVBoxLayout, QWidget)

from profiler.config import RobotConfig

LEFT_WIDTH = 270
RIGHT_WIDTH = 250


def _section(text):
    label = QLabel(text.upper())
    label.setObjectName("section")
    return label


def _spin(lo, hi, decimals=1, suffix="", special=None, step=1.0):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setKeyboardTracking(False)
    s.setAlignment(Qt.AlignRight)
    if suffix:
        s.setSuffix(suffix)
    if special:
        s.setSpecialValueText(special)  # shown when the value is the minimum
    return s


def _sidebar(side, width):
    frame = QFrame()
    frame.setObjectName("sidebar")
    frame.setProperty("side", side)
    frame.setFixedWidth(width)
    return frame


class WaypointPanel(QFrame):
    """Waypoint list plus an editor for the selected waypoint. Every commit is one undo step."""

    def __init__(self, editor, on_error=None):
        super().__init__()
        self.setObjectName("sidebar")
        self.setProperty("side", "left")
        self.setFixedWidth(LEFT_WIDTH)
        self.editor = editor
        self.on_error = on_error or (lambda title, msg: None)
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        layout.addWidget(_section("Waypoints"))
        self.list = QListWidget()
        self.list.setToolTip("Click to select. Drag points on the field to move them.")
        layout.addWidget(self.list, 1)
        self.empty_label = QLabel("Click the field to add a waypoint.")
        self.empty_label.setObjectName("empty")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        layout.addWidget(_section("Selected waypoint"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        self.x_spin = _spin(-24, 168, suffix=" in")
        self.y_spin = _spin(-24, 168, suffix=" in")
        self.dx_spin = _spin(-2000, 2000)
        self.dy_spin = _spin(-2000, 2000)
        for col, (label, spin, tip) in enumerate((("x", self.x_spin, "Position (in)"),
                                                  ("y", self.y_spin, "Position (in)"))):
            grid.addWidget(self._small(label), 0, col)
            grid.addWidget(spin, 1, col)
            spin.setToolTip(tip)
        for col, (label, spin) in enumerate((("heading dx", self.dx_spin), ("heading dy", self.dy_spin))):
            grid.addWidget(self._small(label), 2, col)
            grid.addWidget(spin, 3, col)
            spin.setToolTip("Tangent / heading vector. Editing it makes the heading manual.")
        layout.addLayout(grid)

        self.reverse_box = QCheckBox("Drive next segment in reverse")
        layout.addWidget(self.reverse_box)
        cap_row = QHBoxLayout()
        cap_row.addWidget(self._small("Max speed, next segment"))
        self.cap_spin = _spin(0, 500, decimals=0, suffix=" in/s", special="none", step=5)
        self.cap_spin.setToolTip("Speed cap for the segment leaving this waypoint (none = no cap)")
        cap_row.addWidget(self.cap_spin)
        layout.addLayout(cap_row)

        buttons = QHBoxLayout()
        self.auto_button = QPushButton("Auto heading")
        self.auto_button.setToolTip("Return the heading to automatic")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Delete waypoint (Del)")
        buttons.addWidget(self.auto_button)
        buttons.addWidget(self.delete_button)
        layout.addLayout(buttons)

        self.inputs = [self.x_spin, self.y_spin, self.dx_spin, self.dy_spin, self.reverse_box, self.cap_spin,
                       self.auto_button, self.delete_button]

        self.list.currentRowChanged.connect(self._row_changed)
        for spin, attr in ((self.x_spin, "x"), (self.y_spin, "y"), (self.dx_spin, "dx"), (self.dy_spin, "dy")):
            spin.editingFinished.connect(lambda s=spin, a=attr: self._commit(a, s))
        self.cap_spin.editingFinished.connect(self._commit_cap)
        self.reverse_box.toggled.connect(self._commit_reverse)
        self.auto_button.clicked.connect(lambda: self.editor.reset_tangent())
        self.delete_button.clicked.connect(lambda: self.editor.delete_waypoint())
        editor.subscribe(lambda kind: self.refresh() if kind in ("path", "selection") else None)
        self.refresh()

    @staticmethod
    def _small(text):
        label = QLabel(text)
        label.setObjectName("statLabel")
        return label

    # ----- editor -> widgets -----

    def refresh(self):
        self._updating = True
        try:
            ed = self.editor
            self.list.clear()
            for i, w in enumerate(ed.waypoints):
                text = f"{i + 1}    ({w.x:.1f}, {w.y:.1f})"
                if w.reversed and i < len(ed.waypoints) - 1:
                    text += "   R"
                if w.v_cap is not None and i < len(ed.waypoints) - 1:
                    text += f"   ≤{w.v_cap:g}"
                self.list.addItem(text)
            sel = next((i for i, w in enumerate(ed.waypoints) if w is ed.selected), -1)
            self.list.setCurrentRow(sel)
            self.empty_label.setVisible(not ed.waypoints)

            w = ed.selected
            for widget in self.inputs:
                widget.setEnabled(w is not None)
            if w is not None:
                self.x_spin.setValue(w.x)
                self.y_spin.setValue(w.y)
                self.dx_spin.setValue(w.dx)
                self.dy_spin.setValue(w.dy)
                self.reverse_box.setChecked(w.reversed)
                self.cap_spin.setValue(w.v_cap or 0)
                self.auto_button.setEnabled(w.manual_tangent)
                last = sel == len(ed.waypoints) - 1
                self.reverse_box.setEnabled(not last)   # segment options belong to the leaving segment
                self.cap_spin.setEnabled(not last)
        finally:
            self._updating = False

    # ----- widgets -> editor -----

    def _row_changed(self, row):
        if self._updating:
            return
        ed = self.editor
        ed.select(ed.waypoints[row] if 0 <= row < len(ed.waypoints) else None)

    def _commit(self, attr, spin):
        w = self.editor.selected
        if self._updating or w is None:
            return
        value = spin.value()
        if abs(value - round(getattr(w, attr), spin.decimals())) < 1e-9:
            return  # nothing changed: no undo step
        self.editor.update_waypoint(w, **{attr: value})

    def _commit_cap(self):
        w = self.editor.selected
        if self._updating or w is None:
            return
        cap = self.cap_spin.value() or None
        if cap == w.v_cap:
            return
        try:
            self.editor.update_waypoint(w, v_cap=cap)
        except ValueError as e:
            self.on_error("Invalid speed cap", str(e))

    def _commit_reverse(self, checked):
        w = self.editor.selected
        if self._updating or w is None or checked == w.reversed:
            return
        self.editor.update_waypoint(w, reversed=checked)


class RobotPanel(QFrame):
    """Robot constants (applied together) and the current path's stats."""

    FIELDS = [
        # attr, label, lo, hi, decimals, suffix, special (shown at lo)
        ("v_max", "Max speed", 1, 500, 1, " in/s", None),
        ("a_max", "Max accel", 1, 2000, 1, " in/s²", None),
        ("a_lat_max", "Lateral accel", 0, 2000, 1, " in/s²", "same as accel"),
        ("track_width", "Track width", 0, 48, 2, " in", "off"),
        ("spacing", "Point spacing", 0.05, 6, 2, " in", None),
    ]

    def __init__(self, editor, on_error=None):
        super().__init__()
        self.setObjectName("sidebar")
        self.setProperty("side", "right")
        self.setFixedWidth(RIGHT_WIDTH)
        self.editor = editor
        self.on_error = on_error or (lambda title, msg: None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(6)
        layout.addWidget(_section("Robot"))
        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        self.spins = {}
        for row, (attr, label, lo, hi, dec, suffix, special) in enumerate(self.FIELDS):
            grid.addWidget(QLabel(label), row, 0)
            spin = _spin(lo, hi, dec, suffix, special, step=0.5 if attr == "spacing" else 1)
            grid.addWidget(spin, row, 1)
            self.spins[attr] = spin
        layout.addLayout(grid)
        self.apply_button = QPushButton("Apply robot settings")
        self.apply_button.setObjectName("primary")
        layout.addWidget(self.apply_button)

        layout.addSpacing(10)
        layout.addWidget(_section("Path"))
        self.length_label, self.time_label, self.peak_label = QLabel("—"), QLabel("—"), QLabel("—")
        for caption, value in (("Total time", self.time_label), ("Length", self.length_label),
                               ("Peak speed", self.peak_label)):
            value.setObjectName("stat")
            cap = QLabel(caption)
            cap.setObjectName("statLabel")
            layout.addWidget(value)
            layout.addWidget(cap)
        layout.addStretch(1)

        self.apply_button.clicked.connect(self.apply)
        editor.subscribe(self._on_change)
        self.fill()
        self.update_stats()

    def _on_change(self, kind):
        if kind == "config":
            self.fill()
        if kind in ("path", "config"):
            self.update_stats()

    def fill(self):
        cfg = self.editor.config
        for attr, spin in self.spins.items():
            value = getattr(cfg, attr)
            spin.setValue(spin.minimum() if value is None else value)

    def apply(self):
        values = {attr: spin.value() for attr, spin in self.spins.items()}
        if values["a_lat_max"] <= self.spins["a_lat_max"].minimum():
            values["a_lat_max"] = None
        try:
            self.editor.set_config(RobotConfig(**values))
        except (ValueError, OSError) as e:
            self.on_error("Robot settings", str(e))

    def update_stats(self):
        s = self.editor.stats()
        if s is None:
            for label in (self.time_label, self.length_label, self.peak_label):
                label.setText("—")
            return
        self.time_label.setText(f"{s['time']:.2f} s")
        self.length_label.setText(f"{s['length']:.1f} in")
        self.peak_label.setText(f"{s['peak']:.1f} in/s")
