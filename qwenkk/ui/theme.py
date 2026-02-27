"""Factory AI dark theme for QwenKK.

Design language (matched to Factory / Claude Code desktop app):
- Neutral dark gray backgrounds (#1a1a1a) — NOT blue-tinted
- Minimal accent usage — warm orange only for primary actions
- Clean monospace typography
- Very subtle borders, minimal visual noise
- Professional, restrained, industrial
"""

# ── Color palette ────────────────────────────────────────────────────────────
# Neutral dark grays — NO blue tint

BG_DARKEST = "#111111"       # deepest (status bar, code blocks)
BG_DARK = "#1a1a1a"          # main background
BG_MID = "#252525"           # panels / surfaces
BG_LIGHT = "#303030"         # elevated surfaces / inputs
BG_LIGHTER = "#3d3d3d"       # hover states

BORDER = "#333333"           # subtle borders
BORDER_ACTIVE = "#555555"    # active / focus border

TEXT_PRIMARY = "#d4d4d4"     # main text (warm light gray)
TEXT_SECONDARY = "#808080"   # muted text
TEXT_DIM = "#555555"         # very dim text / placeholders

ACCENT = "#e78a4e"          # warm orange (used sparingly)
ACCENT_DIM = "#c47a42"      # deeper orange
ACCENT_GLOW = "#e78a4e22"   # subtle glow

ERROR = "#d46b6b"            # muted red
WARNING = "#d4a04e"          # muted amber
SUCCESS = "#6bbd6b"          # muted green

DARK_STYLESHEET = f"""
/* ── Base ─────────────────────────────────────────────────── */

QMainWindow, QDialog, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-size: 12px;
}}

QLabel {{
    color: {TEXT_PRIMARY};
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
}}

/* ── Buttons ──────────────────────────────────────────────── */

QPushButton {{
    background-color: {BG_MID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 6px 16px;
    font-size: 11px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-weight: 500;
    letter-spacing: 0.5px;
}}

QPushButton:hover {{
    background-color: {BG_LIGHT};
    border-color: {BORDER_ACTIVE};
    color: {TEXT_PRIMARY};
}}

QPushButton:pressed {{
    background-color: {BG_LIGHTER};
    color: {TEXT_PRIMARY};
    border-color: {BORDER_ACTIVE};
}}

QPushButton:disabled {{
    background-color: {BG_DARK};
    color: {TEXT_DIM};
    border-color: {BORDER};
}}

QPushButton#primary {{
    background-color: {ACCENT};
    color: {BG_DARKEST};
    border: none;
    font-weight: bold;
    letter-spacing: 0.5px;
}}

QPushButton#primary:hover {{
    background-color: #f09a5e;
}}

QPushButton#primary:pressed {{
    background-color: {ACCENT_DIM};
}}

QPushButton#primary:disabled {{
    background-color: {BG_LIGHT};
    color: {TEXT_DIM};
}}

/* ── ComboBox ─────────────────────────────────────────────── */

QComboBox {{
    background-color: {BG_MID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px 8px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-size: 11px;
}}

QComboBox:hover {{
    border-color: {BORDER_ACTIVE};
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
    background-color: {BG_MID};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: {BG_DARKEST};
    border: 1px solid {BG_LIGHT};
    outline: none;
}}

/* ── ProgressBar ──────────────────────────────────────────── */

QProgressBar {{
    background-color: {BG_MID};
    border: none;
    border-radius: 2px;
    height: 4px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 2px;
}}

/* ── ScrollArea / ScrollBar ───────────────────────────────── */

QScrollArea {{
    border: none;
    background-color: transparent;
}}

QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {BG_LIGHT};
    min-height: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {BG_LIGHTER};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {BG_DARK};
    height: 8px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {BG_LIGHT};
    min-width: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {BG_LIGHTER};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Table ────────────────────────────────────────────────── */

QTableWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    gridline-color: {BG_MID};
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-size: 11px;
    selection-background-color: {ACCENT_GLOW};
    selection-color: {TEXT_PRIMARY};
}}

QTableWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {BG_MID};
}}

QTableWidget::item:selected {{
    background-color: {ACCENT_GLOW};
    color: {TEXT_PRIMARY};
}}

QHeaderView::section {{
    background-color: {BG_MID};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BG_DARK};
    padding: 6px 8px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}}

/* ── GroupBox ─────────────────────────────────────────────── */

QGroupBox {{
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    margin-top: 10px;
    padding-top: 18px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_SECONDARY};
}}

/* ── Dialog / MessageBox ──────────────────────────────────── */

QMessageBox {{
    background-color: {BG_DARK};
}}

QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
}}

/* ── LineEdit ─────────────────────────────────────────────── */

QLineEdit {{
    background-color: {BG_MID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px 8px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    selection-background-color: {ACCENT_GLOW};
    selection-color: {TEXT_PRIMARY};
}}

QLineEdit:focus {{
    border-color: {BORDER_ACTIVE};
}}

/* ── RadioButton / CheckBox ───────────────────────────────── */

QRadioButton {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-size: 12px;
}}

QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {BG_LIGHTER};
    border-radius: 7px;
    background: {BG_MID};
}}

QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QRadioButton::indicator:hover {{
    border-color: {BORDER_ACTIVE};
}}

QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 6px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {BG_LIGHTER};
    border-radius: 2px;
    background: {BG_MID};
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

QCheckBox::indicator:hover {{
    border-color: {BORDER_ACTIVE};
}}

/* ── Splitter ─────────────────────────────────────────────── */

QSplitter::handle {{
    background-color: {BG_MID};
}}

QSplitter::handle:hover {{
    background-color: {BG_LIGHTER};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ── TextBrowser ──────────────────────────────────────────── */

QTextBrowser {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 12px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-size: 12px;
    selection-background-color: {ACCENT_GLOW};
    selection-color: {TEXT_PRIMARY};
}}

/* ── ToolTip ──────────────────────────────────────────────── */

QToolTip {{
    background-color: {BG_MID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BG_LIGHT};
    padding: 4px 8px;
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", Menlo, Consolas, monospace;
    font-size: 11px;
}}
"""
