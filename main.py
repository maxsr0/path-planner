"""PRISM Path Planner: launch the Qt app (starts maximized; F11 toggles full screen)."""
import os
import sys

from PySide6.QtWidgets import QApplication

from qt_ui.main_window import APP_NAME, MainWindow

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")  # consistent base for the stylesheet on every OS
    window = MainWindow(prefs_path=os.path.join(HERE, "ui_prefs.json"),
                        config_path=os.path.join(HERE, "robot_config.json"))
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
