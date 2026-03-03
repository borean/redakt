"""Light/dark theme system for Redakt with Clinical and Terminal UI styles.

Two independent axes:
- **Color theme**: dark / light / system  (controls palette)
- **UI style**: clinical / terminal  (controls typography and visual weight)

Clinical (default) — designed for medical professionals:
  System sans-serif (SF Pro, Segoe UI, etc.), 13 px base, rounded corners,
  softer visual weight, generous padding.  Approachable, not intimidating.

Terminal — designed for power users / developers:
  Monospace (SF Mono, Fira Code, etc.), 12 px base, minimal border-radius,
  compact padding, letter-spacing on labels.  The original Redakt look.
"""

from PySide6.QtCore import QObject, Qt, QSettings, Signal
from PySide6.QtGui import QGuiApplication

# ── Settings keys ────────────────────────────────────────────────────────────
_KEY_THEME = "config/theme"
_KEY_UI_STYLE = "config/ui_style"

# ── Font stacks ──────────────────────────────────────────────────────────────
_FONT_CLINICAL = (
    '"SF Pro Text", "SF Pro", "Segoe UI", "Helvetica Neue", '
    "Helvetica, Arial, sans-serif"
)
_FONT_CLINICAL_MONO = (
    '"SF Mono", "Fira Code", "JetBrains Mono", '
    "Menlo, Consolas, monospace"
)
_FONT_TERMINAL = (
    '"SF Mono", "Fira Code", "JetBrains Mono", '
    "Menlo, Consolas, monospace"
)

# ── Dark palette ─────────────────────────────────────────────────────────────
_DARK = {
    "BG_DARKEST": "#111111",
    "BG_DARK": "#1a1a1a",
    "BG_MID": "#252525",
    "BG_LIGHT": "#303030",
    "BG_LIGHTER": "#3d3d3d",
    "BORDER": "#333333",
    "BORDER_ACTIVE": "#555555",
    "TEXT_PRIMARY": "#d4d4d4",
    "TEXT": "#d4d4d4",
    "TEXT_SECONDARY": "#808080",
    "TEXT_DIM": "#808080",
    "TEXT_VDIM": "#555555",
    "ACCENT": "#e78a4e",
    "ACCENT_DIM": "#c47a42",
    "ACCENT_GLOW": "#e78a4e22",
    "ERROR": "#d46b6b",
    "WARNING": "#d4a04e",
    "SUCCESS": "#6bbd6b",
    "BLUE": "#7aabdb",
}

# ── Light palette ────────────────────────────────────────────────────────────
_LIGHT = {
    "BG_DARKEST": "#fafaf9",
    "BG_DARK": "#fefefe",
    "BG_MID": "#f5f5f4",
    "BG_LIGHT": "#e7e5e4",
    "BG_LIGHTER": "#d6d3d1",
    "BORDER": "#d6d3d1",
    "BORDER_ACTIVE": "#a8a29e",
    "TEXT_PRIMARY": "#1c1917",
    "TEXT": "#1c1917",
    "TEXT_SECONDARY": "#57534e",
    "TEXT_DIM": "#78716c",
    "TEXT_VDIM": "#a8a29e",
    "ACCENT": "#b45309",
    "ACCENT_DIM": "#92400e",
    "ACCENT_GLOW": "#b4530922",
    "ERROR": "#b91c1c",
    "WARNING": "#a16207",
    "SUCCESS": "#15803d",
    "BLUE": "#1d4ed8",
}

# Legacy exports for backwards compatibility during migration
BG_DARKEST = _DARK["BG_DARKEST"]
BG_DARK = _DARK["BG_DARK"]
BG_MID = _DARK["BG_MID"]
BG_LIGHT = _DARK["BG_LIGHT"]
BG_LIGHTER = _DARK["BG_LIGHTER"]
BORDER = _DARK["BORDER"]
BORDER_ACTIVE = _DARK["BORDER_ACTIVE"]
TEXT_PRIMARY = _DARK["TEXT_PRIMARY"]
TEXT_SECONDARY = _DARK["TEXT_SECONDARY"]
TEXT_DIM = _DARK["TEXT_DIM"]
ACCENT = _DARK["ACCENT"]
ACCENT_DIM = _DARK["ACCENT_DIM"]
ACCENT_GLOW = _DARK["ACCENT_GLOW"]
ERROR = _DARK["ERROR"]
WARNING = _DARK["WARNING"]
SUCCESS = _DARK["SUCCESS"]


