import sys

from PySide6.QtWidgets import QApplication

from qwenkk import APP_NAME, ORG_NAME
from qwenkk.ui.theme import DARK_STYLESHEET


def create_app(argv: list[str] | None = None) -> QApplication:
    argv = argv or sys.argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyleSheet(DARK_STYLESHEET)

    from qwenkk.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    # Keep reference so it doesn't get garbage collected
    app._main_window = window
    return app
