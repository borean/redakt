from PySide6.QtCore import Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from redakt.ui import theme as theme_module


def _c():
    tm = getattr(theme_module, "theme_manager", None)
    return tm.get_colors() if tm else {
        "BG_DARKEST": "#111111", "BORDER": "#333333",
        "TEXT_DIM": "#808080", "ACCENT": "#e78a4e",
        "ERROR": "#d46b6b", "SUCCESS": "#6bbd6b",
    }


class StatusBar(QWidget):
    """Simple status bar: Ready / Processing + LOCAL badge. No internal details."""

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        # Translatable status texts (updated via set_translations)
        self._t_ready = "READY"
        self._t_not_ready = "NOT READY"
        self._t_processing = "PROCESSING LOCALLY..."
        self._t_error = "ERROR"

        self._status_label = QLabel(self._t_ready)
        layout.addWidget(self._status_label)

        layout.addStretch()

        self._local_badge = QLabel("100% LOCAL · NO INTERNET")
        layout.addWidget(self._local_badge)

        self._apply_theme()

    def _apply_theme(self):
        """Apply current theme colors. Called on init and when theme changes."""
        c = _c()
        self._status_label.setStyleSheet(
            f"color: {c['TEXT_DIM']}; font-size: 10px; letter-spacing: 1px;"
        )
        self._local_badge.setStyleSheet(
            f"color: {c['SUCCESS']}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 1.5px; border: 1px solid {c['SUCCESS']}40; "
            f"border-radius: 2px; padding: 2px 8px;"
        )
        self.setStyleSheet(
            f"StatusBar {{ background-color: {c['BG_DARKEST']}; "
            f"border: 1px solid {c['BORDER']}; border-radius: 2px; }}"
        )

    def set_translations(self, *, ready: str, not_ready: str, processing: str, error: str):
        """Update translatable status texts (called from _relabel_ui)."""
        self._t_ready = ready
        self._t_not_ready = not_ready
        self._t_processing = processing
        self._t_error = error

    @Slot(bool)
    def set_ready_status(self, running: bool):
        c = _c()
        if running:
            self._status_label.setText(self._t_ready)
            self._status_label.setStyleSheet(
                f"color: {c['SUCCESS']}; font-size: 10px; letter-spacing: 1px;"
            )
        else:
            self._status_label.setText(self._t_not_ready)
            self._status_label.setStyleSheet(
                f"color: {c['ERROR']}; font-size: 10px; letter-spacing: 1px;"
            )

    @Slot(bool)
    def set_active_inference(self, active: bool):
        """Show Processing when scanning, Ready when idle."""
        c = _c()
        if active:
            self._status_label.setText(self._t_processing)
            self._status_label.setStyleSheet(
                f"color: {c['ACCENT']}; font-size: 10px; letter-spacing: 1px;"
            )
        else:
            self._status_label.setText(self._t_ready)
            self._status_label.setStyleSheet(
                f"color: {c['SUCCESS']}; font-size: 10px; letter-spacing: 1px;"
            )

    @Slot(str)
    def set_model_status(self, status: str):
        """Ignore internal model/backend names — keep status simple."""
        if "failed" in status.lower() or "error" in status.lower():
            c = _c()
            self._status_label.setText(self._t_error)
            self._status_label.setStyleSheet(
                f"color: {c['ERROR']}; font-size: 10px; letter-spacing: 1px;"
            )

    @Slot(str)
    def set_local_badge(self, text: str):
        """Update the local/no-internet badge (for i18n)."""
        self._local_badge.setText(text)
