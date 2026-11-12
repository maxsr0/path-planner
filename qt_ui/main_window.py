"""Main window: toolbar, waypoint sidebar, big centered field, robot sidebar, speed strip, status bar."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QGridLayout, QLabel, QMainWindow,
                               QMessageBox, QToolButton, QWidget)

from exporter.binary_exporter import export_trajectory
from exporter.header_exporter import export_trajectory_header
from exporter.path_file import EXTENSION
from planner.editor import Editor, Playback
from planner.fields import FIELDS_DIR, FieldLibrary
from qt_ui.field_view import FieldView
from qt_ui.panels import RobotPanel, WaypointPanel
from qt_ui.speed_plot import SpeedPlot
from qt_ui.theme import THEMES, load_theme_name, save_theme_name, stylesheet, toggled

ADD_IMAGE = "+ Add image…"
APP_NAME = "PRISM Path Planner"

SHORTCUTS = [
    ("Click field", "Add a waypoint (selects it)"),
    ("Drag waypoint", "Move it  ·  hold Ctrl to snap to whole inches"),
    ("Drag square handle", "Bend the curve (manual heading)"),
    ("Shift + click path", "Insert a waypoint into that segment"),
    ("Right-click waypoint / Del", "Delete"),
    ("Mouse wheel / middle-drag", "Zoom / pan  ·  F fits the field"),
    ("Hover speed graph", "Scrub the robot along the path"),
    ("Space", "Play / stop"),
    ("Ctrl+Z / Ctrl+Y", "Undo / redo"),
    ("Ctrl+N / O / S, Ctrl+Shift+S", "New / open / save / save as"),
    ("Ctrl+E / Ctrl+Shift+E", "Export .bin / .hpp"),
    ("Ctrl+T", "Light / dark theme"),
    ("Ctrl+G", "Show / hide speed graph"),
    ("F11", "Full screen"),
]


class MainWindow(QMainWindow):
    def __init__(self, prefs_path=None, config_path=None, fields_dir=FIELDS_DIR, editor=None):
        super().__init__()
        self.prefs_path = prefs_path
        self.editor = editor or Editor(config_path=config_path)
        self.library = FieldLibrary(prefs_path, fields_dir)
        self.playback = Playback(self.editor)
        self.theme_name = load_theme_name(prefs_path)
        theme = THEMES[self.theme_name]

        self.field_view = FieldView(self.editor, theme)
        self.speed_plot = SpeedPlot(self.editor, theme)
        self.speed_plot.setFixedHeight(150)
        self.waypoint_panel = WaypointPanel(self.editor, on_error=lambda t, m: self.show_error(t, m))
        self.robot_panel = RobotPanel(self.editor, on_error=lambda t, m: self.show_error(t, m))

        central = QWidget()
        central.setObjectName("central")
        grid = QGridLayout(central)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self.waypoint_panel, 0, 0, 2, 1)
        grid.addWidget(self.field_view, 0, 1)
        grid.addWidget(self.speed_plot, 1, 1)
        grid.addWidget(self.robot_panel, 0, 2, 2, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        self.setCentralWidget(central)

        self._build_actions()
        self._build_toolbar()
        self._build_status_bar()

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._play_tick)

        self.field_view.cursor_moved.connect(lambda x, y: self.cursor_label.setText(f"x {x:.1f}   y {y:.1f}"))
        self.field_view.hint_changed.connect(self.hint_label.setText)
        self.speed_plot.time_hovered.connect(self._scrub)
        self.editor.subscribe(self._on_editor_change)

        self.setMinimumSize(1100, 700)
        self.apply_theme(self.theme_name, remember=False)
        self._load_field(self.library.selected_name())
        self._update_title()
        if self.editor.config_error:
            QTimer.singleShot(0, lambda: self.show_error("Robot settings", self.editor.config_error))

    # ---------- construction ----------

    def _action(self, key, text, slot, shortcut=None, tip=None, context=Qt.WindowShortcut, widget=None):
        action = QAction(text, self)
        if shortcut:
            seqs = shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]
            action.setShortcuts([QKeySequence(s) for s in seqs])
            action.setShortcutContext(context)
        tip = tip or text
        action.setToolTip(f"{tip} ({QKeySequence(seqs[0]).toString(QKeySequence.NativeText)})" if shortcut else tip)
        action.triggered.connect(slot)
        (widget or self).addAction(action)
        self.actions[key] = action
        return action

    def _build_actions(self):
        self.actions = {}
        fv = self.field_view
        self._action("new", "New", self.new_path, "Ctrl+N", "New path")
        self._action("open", "Open", self.open_path, "Ctrl+O", "Open path")
        self._action("save", "Save", self.save, "Ctrl+S", "Save path")
        self._action("save_as", "Save as", self.save_as, "Ctrl+Shift+S", "Save path as")
        self._action("undo", "Undo", self.editor.undo, "Ctrl+Z")
        self._action("redo", "Redo", self.editor.redo, ["Ctrl+Y", "Ctrl+Shift+Z"])
        # Keys that would clash with typing in the sidebars only act while the field has focus.
        self._action("delete", "Delete", lambda: self.editor.delete_waypoint(), ["Delete", "Backspace"],
                     "Delete selected waypoint", Qt.WidgetShortcut, fv)
        self._action("deselect", "Deselect", lambda: self.editor.select(None), "Escape",
                     context=Qt.WidgetShortcut, widget=fv)
        self._action("fit", "Fit", self.field_view.fit_field, "F", "Fit field to view", Qt.WidgetShortcut, fv)
        self._action("play", "Play", self.toggle_play, "Space", "Play / stop the path", Qt.WidgetShortcut, fv)
        self._action("toggle_speed", "Speed graph", self.toggle_speed_strip, "Ctrl+G", "Show / hide the speed graph")
        self._action("theme", "Light theme", self.toggle_theme, "Ctrl+T", "Switch light / dark theme")
        self._action("export_bin", "Export .bin", lambda: self.export("bin"), "Ctrl+E", "Export .bin (SD card)")
        self._action("export_hpp", "Export .hpp", lambda: self.export("hpp"), "Ctrl+Shift+E",
                     "Export .hpp (embed in firmware)")
        self._action("fullscreen", "Full screen", self.toggle_fullscreen, "F11")
        self._action("shortcuts", "Shortcuts", self.show_shortcuts, "F1", "Keyboard and mouse shortcuts")

    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        a = self.actions
        for group in (("new", "open", "save"), ("undo", "redo"), ("play", "fit", "toggle_speed")):
            for key in group:
                tb.addAction(a[key])
            tb.addSeparator()
        tb.addWidget(QLabel(" Field "))
        self.field_combo = QComboBox()
        self.field_combo.setMinimumWidth(250)
        self.field_combo.setToolTip("Field background")
        tb.addWidget(self.field_combo)
        self._fill_field_combo(self.library.selected_name())
        self.field_combo.currentTextChanged.connect(self._field_chosen)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)
        tb.addAction(a["theme"])
        tb.addSeparator()
        tb.addAction(a["export_bin"])
        tb.addAction(a["export_hpp"])

    def _build_status_bar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.cursor_label = QLabel("x —   y —")
        self.cursor_label.setMinimumWidth(140)
        self.hint_label = QLabel("Click the field to add a waypoint")
        sb.addWidget(self.cursor_label)
        sb.addWidget(self.hint_label, 1)
        help_button = QToolButton()
        help_button.setDefaultAction(self.actions["shortcuts"])
        help_button.setText("? Shortcuts")
        sb.addPermanentWidget(help_button)

    # ---------- dialogs (tests replace these) ----------

    def show_error(self, title, message):
        QMessageBox.warning(self, title, message)

    def ask_discard(self):
        """'save', 'discard' or 'cancel' for unsaved changes."""
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Save changes to {self.editor.path_stem()}?")
        save = box.addButton("Save", QMessageBox.AcceptRole)
        discard = box.addButton("Don't save", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        return "save" if clicked is save else "discard" if clicked is discard else "cancel"

    def ask_save_path(self, kind):
        stem = self.editor.path_stem()
        filters = {"path": ("Save path", f"{stem}{EXTENSION}", f"PRISM path (*{EXTENSION})"),
                   "bin": ("Export .bin (SD card)", f"{stem}.bin", "Binary trajectory (*.bin)"),
                   "hpp": ("Export .hpp (firmware)", f"{stem}.hpp", "C++ header (*.hpp)")}
        title, name, flt = filters[kind]
        path, _ = QFileDialog.getSaveFileName(self, title, name, flt)
        return path or None

    def ask_open_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open path", "", f"PRISM path (*{EXTENSION} *.json)")
        return path or None

    def ask_image_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Field image (top-down, cropped to the 144 in tiles)", "",
                                              "Images (*.png *.jpg *.jpeg)")
        return path or None

    # ---------- files ----------

    def _confirm_discard(self):
        if not self.editor.is_dirty():
            return True
        answer = self.ask_discard()
        if answer == "save":
            return self.save()
        return answer == "discard"

    def new_path(self):
        if self._confirm_discard():
            self.editor.new()

    def open_path(self):
        if not self._confirm_discard():
            return
        path = self.ask_open_path()
        if not path:
            return
        try:
            self.editor.load(path)
        except (OSError, ValueError) as e:
            self.show_error("Open path", f"Could not open {path}: {e}")

    def save(self):
        if not self.editor.file_path:
            return self.save_as()
        return self._write(self.editor.file_path)

    def save_as(self):
        path = self.ask_save_path("path")
        return self._write(path) if path else False

    def _write(self, path):
        try:
            self.editor.save(path)
            return True
        except OSError as e:
            self.show_error("Save path", f"Could not save {path}: {e}")
            return False

    def export(self, kind):
        traj = self.editor.trajectory
        if len(traj) < 2:
            self.show_error("Export", "Place at least two waypoints first.")
            return
        path = self.ask_save_path(kind)
        if not path:
            return
        try:
            (export_trajectory if kind == "bin" else export_trajectory_header)(traj, path)
            self.statusBar().showMessage(f"Exported {path}", 5000)
        except OSError as e:
            self.show_error("Export", f"Could not write {path}: {e}")

    def closeEvent(self, event):
        if self._confirm_discard():
            self.playback.stop()
            event.accept()
        else:
            event.ignore()

    # ---------- field picker ----------

    def _fill_field_combo(self, current):
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        self.field_combo.addItems(self.library.names() + [ADD_IMAGE])
        self.field_combo.setCurrentText(current)
        self.field_combo.blockSignals(False)
        self._field_name = current

    def _field_chosen(self, name):
        if name == ADD_IMAGE:
            path = self.ask_image_path()
            if path:
                name = self.library.add_custom(path)
            else:
                name = self._field_name
            self._fill_field_combo(name)
        self._load_field(name)

    def _load_field(self, name):
        try:
            preset = self.library.get(name)
            self.library.select(name)
        except KeyError:
            preset, name = None, self.library.names()[0]
        if not self.field_view.set_field(preset):
            self.show_error("Field image", f"Could not load the image for {name}.")
        self._field_name = name

    # ---------- theme / view ----------

    def apply_theme(self, name, remember=True):
        self.theme_name = name
        theme = THEMES[name]
        QApplication.instance().setStyleSheet(stylesheet(theme))
        self.field_view.set_theme(theme)
        self.speed_plot.set_theme(theme)
        self.actions["theme"].setText("Dark theme" if name == "light" else "Light theme")
        if remember:
            save_theme_name(self.prefs_path, name)

    def toggle_theme(self):
        self.apply_theme(toggled(self.theme_name))

    def toggle_speed_strip(self):
        self.speed_plot.setVisible(not self.speed_plot.isVisible())

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def show_shortcuts(self):
        rows = "".join(f"<tr><td style='padding:3px 16px 3px 0'><b>{k}</b></td><td>{v}</td></tr>"
                       for k, v in SHORTCUTS)
        QMessageBox.information(self, "Shortcuts", f"<table>{rows}</table>")

    # ---------- playback ----------

    def toggle_play(self):
        if self.playback.playing:
            self.stop_play()
        else:
            self.playback.start()
            if self.playback.playing:
                self.actions["play"].setText("Stop")
                self.timer.start()

    def stop_play(self):
        self.playback.stop()
        self.timer.stop()
        self.actions["play"].setText("Play")
        self.field_view.set_robot_time(None)
        self.speed_plot.set_playhead(None)

    def _play_tick(self, now=None):
        t = self.playback.time(now)
        if t is None:
            self.stop_play()
            return
        self.field_view.set_robot_time(t)
        self.speed_plot.set_playhead(t)

    def _scrub(self, t):
        if self.playback.playing:
            return
        self.field_view.set_robot_time(t)
        self.speed_plot.set_playhead(t)

    # ---------- state ----------

    def _on_editor_change(self, kind):
        if kind in ("path", "file"):
            self._update_title()

    def _update_title(self):
        star = "*" if self.editor.is_dirty() else ""
        self.setWindowTitle(f"{star}{self.editor.path_stem()} - {APP_NAME}")