# ── Style parameters ─────────────────────────────────────────────────────────

def _style_params(style: str) -> dict:
    """Return typography/sizing params for a UI style."""
    if style == "clinical":
        return {
            "font": _FONT_CLINICAL,
            "font_mono": _FONT_CLINICAL_MONO,
            "base_size": 13,
            "small_size": 11,
            "tiny_size": 10,
            "btn_size": 12,
            "btn_padding": "7px 18px",
            "radius": 5,
            "small_radius": 3,
            "label_spacing": "0.5px",
            "section_spacing": "1px",
            "hint_style": "font-style: italic;",
            "header_size": 10,
            "table_size": 12,
            "text_browser_size": 13,
        }
    else:  # terminal
        return {
            "font": _FONT_TERMINAL,
            "font_mono": _FONT_TERMINAL,
            "base_size": 12,
            "small_size": 11,
            "tiny_size": 9,
            "btn_size": 11,
            "btn_padding": "6px 16px",
            "radius": 3,
            "small_radius": 2,
            "label_spacing": "2px",
            "section_spacing": "1px",
            "hint_style": "font-style: italic;",
            "header_size": 10,
            "table_size": 11,
            "text_browser_size": 12,
        }


def _build_stylesheet(c: dict, style: str = "clinical") -> str:
    s = _style_params(style)
    return f"""
/* ── Base ─────────────────────────────────────────────────── */

QMainWindow, QDialog, QWidget {{
    background-color: {c["BG_DARK"]};
    color: {c["TEXT_PRIMARY"]};
    font-family: {s["font"]};
    font-size: {s["base_size"]}px;
}}

QLabel {{
    color: {c["TEXT_PRIMARY"]};
    font-family: {s["font"]};
}}

/* ── Buttons ──────────────────────────────────────────────── */

QPushButton {{
    background-color: {c["BG_MID"]};
    color: {c["TEXT_PRIMARY"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["radius"]}px;
    padding: {s["btn_padding"]};
    font-size: {s["btn_size"]}px;
    font-family: {s["font"]};
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {c["BG_LIGHT"]};
    border-color: {c["BORDER_ACTIVE"]};
    color: {c["TEXT_PRIMARY"]};
}}

QPushButton:pressed {{
    background-color: {c["BG_LIGHTER"]};
    color: {c["TEXT_PRIMARY"]};
    border-color: {c["BORDER_ACTIVE"]};
}}

QPushButton:disabled {{
    background-color: {c["BG_DARK"]};
    color: {c["TEXT_DIM"]};
    border-color: {c["BORDER"]};
}}

QPushButton#primary {{
    background-color: {c["ACCENT"]};
    color: {c["BG_DARKEST"]};
    border: none;
    font-weight: bold;
    border-radius: {s["radius"]}px;
}}

QPushButton#primary:hover {{
    background-color: {c["ACCENT_DIM"]};
}}

QPushButton#primary:pressed {{
    background-color: {c["ACCENT_DIM"]};
}}

QPushButton#primary:disabled {{
    background-color: {c["BG_LIGHT"]};
    color: {c["TEXT_DIM"]};
}}

/* ── ComboBox ─────────────────────────────────────────────── */

QComboBox {{
    background-color: {c["BG_MID"]};
    color: {c["TEXT_PRIMARY"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["radius"]}px;
    padding: 4px 8px;
    font-family: {s["font"]};
    font-size: {s["small_size"]}px;
}}

QComboBox:hover {{
    border-color: {c["BORDER_ACTIVE"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: {c["BG_MID"]};
    color: {c["TEXT_PRIMARY"]};
    selection-background-color: {c["ACCENT"]};
    selection-color: {c["BG_DARKEST"]};
    border: 1px solid {c["BG_LIGHT"]};
    outline: none;
}}

/* ── ProgressBar ──────────────────────────────────────────── */

QProgressBar {{
    background-color: {c["BG_MID"]};
    border: none;
    border-radius: 2px;
    height: 4px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {c["ACCENT"]};
    border-radius: 2px;
}}

/* ── ScrollArea / ScrollBar ───────────────────────────────── */

QScrollArea {{
    border: none;
    background-color: transparent;
}}

QScrollBar:vertical {{
    background: {c["BG_DARK"]};
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {c["BG_LIGHT"]};
    min-height: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c["BG_LIGHTER"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {c["BG_DARK"]};
    height: 8px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {c["BG_LIGHT"]};
    min-width: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c["BG_LIGHTER"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Table ────────────────────────────────────────────────── */

QTableWidget {{
    background-color: {c["BG_DARK"]};
    color: {c["TEXT_PRIMARY"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["radius"]}px;
    gridline-color: {c["BG_MID"]};
    font-family: {s["font"]};
    font-size: {s["table_size"]}px;
    selection-background-color: {c["ACCENT_GLOW"]};
    selection-color: {c["TEXT_PRIMARY"]};
}}

QTableWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {c["BG_MID"]};
}}

QTableWidget::item:selected {{
    background-color: {c["ACCENT_GLOW"]};
    color: {c["TEXT_PRIMARY"]};
}}

QHeaderView::section {{
    background-color: {c["BG_MID"]};
    color: {c["TEXT_SECONDARY"]};
    border: none;
    border-bottom: 1px solid {c["BORDER"]};
    border-right: 1px solid {c["BG_DARK"]};
    padding: 6px 8px;
    font-size: {s["header_size"]}px;
    font-weight: bold;
    letter-spacing: {s["section_spacing"]};
}}

/* ── GroupBox ─────────────────────────────────────────────── */

QGroupBox {{
    color: {c["TEXT_SECONDARY"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["radius"]}px;
    margin-top: 10px;
    padding-top: 18px;
    font-size: {s["small_size"]}px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {c["TEXT_SECONDARY"]};
}}

/* ── Dialog / MessageBox ──────────────────────────────────── */

QMessageBox {{
    background-color: {c["BG_DARK"]};
}}

QMessageBox QLabel {{
    color: {c["TEXT_PRIMARY"]};
}}

/* ── LineEdit ─────────────────────────────────────────────── */

QLineEdit {{
    background-color: {c["BG_MID"]};
    color: {c["TEXT_PRIMARY"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["radius"]}px;
    padding: 5px 10px;
    font-family: {s["font"]};
    font-size: {s["base_size"]}px;
    selection-background-color: {c["ACCENT_GLOW"]};
    selection-color: {c["TEXT_PRIMARY"]};
}}

QLineEdit:focus {{
    border-color: {c["BORDER_ACTIVE"]};
}}

/* ── RadioButton / CheckBox ───────────────────────────────── */

QRadioButton {{
    color: {c["TEXT_PRIMARY"]};
    spacing: 8px;
    font-family: {s["font"]};
    font-size: {s["base_size"]}px;
}}

QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 2px solid {c["BG_LIGHTER"]};
    border-radius: 9px;
    background: {c["BG_MID"]};
}}

QRadioButton::indicator:checked {{
    background: {c["ACCENT"]};
    border-color: {c["ACCENT"]};
}}

QRadioButton::indicator:hover {{
    border-color: {c["BORDER_ACTIVE"]};
}}

QCheckBox {{
    color: {c["TEXT_PRIMARY"]};
    spacing: 6px;
    font-family: {s["font"]};
    font-size: {s["base_size"]}px;
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 2px solid {c["BG_LIGHTER"]};
    border-radius: {s["small_radius"]}px;
    background: {c["BG_MID"]};
}}

QCheckBox::indicator:checked {{
    background: {c["ACCENT"]};
    border-color: {c["ACCENT"]};
}}

QCheckBox::indicator:hover {{
    border-color: {c["BORDER_ACTIVE"]};
}}

/* ── Splitter ─────────────────────────────────────────────── */

QSplitter::handle {{
    background-color: {c["BG_MID"]};
}}

QSplitter::handle:hover {{
    background-color: {c["BG_LIGHTER"]};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ── TextBrowser ──────────────────────────────────────────── */

QTextBrowser {{
    background-color: {c["BG_DARK"]};
    color: {c["TEXT_PRIMARY"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["radius"]}px;
    padding: 12px;
    font-family: {s["font_mono"]};
    font-size: {s["text_browser_size"]}px;
    selection-background-color: {c["ACCENT_GLOW"]};
    selection-color: {c["TEXT_PRIMARY"]};
}}

/* ── ToolTip ──────────────────────────────────────────────── */

QToolTip {{
    background-color: {c["BG_MID"]};
    color: {c["TEXT_PRIMARY"]};
    border: 1px solid {c["BG_LIGHT"]};
    padding: 6px 10px;
    font-family: {s["font"]};
    font-size: {s["small_size"]}px;
    border-radius: {s["small_radius"]}px;
}}

/* ── ObjectName selectors ────────────────────────────────── */

QLabel#sectionLabel {{
    font-size: {s["tiny_size"]}px;
    font-weight: 600;
    color: {c["TEXT_DIM"]};
    letter-spacing: {s["label_spacing"]};
    padding: 2px 0;
}}

QLabel#sectionHint {{
    font-size: {s["tiny_size"]}px;
    color: {c["TEXT_VDIM"]};
    padding: 0 0 2px 0;
    {s["hint_style"]}
}}

QPushButton#secondary {{
    background-color: {c["BG_LIGHT"]};
    color: {c["TEXT_DIM"]};
    border: 1px solid {c["BORDER"]};
    border-radius: {s["small_radius"]}px;
    font-size: {s["tiny_size"]}px;
    padding: 4px 12px;
}}

QPushButton#secondary:hover {{
    color: {c["TEXT_PRIMARY"]};
    border-color: {c["BORDER_ACTIVE"]};
}}
"""


