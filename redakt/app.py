import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from redakt import APP_NAME, ORG_NAME
from redakt.ui import theme as theme_module


def create_app(argv: list[str] | None = None) -> QApplication:
    argv = argv or sys.argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    # Set app icon (works for window/taskbar; .icns handles Dock on macOS)
    icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
    if not os.path.exists(icon_path):
        # PyInstaller bundle: assets are in the _MEIPASS directory
        icon_path = os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Initialize theme manager and apply saved preference
    theme_module.theme_manager = theme_module.ThemeManager(app)
    theme_module.theme_manager.apply_to_app()

    from redakt.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    # Refresh UI when theme changes (e.g. from settings)
    tm = theme_module.theme_manager
    tm.theme_changed.connect(lambda: tm.apply_to_app())
    tm.theme_changed.connect(window._on_theme_changed)

    # Keep reference so it doesn't get garbage collected
    app._main_window = window
    return app