DARK_STYLESHEET = _build_stylesheet(_DARK, "clinical")
LIGHT_STYLESHEET = _build_stylesheet(_LIGHT, "clinical")


class ThemeManager(QObject):
    """Manages theme preference and UI style, emits theme_changed when either changes."""

    theme_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    # ── Color theme (dark / light / system) ─────────────────────────

    def get_theme(self) -> str:
        """Return stored preference: 'dark', 'light', or 'system'."""
        s = QSettings()
        return str(s.value(_KEY_THEME, "dark"))

    def set_theme(self, value: str):
        """Persist theme preference and emit theme_changed."""
        s = QSettings()
        s.setValue(_KEY_THEME, value)
        s.sync()
        self.theme_changed.emit()

    def get_effective_theme(self) -> str:
        """Return 'dark' or 'light' (resolves 'system')."""
        pref = self.get_theme()
        if pref == "system":
            return self._detect_system_theme()
        return pref if pref in ("dark", "light") else "dark"

    def _detect_system_theme(self) -> str:
        app = QGuiApplication.instance()
        if app and hasattr(app, "styleHints"):
            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                scheme = hints.colorScheme()
                if scheme == Qt.ColorScheme.Dark:
                    return "dark"
                if scheme == Qt.ColorScheme.Light:
                    return "light"
        return "dark"

    # ── UI style (clinical / terminal) ───────────────────────────────

    def get_ui_style(self) -> str:
        """Return stored UI style: 'clinical' or 'terminal'."""
        s = QSettings()
        val = str(s.value(_KEY_UI_STYLE, "clinical"))
        return val if val in ("clinical", "terminal") else "clinical"

    def set_ui_style(self, value: str):
        """Persist UI style preference and emit theme_changed."""
        s = QSettings()
        s.setValue(_KEY_UI_STYLE, value)
        s.sync()
        self.theme_changed.emit()

    # ── Combined accessors ──────────────────────────────────────────

    def get_colors(self) -> dict:
        """Return color dict for the current effective theme."""
        return _DARK if self.get_effective_theme() == "dark" else _LIGHT

    def get_stylesheet(self) -> str:
        """Return stylesheet for the current effective theme + UI style."""
        c = self.get_colors()
        style = self.get_ui_style()
        return _build_stylesheet(c, style)

    def get_font_family(self) -> str:
        """Return the primary font family string for the current UI style."""
        return _FONT_CLINICAL if self.get_ui_style() == "clinical" else _FONT_TERMINAL

    def get_mono_font(self) -> str:
        """Return the monospace font family string."""
        return _FONT_CLINICAL_MONO

    def apply_to_app(self):
        """Apply current theme to QApplication."""
        app = QGuiApplication.instance()
        if app:
            app.setStyleSheet(self.get_stylesheet())


# Singleton, set by app on startup
theme_manager: ThemeManager | None = None
