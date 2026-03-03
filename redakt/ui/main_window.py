"""Main application window — visual document redaction workflow.

Features:
- Split view: highlighted document text | redacted preview
- Entity table with per-item checkboxes (toggle individual redactions)
- Category chips to toggle entire PII categories at once
- Export as PDF / DOCX / TXT / Markdown
- Chat with document (Q&A)
- Factory AI neutral dark theme
"""

import html as _html
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from redakt.constants import SUPPORTED_EXTENSIONS, Language
from redakt.core.anonymizer import Anonymizer
from redakt.core.entities import PIIEntity, PIIResponse
from redakt.core.llamacpp_manager import LlamaCppManager
from redakt.core.redactor import (
    CATEGORY_COLORS,
    CATEGORY_LABELS_TR,
    TextSpan,
    find_entity_spans,
    render_highlighted_html,
    render_redacted_html,
)
from redakt.core.worker import AsyncWorker
from redakt.core.md_renderer import render_markdown
from redakt.exporters import (
    EXPORT_FORMATS,
    export_redacted,
)
from redakt.parsers import get_parser
from redakt.ui.i18n import t
from redakt.ui.settings_dialog import SettingsDialog, load_settings, save_settings
from redakt.ui.setup_wizard import SetupWizard
from redakt.ui.status_bar import StatusBar
from redakt.ui import theme as theme_module

# ── Theme colors (fallback when theme_manager not yet initialized) ─────────
_DARK = {
    "BG_DARKEST": "#111111", "BG_DARK": "#1a1a1a", "BG_MID": "#252525",
    "BG_LIGHT": "#303030", "BG_LIGHTER": "#3d3d3d", "BORDER": "#333333",
    "TEXT": "#d4d4d4", "TEXT_DIM": "#808080", "TEXT_VDIM": "#555555",
    "ACCENT": "#e78a4e", "ACCENT_DIM": "#c47a42", "ERROR": "#d46b6b",
    "WARNING": "#d4a04e", "SUCCESS": "#6bbd6b", "BLUE": "#7aabdb",
}


def _c() -> dict:
    """Current theme colors."""
    tm = getattr(theme_module, "theme_manager", None)
    return tm.get_colors() if tm else _DARK


_MONO = (
    "'SF Mono', 'Fira Code', 'JetBrains Mono', "
    "Menlo, Consolas, monospace"
)


def _font() -> str:
    """Current UI font family from theme manager."""
    tm = getattr(theme_module, "theme_manager", None)
    return tm.get_font_family() if tm else _MONO


class MainWindow(QMainWindow):
    _sig_scan_status = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Redakt")
        self.setMinimumSize(900, 700)
        self.resize(1100, 800)
        self.setAcceptDrops(True)

        # ── State ──
        self._current_file: Path | None = None
        self._extracted_text: str = ""
        self._entities: list[PIIEntity] = []
        self._spans: list[TextSpan] = []
        self._entity_enabled: list[bool] = []  # per-item redaction toggle
        self._model_ready = False
        self._updating_table = False  # guard against recursive signals
        self._chat_history: list[dict] = []  # multi-turn chat history
        self._original_placeholders: dict[str, str] = {}
        self._birth_date_text: str | None = None
        self._is_image: bool = False

        # ── Managers ──
        self.llamacpp_manager = LlamaCppManager()
        self.anonymizer = Anonymizer()
        self._workers: list[AsyncWorker] = []

        # Load persisted settings
        saved = load_settings()
        if saved["gguf_path"]:
            from pathlib import Path as _P
            gguf_p = _P(saved["gguf_path"])
            if gguf_p.exists():
                self.llamacpp_manager.gguf_path = gguf_p

        # Category chip buttons (built after scan)
        self._category_chips: dict[str, QPushButton] = {}

        self._setup_ui()
        self._connect_signals()
        self._set_ui_state("empty")

    # ── UI Construction ──────────────────────────────────────────────

    @staticmethod
    def _tech_label(text: str, color: str | None = None) -> QLabel:
        """Create a tech-style section label (styled via #sectionLabel in stylesheet)."""
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        if color:
            lbl.setStyleSheet(f"color: {color};")
        return lbl

    @staticmethod
    def _section_hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionHint")
        lbl.setWordWrap(True)
        return lbl

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(16, 12, 16, 8)

        # ── Top bar ──
        top = QHBoxLayout()

        # Title with cyber glow
        title = QLabel("REDAKT")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {_c()["ACCENT"]}; "
            f"letter-spacing: 6px;"
        )
        top.addWidget(title)

        subtitle = QLabel("LOCAL DE-IDENTIFICATION")
        subtitle.setStyleSheet(
            f"font-size: 11px; color: {_c()["TEXT_DIM"]}; letter-spacing: 3px; "
            f"padding-top: 8px;"
        )
        top.addWidget(subtitle)

        top.addStretch()
        self.settings_btn = QPushButton("CONFIG")
        self.settings_btn.setObjectName("secondary")
        self.settings_btn.setToolTip("Configure model, backend, and language settings")
        self.settings_btn.clicked.connect(self._open_settings)
        top.addWidget(self.settings_btn)
        root.addLayout(top)

        # Thin accent line under title
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: qlineargradient(x1:0, x2:1, "
            f"stop:0 {_c()["TEXT_DIM"]}, stop:0.5 {_c()["TEXT_DIM"]}44, stop:1 transparent);"
        )
        root.addWidget(line)

        # ── File bar ──
        file_bar = QHBoxLayout()
        self.file_label = QLabel("NO FILE LOADED")
        self.file_label.setStyleSheet(
            f"font-size: 11px; color: {_c()["TEXT_DIM"]}; padding: 4px 0; "
            f"letter-spacing: 1px;"
        )
        file_bar.addWidget(self.file_label, stretch=1)
        self.open_btn = QPushButton("OPEN FILE")
        self.open_btn.setToolTip("Open a medical document (PDF, DOCX, XLSX, or image)")
        self.open_btn.clicked.connect(self._open_file_dialog)
        file_bar.addWidget(self.open_btn)
        self.clear_btn = QPushButton("CLEAR")
        self.clear_btn.setToolTip("Close the current document and reset")
        self.clear_btn.clicked.connect(self._clear)
        file_bar.addWidget(self.clear_btn)
        root.addLayout(file_bar)

        self._workflow_hint = QLabel(
            "1. Open file  \u2192  2. Scan for PII  \u2192  3. Review & toggle  \u2192  4. Export"
        )
        self._workflow_hint.setObjectName("sectionHint")
        self._workflow_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._workflow_hint.setWordWrap(True)
        root.addWidget(self._workflow_hint)

        # ── Main vertical splitter ──
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Top section: Document Text | Redacted Preview ──
        text_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: original text with highlights
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        self.left_label = self._tech_label("Document Text")
        left_layout.addWidget(self.left_label)
        self._left_hint = self._section_hint(
            "Original document text. PII entities are highlighted after scanning."
        )
        left_layout.addWidget(self._left_hint)
        self.original_view = QTextBrowser()
        self.original_view.setOpenExternalLinks(False)
        left_layout.addWidget(self.original_view)
        text_splitter.addWidget(left)

        # Right panel: redacted preview
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        self.right_label = self._tech_label("Redacted Preview")
        right_layout.addWidget(self.right_label)
        self._right_hint = self._section_hint(
            "Preview with personal data replaced by black bars."
        )
        right_layout.addWidget(self._right_hint)
        self.redacted_view = QTextBrowser()
        self.redacted_view.setOpenExternalLinks(False)
        right_layout.addWidget(self.redacted_view)
        text_splitter.addWidget(right)

        text_splitter.setSizes([500, 500])
        text_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(text_splitter)

        # ── Middle section: Entity panel (chips + table) ──
        table_panel = QWidget()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)

        # Header row: label + category chips
        header_row = QHBoxLayout()
        self.table_label = self._tech_label("Detected PII")
        header_row.addWidget(self.table_label)
        header_row.addSpacing(16)

        # Category chip container (populated after scan)
        self.chip_container = QHBoxLayout()
        self.chip_container.setSpacing(6)
        header_row.addLayout(self.chip_container)
        header_row.addStretch()

        # Select All / None buttons
        self.select_all_btn = QPushButton("SELECT ALL")
        self.select_all_btn.setObjectName("secondary")
        self.select_all_btn.setFixedHeight(22)
        self.select_all_btn.setToolTip("Enable all detected entities for redaction")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_all_btn.setVisible(False)
        header_row.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("SELECT NONE")
        self.select_none_btn.setObjectName("secondary")
        self.select_none_btn.setFixedHeight(22)
        self.select_none_btn.setToolTip("Disable all entities (nothing will be redacted)")
        self.select_none_btn.clicked.connect(self._select_none)
        self.select_none_btn.setVisible(False)
        header_row.addWidget(self.select_none_btn)

        table_layout.addLayout(header_row)
        self._entity_hint = self._section_hint(
            "Toggle individual items on/off. Unchecked items won't be redacted."
        )
        table_layout.addWidget(self._entity_hint)

        # Entity table: checkbox | # | Original | Category | Placeholder | Conf
        self.entity_table = QTableWidget(0, 6)
        self.entity_table.setHorizontalHeaderLabels(
            ["", "#",
             t("col_original", self._lang),
             t("col_type", self._lang),
             t("col_replacement", self._lang),
             t("col_conf", self._lang)]
        )
        hdr = self.entity_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(0, 36)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(1, 40)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(5, 60)
        self.entity_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.entity_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.entity_table.cellClicked.connect(self._on_entity_clicked)
        table_layout.addWidget(self.entity_table)
        self.main_splitter.addWidget(table_panel)

        # ── Bottom section: Chat / Summary panel ──
        self.chat_panel = QWidget()
        chat_layout = QVBoxLayout(self.chat_panel)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(4)

        # Chat header with toggle buttons
        chat_header = QHBoxLayout()
        self.chat_label = self._tech_label("Document AI")
        chat_header.addWidget(self.chat_label)
        chat_header.addStretch()

        self.clear_chat_btn = QPushButton("CLEAR CHAT")
        self.clear_chat_btn.setObjectName("secondary")
        self.clear_chat_btn.setFixedHeight(22)
        self.clear_chat_btn.setToolTip("Clear conversation history")
        self.clear_chat_btn.clicked.connect(self._clear_chat)
        chat_header.addWidget(self.clear_chat_btn)

        chat_layout.addLayout(chat_header)
        self._ai_hint = self._section_hint(
            "AI-powered document analysis. Ask questions about the document."
        )
        chat_layout.addWidget(self._ai_hint)

        # Chat message display
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.setHtml("")  # placeholder set by _relabel_ui / _set_ui_state
        chat_layout.addWidget(self.chat_view)

        # Chat input row
        chat_input_row = QHBoxLayout()
        chat_input_row.setSpacing(6)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask a question about the document...")
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.chat_input.setEnabled(False)
        chat_input_row.addWidget(self.chat_input)

        self.send_btn = QPushButton("SEND")
        self.send_btn.setMinimumSize(70, 30)
        self.send_btn.setToolTip("Send your question to the AI")
        self.send_btn.clicked.connect(self._send_chat_message)
        self.send_btn.setEnabled(False)
        chat_input_row.addWidget(self.send_btn)

        chat_layout.addLayout(chat_input_row)
        self.main_splitter.addWidget(self.chat_panel)
        self.chat_panel.setVisible(False)  # Hidden: single-function app, no talk-to-document

        self.main_splitter.setSizes([500, 250, 0])  # More space for doc + redaction
        self.main_splitter.setChildrenCollapsible(False)
        root.addWidget(self.main_splitter, stretch=1)

        # ── Progress bar (hidden by default) ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        root.addWidget(self.progress_bar)

        # ── Controls bar ──
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self._lang_label = QLabel("LANG:")
        self._lang_label.setObjectName("sectionLabel")
        controls.addWidget(self._lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("TR", Language.TR)
        self.lang_combo.addItem("EN", Language.EN)
        self.lang_combo.setFixedWidth(60)
        self.lang_combo.currentIndexChanged.connect(self._relabel_ui)
        controls.addWidget(self.lang_combo)

        controls.addSpacing(8)

        self.age_mode_cb = QCheckBox("AGE-BASED DATES")
        self.age_mode_cb.setToolTip(
            "When a birth date is found, replace other dates with patient age "
            "(e.g., 'at age 3.5 yrs'). Useful for pediatric documents."
        )
        self.age_mode_cb.setChecked(False)
        self.age_mode_cb.toggled.connect(self._on_age_mode_toggled)
        controls.addWidget(self.age_mode_cb)

        # Birth date display (shown when age conversion used a birth date)
        self._birth_date_label = QLabel()
        self._birth_date_label.setStyleSheet(
            f"font-size: 10px; color: {_c()['TEXT_DIM']}; letter-spacing: 0.5px;"
        )
        self._birth_date_value = QLabel()
        self._birth_date_value.setStyleSheet(
            f"font-size: 10px; color: {_c()['TEXT']}; font-weight: 600;"
        )
        self._change_birth_btn = QPushButton()
        self._change_birth_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_c()['ACCENT']}; "
            f"font-size: 10px; border: none; padding: 2px 6px; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )
        self._change_birth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_birth_btn.clicked.connect(self._on_change_birth_date)
        self._birth_date_widget = QWidget()
        birth_layout = QHBoxLayout(self._birth_date_widget)
        birth_layout.setContentsMargins(8, 0, 0, 0)
        birth_layout.setSpacing(6)
        birth_layout.addWidget(self._birth_date_label)
        birth_layout.addWidget(self._birth_date_value)
        birth_layout.addWidget(self._change_birth_btn)
        self._birth_date_widget.setVisible(False)
        controls.addWidget(self._birth_date_widget)

        controls.addSpacing(8)

        self.scan_btn = QPushButton("SCAN FOR PII")
        self.scan_btn.setToolTip("Run AI analysis to detect all personal data in the document")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setMinimumWidth(160)
        self.scan_btn.setMinimumHeight(32)
        self.scan_btn.clicked.connect(self._start_scan)
        controls.addWidget(self.scan_btn)

        controls.addSpacing(12)

        controls.addStretch()

        self._export_label = QLabel("EXPORT:")
        self._export_label.setObjectName("sectionLabel")
        controls.addWidget(self._export_label)
        self.format_combo = QComboBox()
        for fmt in EXPORT_FORMATS:
            self.format_combo.addItem(fmt)
        self.format_combo.setFixedWidth(110)
        controls.addWidget(self.format_combo)

        self.export_btn = QPushButton("EXPORT REDACTED")
        self.export_btn.setToolTip("Export the redacted document with PII removed")
        self.export_btn.setMinimumHeight(32)
        self.export_btn.clicked.connect(self._export_file)
        controls.addWidget(self.export_btn)
        root.addLayout(controls)

        # ── Status bar ──
        self.status_bar = StatusBar()
        root.addWidget(self.status_bar)

        # Apply initial localization
        self._relabel_ui()

    # ── Localization ──────────────────────────────────────────────────

    @property
    def _lang(self):
        """Current UI language from the language combo."""
        combo = getattr(self, "lang_combo", None)
        if combo is not None:
            data = combo.currentData()
            if data:
                return data
        return Language.EN

    def _relabel_ui(self):
        """Update all UI text to the current language."""
        lang = self._lang

        # Top bar
        self.settings_btn.setText(t("config", lang))
        self.settings_btn.setToolTip(t("tip_config", lang))

        # File bar
        if not self._current_file:
            self.file_label.setText(t("no_file", lang))
        self.open_btn.setText(t("open_file", lang))
        self.open_btn.setToolTip(t("tip_open", lang))
        self.clear_btn.setText(t("clear", lang))
        self.clear_btn.setToolTip(t("tip_clear", lang))

        # Workflow hint
        self._workflow_hint.setText(t("workflow_hint", lang))

        # Panel headers
        if not self._entities:
            self.left_label.setText(t("document_text", lang))
        self.right_label.setText(t("redacted_preview", lang))

        # Section hints
        self._left_hint.setText(t("document_hint", lang))
        self._right_hint.setText(t("redacted_hint", lang))
        self._entity_hint.setText(t("entity_hint", lang))
        self._ai_hint.setText(t("ai_hint", lang))

        # Entity panel header
        if not self._entities:
            self.table_label.setText(t("detected_pii", lang))

        # Entity table headers
        self.entity_table.setHorizontalHeaderLabels(
            ["", "#",
             t("col_original", lang),
             t("col_type", lang),
             t("col_replacement", lang),
             t("col_conf", lang)]
        )

        # Select All / None buttons
        self.select_all_btn.setText(t("select_all", lang))
        self.select_all_btn.setToolTip(t("tip_select_all", lang))
        self.select_none_btn.setText(t("select_none", lang))
        self.select_none_btn.setToolTip(t("tip_select_none", lang))

        # Chat panel header
        self.chat_label.setText(t("document_ai", lang))
        self.clear_chat_btn.setText(t("clear_chat", lang))
        self.clear_chat_btn.setToolTip(t("tip_clear_chat", lang))
        self.chat_input.setPlaceholderText(t("ask_placeholder", lang))
        self.send_btn.setText(t("send", lang))
        self.send_btn.setToolTip(t("tip_send", lang))

        # Controls bar
        self._lang_label.setText(t("lang", lang))
        self.scan_btn.setText(t("scan_for_pii", lang))
        self.scan_btn.setToolTip(t("tip_scan", lang))
        self.age_mode_cb.setText(t("age_based_dates", lang))
        self.age_mode_cb.setToolTip(t("tip_age_mode", lang))
        if self._birth_date_text:
            self._birth_date_label.setText(t("birth_date_label", lang))
            self._change_birth_btn.setText(t("change_birth_date", lang))
            self._change_birth_btn.setToolTip(t("tip_change_birth_date", lang))
        self._export_label.setText(t("export", lang))
        self.export_btn.setText(t("export_redacted", lang))
        self.export_btn.setToolTip(t("tip_export", lang))
        self.status_bar.set_local_badge(t("status_local_badge", lang))
        self.status_bar.set_translations(
            ready=t("status_ready", lang),
            not_ready=t("status_not_ready", lang),
            processing=t("status_processing", lang),
            error=t("status_error", lang),
        )

    def _connect_signals(self):
        self.llamacpp_manager.server_ready.connect(self._on_model_ready)
        self.llamacpp_manager.error_occurred.connect(self._show_error)
        self.llamacpp_manager.error_occurred.connect(self._show_error)

        self._sig_scan_status.connect(self._slot_scan_status)

    # ── UI state management ──────────────────────────────────────────

    def _set_ui_state(self, state: str):
        if state == "empty":
            self.scan_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.chat_input.setEnabled(False)
            self.send_btn.setEnabled(False)
            lang = self._lang
            self.original_view.setHtml(
                f'<p style="color: {_c()["TEXT_VDIM"]}; font-size: 13px; text-align: center; '
                f"padding-top: 60px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('drop_here', lang)}</p>"
            )
            self.redacted_view.setHtml(
                f'<p style="color: {_c()["TEXT_VDIM"]}; font-size: 13px; text-align: center; '
                f"padding-top: 60px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('scan_to_preview', lang)}</p>"
            )
            self.entity_table.setRowCount(0)
            self.table_label.setText(t("detected_pii", lang))
            self.file_label.setText(t("no_file", lang))
            self.left_label.setText(t("document_text", lang))
            self._clear_category_chips()
            self._clear_chat()
        elif state == "file_loaded":
            lang = self._lang
            self.scan_btn.setEnabled(self._model_ready)
            self.export_btn.setEnabled(False)
            self.clear_btn.setEnabled(True)
            self.chat_input.setEnabled(self._model_ready)
            self.send_btn.setEnabled(self._model_ready)
            self.redacted_view.setHtml(
                f'<p style="color: {_c()["TEXT_VDIM"]}; font-size: 13px; text-align: center; '
                f"padding-top: 60px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('click_scan', lang)}</p>"
            )
            self.entity_table.setRowCount(0)
            self.table_label.setText(t("detected_pii", lang))
            self._clear_category_chips()
        elif state == "scanning":
            self.scan_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
        elif state == "scanned":
            self.scan_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.select_all_btn.setVisible(True)
            self.select_none_btn.setVisible(True)
        elif state == "error":
            self.scan_btn.setEnabled(True)
            self.export_btn.setEnabled(False)
            self.progress_bar.setVisible(False)

    # ── Lifecycle ────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not self._model_ready:
            self._run_setup_wizard()

    def closeEvent(self, event):
        self.llamacpp_manager.stop_server()
        super().closeEvent(event)

    def _run_setup_wizard(self):
        wizard = SetupWizard(self.llamacpp_manager, parent=self)
        wizard.setup_complete.connect(self._on_model_ready)
        wizard.exec()

    @Slot()
    def _on_theme_changed(self):
        """Refresh UI when theme changes (e.g. from settings)."""
        c = _c()

        # File label
        if self._current_file:
            self.file_label.setStyleSheet(
                f"font-size: 11px; color: {c['TEXT']}; padding: 4px 0; "
                f"letter-spacing: 0.5px;"
            )
        else:
            self.file_label.setStyleSheet(
                f"font-size: 11px; color: {c['TEXT_DIM']}; padding: 4px 0; "
                f"letter-spacing: 1px;"
            )

        # Birth date widgets
        self._birth_date_label.setStyleSheet(
            f"font-size: 10px; color: {c['TEXT_DIM']}; letter-spacing: 0.5px;"
        )
        self._birth_date_value.setStyleSheet(
            f"font-size: 10px; color: {c['TEXT']}; font-weight: 600;"
        )
        self._change_birth_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {c['ACCENT']}; "
            f"font-size: 10px; border: none; padding: 2px 6px; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )

        # Refresh content views
        if self._current_file:
            if self._entities:
                self._refresh_views()
            else:
                self._set_ui_state("file_loaded")
        else:
            self._set_ui_state("empty")
        self._clear_chat()

        # Status bar
        if hasattr(self, "status_bar") and hasattr(self.status_bar, "_apply_theme"):
            self.status_bar._apply_theme()

    @Slot()
    def _on_model_ready(self):
        self._model_ready = True
        self.status_bar.set_ready_status(True)
        self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
        if self._current_file:
            self.scan_btn.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.send_btn.setEnabled(True)

    # ── File handling ────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self._load_file(path)
            else:
                self._show_error(
                    t("unsupported_file", self._lang,
                      ext=path.suffix,
                      supported=", ".join(sorted(SUPPORTED_EXTENSIONS)))
                )

    @Slot()
    def _open_file_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("open_document", self._lang),
            str(Path.home() / "Desktop"),
            t("file_filter", self._lang, exts=exts),
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path):
        try:
            parser = get_parser(path)
            result = parser.extract_text(path)
        except Exception as e:
            self._show_error(t("file_read_failed", self._lang, error=e))
            return

        self._current_file = path
        self._extracted_text = result.text
        self._is_image = result.metadata.get("requires_vision", False)
        self._entities = []
        self._spans = []
        self._entity_enabled = []
        self._chat_history = []
        self._birth_date_text = None
        self._update_birth_date_display()

        lang = self._lang
        if self._is_image:
            char_count = 0
            self.file_label.setText(t("file_image", lang, name=path.name))
            self.file_label.setStyleSheet(
                f"font-size: 11px; color: {_c()["TEXT"]}; padding: 4px 0; "
                f"letter-spacing: 0.5px;"
            )
            self.left_label.setText(t("document_text", lang))
            img_msg = t("image_file_loaded", lang, name=_html.escape(path.name))
            parts = img_msg.split("\n\n", 1)
            self.original_view.setHtml(
                f'<p style="color: {_c()["TEXT_DIM"]}; font-size: 13px; text-align: center; '
                f"padding-top: 40px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{_html.escape(parts[0])}<br><br>"
                f'<span style="color: {_c()["TEXT_VDIM"]};">'
                f"{_html.escape(parts[1]) if len(parts) > 1 else ''}</span></p>"
            )
        else:
            char_count = len(result.text)
            self.file_label.setText(
                t("file_chars", lang, name=path.name, count=f"{char_count:,}")
            )
            self.file_label.setStyleSheet(
                f"font-size: 11px; color: {_c()["TEXT"]}; padding: 4px 0; "
                f"letter-spacing: 0.5px;"
            )
            self.left_label.setText(
                t("doc_text_chars", lang, count=f"{char_count:,}")
            )
            self.original_view.setPlainText(result.text)

        self._set_ui_state("file_loaded")

        # Update chat panel
        chat_msg = t("file_loaded_chat", lang, name=_html.escape(path.name))
        chat_lines = chat_msg.split("\n", 1)
        self.chat_view.setHtml(
            f'<p style="color: {_c()["TEXT_DIM"]}; font-size: 11px; '
            f"font-family: {_MONO}; letter-spacing: 0.5px;\">"
            f"{chat_lines[0]}<br>"
            f'<span style="color: {_c()["TEXT_DIM"]};">'
            f"{chat_lines[1] if len(chat_lines) > 1 else ''}</span></p>"
        )

    @Slot()
    def _clear(self):
        self._current_file = None
        self._extracted_text = ""
        self._is_image = False
        self._entities = []
        self._spans = []
        self._entity_enabled = []
        self._chat_history = []
        self._birth_date_text = None
        self._update_birth_date_display()
        self._set_ui_state("empty")

    # ── PII Scanning ─────────────────────────────────────────────────

    @Slot()
    def _start_scan(self):
        if not self._extracted_text and not self._is_image:
            return
        self.status_bar.set_active_inference(True)
        self._set_ui_state("scanning")
        self.anonymizer.language = self.lang_combo.currentData()

        if self._is_image:
            worker = AsyncWorker(self._run_image_scan, str(self._current_file))
        else:
            worker = AsyncWorker(self._run_scan, self._extracted_text)
        worker.finished.connect(self._on_scan_complete)
        worker.error.connect(self._on_scan_error)
        self._workers.append(worker)
        worker.start()

    async def _run_image_scan(self, image_path: str) -> PIIResponse:
        self._sig_scan_status.emit(t("scanning_image", self._lang))
        response = await self.anonymizer.detect_pii_from_image(image_path)
        entities = self.anonymizer._renumber_placeholders(response.entities)
        return PIIResponse(entities=entities, summary=response.summary or "Image scanned")

    async def _run_scan(self, text: str) -> PIIResponse:
        self._sig_scan_status.emit(t("scanning", self._lang))
        chunks = self.anonymizer.chunk_text(text)
        all_entities: dict[str, PIIEntity] = {}
        errors: list[str] = []

        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                self._sig_scan_status.emit(
                    t("scanning_chunk", self._lang, i=i + 1, n=len(chunks))
                )
            try:
                response = await self.anonymizer.detect_pii_from_text(chunk)
                for entity in response.entities:
                    if entity.original not in all_entities:
                        all_entities[entity.original] = entity
            except Exception as e:
                errors.append(f"Chunk {i + 1}: {e}")
                # Continue with remaining chunks

        if not all_entities and errors:
            # All chunks failed — raise the combined error
            raise RuntimeError("\n".join(errors))

        entities = self.anonymizer._renumber_placeholders(
            list(all_entities.values())
        )
        summary = f"Processed {len(chunks)} chunk(s)"
        if errors:
            summary += f" ({len(errors)} failed)"
        return PIIResponse(entities=entities, summary=summary)

    @Slot(object)
    def _on_scan_complete(self, response: PIIResponse):
        self.status_bar.set_active_inference(False)
        self._entities = response.entities

        if self._is_image and not self._extracted_text:
            # For images: generate display text from entities
            lang = self._lang
            lines = [t("pii_in_image", lang, count=len(self._entities)), ""]
            for e in self._entities:
                lines.append(f"  [{e.category.upper()}] {e.original}")
            self._extracted_text = "\n".join(lines)
            self.original_view.setPlainText(self._extracted_text)
            self.left_label.setText(
                t("detected_text_count", lang, count=len(self._entities))
            )

        self._spans = find_entity_spans(self._extracted_text, self._entities)
        self._entity_enabled = [True] * len(self._entities)

        # Auto-apply age conversion when birth date is found (decimal ages instead of redacted dates)
        self._original_placeholders = {
            e.original: e.placeholder for e in self._entities if e.category == "date"
        }
        _, self._birth_date_text = self.anonymizer._apply_age_conversion(
            self._entities, self._extracted_text
        )
        any_age_converted = any(
            e.category == "date" and not e.placeholder.startswith("[")
            for e in self._entities
        )
        if any_age_converted:
            self.age_mode_cb.blockSignals(True)
            self.age_mode_cb.setChecked(True)
            self.age_mode_cb.blockSignals(False)
            self._spans = find_entity_spans(self._extracted_text, self._entities)
        else:
            for e in self._entities:
                if e.original in self._original_placeholders:
                    e.placeholder = self._original_placeholders[e.original]
            self._original_placeholders.clear()
            self._birth_date_text = None

        self._update_birth_date_display()

        # Build category chips + table + views
        self._build_category_chips()
        self._populate_entity_table()
        self._refresh_views()
        self._set_ui_state("scanned")

    @Slot(str)
    def _on_scan_error(self, error: str):
        self.status_bar.set_active_inference(False)
        self._set_ui_state("error")
        self._show_error(t("scan_failed", self._lang, error=error))

    @Slot(str)
    def _slot_scan_status(self, msg: str):
        self.status_bar.set_model_status(msg)

    @Slot(bool)
    def _on_age_mode_toggled(self, checked: bool):
        """Toggle between standard date redaction and age-based conversion.

        Tries automatic birth date detection first (regex scan, subcategory,
        context patterns, earliest-date heuristic).  If that fails, shows a
        dialog letting the user pick the birth date.
        """
        if not self._entities:
            return

        if checked:
            # Save current placeholders before converting
            self._original_placeholders = {
                e.original: e.placeholder for e in self._entities
                if e.category == "date"
            }

            # First: try fully automatic detection (no dialog)
            _, self._birth_date_text = self.anonymizer._apply_age_conversion(
                self._entities, self._extracted_text
            )

            # Check if any dates got converted
            any_converted = any(
                e.category == "date" and not e.placeholder.startswith("[")
                for e in self._entities
            )

            if not any_converted:
                # Auto-detection failed — restore and try user dialog
                for e in self._entities:
                    if e.original in self._original_placeholders:
                        e.placeholder = self._original_placeholders[e.original]

                birth_text = self._show_birth_date_dialog()
                if not birth_text:
                    # User cancelled or no dates — uncheck
                    self._original_placeholders.clear()
                    self.age_mode_cb.blockSignals(True)
                    self.age_mode_cb.setChecked(False)
                    self.age_mode_cb.blockSignals(False)
                    return

                # Re-apply with user-selected birth date
                _, self._birth_date_text = self.anonymizer._apply_age_conversion(
                    self._entities, self._extracted_text,
                    birth_date_text=birth_text,
                )

        else:
            # Toggle off: display only — keep age placeholders, render will show blocks
            pass

        self._update_birth_date_display()

        # Rebuild spans and refresh all views
        self._spans = find_entity_spans(self._extracted_text, self._entities)
        self._populate_entity_table()
        self._refresh_views()

    def _update_birth_date_display(self):
        """Show or hide birth date widget based on whether we have an accepted birth date."""
        if self._birth_date_text:
            self._birth_date_label.setText(t("birth_date_label", self._lang))
            self._birth_date_value.setText(self._birth_date_text)
            self._change_birth_btn.setText(t("change_birth_date", self._lang))
            self._change_birth_btn.setToolTip(t("tip_change_birth_date", self._lang))
            self._birth_date_widget.setVisible(True)
        else:
            self._birth_date_widget.setVisible(False)

    def _on_change_birth_date(self):
        """Let user pick a different birth date and re-apply age conversion."""
        birth_text = self._show_birth_date_dialog()
        if not birth_text:
            return
        self._original_placeholders = {
            e.original: e.placeholder for e in self._entities if e.category == "date"
        }
        _, self._birth_date_text = self.anonymizer._apply_age_conversion(
            self._entities, self._extracted_text, birth_date_text=birth_text
        )
        self._update_birth_date_display()
        self._spans = find_entity_spans(self._extracted_text, self._entities)
        self._populate_entity_table()
        self._refresh_views()

    def _show_birth_date_dialog(self) -> str | None:
        """Show a dialog for the user to pick the birth date from detected dates.

        Returns the selected date's original text, or None if cancelled.
        """
        from redakt.core.anonymizer import Anonymizer as _Anon

        seen_texts: set[str] = set()
        date_options: list[str] = []
        for e in self._entities:
            if e.category != "date" or e.original in seen_texts:
                continue
            if _Anon._parse_date(e.original):
                seen_texts.add(e.original)
                date_options.append(e.original)

        if not date_options:
            QMessageBox.warning(
                self,
                t("select_birth_date", self._lang),
                t("no_dates_found", self._lang),
            )
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle(t("select_birth_date", self._lang))
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet(
            f"QDialog {{ background: {_c()["BG_DARK"]}; }}"
            f"QLabel {{ color: {_c()["TEXT"]}; font-size: 12px; }}"
            f"QComboBox {{ background: {_c()["BG_LIGHT"]}; color: {_c()["TEXT"]}; "
            f"  border: 1px solid {_c()["BORDER"]}; border-radius: 2px; "
            f"  padding: 5px 8px; font-size: 12px; min-height: 22px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {_c()["BG_MID"]}; "
            f"  color: {_c()["TEXT"]}; selection-background-color: {_c()["ACCENT"]}; "
            f"  border: 1px solid {_c()["BORDER"]}; }}"
            f"QPushButton {{ background: {_c()["BG_LIGHT"]}; color: {_c()["TEXT_DIM"]}; "
            f"  border: 1px solid {_c()["BORDER"]}; border-radius: 2px; "
            f"  padding: 6px 18px; font-size: 11px; letter-spacing: 0.5px; }}"
            f"QPushButton:hover {{ color: {_c()["TEXT"]}; border-color: {_c()["TEXT_DIM"]}; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        prompt_lbl = QLabel(t("birth_date_prompt", self._lang))
        prompt_lbl.setWordWrap(True)
        layout.addWidget(prompt_lbl)

        combo = QComboBox()
        for date_text in date_options:
            combo.addItem(date_text, userData=date_text)
        layout.addWidget(combo)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        return combo.currentData()

    # ==================================================================
    #  CHAT WITH DOCUMENT (Q&A)
    # ==================================================================

    @Slot()
    def _send_chat_message(self):
        """Send a question about the document to the LLM."""
        question = self.chat_input.text().strip()
        if not question or not self._extracted_text:
            return

        self.status_bar.set_active_inference(True)
        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_bar.set_model_status(t("chat_thinking", self._lang))

        self.anonymizer.language = self.lang_combo.currentData()

        # Show user question in chat
        self._append_chat_html(
            f'<div style="margin: 6px 0; padding: 6px 12px; '
            f"background-color: {_c()["BG_MID"]}; border-left: 3px solid {_c()["TEXT_DIM"]}; "
            f'border-radius: 2px;">'
            f'<span style="color: {_c()["TEXT_DIM"]}; font-size: 10px; letter-spacing: 1px; '
            f'font-weight: bold;">{t("chat_you", self._lang)}</span><br>'
            f'<span style="color: {_c()["TEXT"]};">{_html.escape(question)}</span></div>'
        )

        worker = AsyncWorker(
            self.anonymizer.chat_with_document,
            self._extracted_text,
            question,
            self._chat_history.copy() if self._chat_history else None,
        )
        worker.finished.connect(
            lambda answer: self._on_chat_answer(question, answer)
        )
        worker.error.connect(self._on_chat_error)
        self._workers.append(worker)
        worker.start()

    @Slot(object)
    def _on_chat_answer(self, question: str, answer: str):
        self.status_bar.set_active_inference(False)
        self.chat_input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.status_bar.set_model_status("Qwen3.5 // llama.cpp")

        # Store in conversation history for multi-turn
        self._chat_history.append({"role": "user", "content": question})
        self._chat_history.append({"role": "assistant", "content": answer})
        # Keep history manageable (last 10 exchanges)
        if len(self._chat_history) > 20:
            self._chat_history = self._chat_history[-20:]

        # Show AI answer
        rendered = render_markdown(answer)
        self._append_chat_html(
            f'<div style="margin: 6px 0; padding: 8px 12px; '
            f"background-color: {_c()["BG_MID"]}; border-left: 3px solid {_c()["TEXT_DIM"]}; "
            f'border-radius: 2px;">'
            f'<span style="color: {_c()["TEXT_DIM"]}; font-size: 10px; letter-spacing: 1px; '
            f'font-weight: bold;">{t("chat_ai", self._lang)}</span><br>'
            f"{rendered}</div>"
        )

    @Slot(str)
    def _on_chat_error(self, error: str):
        self.status_bar.set_active_inference(False)
        self.chat_input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.status_bar.set_model_status("Qwen3.5 // llama.cpp")

        self._append_chat_html(
            f'<div style="margin: 6px 0; padding: 6px 12px; '
            f"border-left: 3px solid {_c()["ERROR"]}; border-radius: 2px;\">"
            f'<span style="color: {_c()["ERROR"]}; font-size: 10px;">ERROR: '
            f"{_html.escape(str(error))}</span></div>"
        )

    def _append_chat_html(self, html_fragment: str):
        """Append HTML to the chat view and scroll to bottom."""
        current = self.chat_view.toHtml()
        # If it's the initial placeholder, replace entirely
        if ("LOAD A FILE" in current or "FILE LOADED" in current
                or "DOSYA YÜKLENDİ" in current or "DOSYA YÜKLEYİN" in current
                or "DOSYA:" in current or "FILE:" in current):
            self.chat_view.setHtml(
                f'<div style="font-family: {_MONO}; font-size: 12px;">'
                f"{html_fragment}</div>"
            )
        else:
            # Append by inserting at the end
            cursor = self.chat_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.chat_view.setTextCursor(cursor)
            self.chat_view.insertHtml(html_fragment)

        # Scroll to bottom
        scrollbar = self.chat_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot()
    def _clear_chat(self):
        """Clear chat history and view."""
        self._chat_history = []
        lang = self._lang
        if self._extracted_text:
            fname = self._current_file.name if self._current_file else "document"
            chat_msg = t("file_cleared_chat", lang, name=_html.escape(fname))
            chat_lines = chat_msg.split("\n", 1)
            self.chat_view.setHtml(
                f'<p style="color: {_c()["TEXT_DIM"]}; font-size: 11px; '
                f"font-family: {_MONO}; letter-spacing: 0.5px;\">"
                f"{chat_lines[0]}<br>"
                f'<span style="color: {_c()["TEXT_DIM"]};">'
                f"{chat_lines[1] if len(chat_lines) > 1 else ''}</span></p>"
            )
        else:
            self.chat_view.setHtml(
                f'<p style="color: {_c()["TEXT_VDIM"]}; font-size: 11px; '
                f"font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('load_file_chat', lang)}</p>"
            )

    # ==================================================================
    #  REDACTION TOGGLES — per item and per category
    # ==================================================================

    def _get_active_spans(self) -> list[TextSpan]:
        """Return only the spans whose entities are enabled for redaction."""
        active_originals: set[str] = set()
        for i, entity in enumerate(self._entities):
            if i < len(self._entity_enabled) and self._entity_enabled[i]:
                active_originals.add(entity.original)
        return [s for s in self._spans if s.entity.original in active_originals]

    def _refresh_views(self):
        """Re-render both text panels based on current enabled state."""
        active_spans = self._get_active_spans()
        n_active = len({s.entity.original for s in active_spans})
        n_total = len(self._entities)

        # Save scroll positions before setHtml() resets them
        orig_scroll = self.original_view.verticalScrollBar().value()
        redacted_scroll = self.redacted_view.verticalScrollBar().value()

        self.original_view.setHtml(
            render_highlighted_html(self._extracted_text, active_spans)
        )
        self.redacted_view.setHtml(
            render_redacted_html(
                self._extracted_text, active_spans,
                age_mode=self.age_mode_cb.isChecked(),
            )
        )

        # Restore scroll positions
        self.original_view.verticalScrollBar().setValue(orig_scroll)
        self.redacted_view.verticalScrollBar().setValue(redacted_scroll)
        lang = self._lang
        self.left_label.setText(
            t("doc_text_count", lang, active=n_active, total=n_total)
        )
        self.right_label.setText(
            t("redacted_count", lang, active=n_active, total=n_total)
        )
        self.table_label.setText(
            t("pii_count", lang, active=n_active, total=n_total)
        )

        # Update chip counts
        self._update_chip_labels()

    # ── Per-item toggle (checkbox in table column 0) ──

    def _on_item_toggled(self, row: int, checked: bool):
        """Called when a single entity checkbox is toggled."""
        if self._updating_table:
            return
        if 0 <= row < len(self._entity_enabled):
            self._entity_enabled[row] = checked
            self._sync_chip_from_items(self._entities[row].category)
            self._refresh_views()

    # ── Per-category toggle (chip buttons) ──

    def _build_category_chips(self):
        """Create a colored toggle chip for each detected category."""
        self._clear_category_chips()

        # Find unique categories in detection order
        seen: list[str] = []
        for entity in self._entities:
            if entity.category not in seen:
                seen.append(entity.category)

        for cat in seen:
            color = CATEGORY_COLORS.get(cat, _c()["ACCENT"])
            label = CATEGORY_LABELS_TR.get(cat, cat)
            count = sum(1 for e in self._entities if e.category == cat)

            btn = QPushButton(f"{label} ({count})")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}55; color: #ffffff; "
                f"border: 1px solid {color}88; "
                f"border-radius: 2px; padding: 0 10px; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 0.5px; }}"
                f"QPushButton:hover {{ background: {color}77; }}"
                f"QPushButton:!checked {{ background: {_c()["BG_LIGHT"]}; "
                f"color: {_c()["TEXT_VDIM"]}; border-color: {_c()["BORDER"]}; }}"
            )
            btn.clicked.connect(
                lambda checked, c=cat: self._on_category_toggled(c, checked)
            )
            self.chip_container.addWidget(btn)
            self._category_chips[cat] = btn

    def _clear_category_chips(self):
        """Remove all category chip buttons."""
        for btn in self._category_chips.values():
            self.chip_container.removeWidget(btn)
            btn.deleteLater()
        self._category_chips.clear()
        self.select_all_btn.setVisible(False)
        self.select_none_btn.setVisible(False)

    def _on_category_toggled(self, category: str, checked: bool):
        """Toggle all entities of a given category on/off."""
        self._updating_table = True
        for i, entity in enumerate(self._entities):
            if entity.category == category:
                self._entity_enabled[i] = checked
                # Update checkbox in table
                cb_widget = self.entity_table.cellWidget(i, 0)
                if cb_widget:
                    cb = cb_widget.findChild(QCheckBox)
                    if cb:
                        cb.setChecked(checked)
        self._updating_table = False
        self._refresh_views()

    def _sync_chip_from_items(self, category: str):
        """Update a category chip's checked state based on individual items."""
        btn = self._category_chips.get(category)
        if not btn:
            return
        # Chip is checked if ALL items of that category are enabled
        all_on = all(
            self._entity_enabled[i]
            for i, e in enumerate(self._entities)
            if e.category == category
        )
        any_on = any(
            self._entity_enabled[i]
            for i, e in enumerate(self._entities)
            if e.category == category
        )
        btn.blockSignals(True)
        btn.setChecked(all_on)
        btn.blockSignals(False)

        # Visual hint for partial selection
        color = CATEGORY_COLORS.get(category, _c()["ACCENT"])
        if all_on:
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}55; color: #ffffff; "
                f"border: 1px solid {color}88; "
                f"border-radius: 2px; padding: 0 10px; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 0.5px; }}"
                f"QPushButton:hover {{ background: {color}77; }}"
                f"QPushButton:!checked {{ background: {_c()["BG_LIGHT"]}; "
                f"color: {_c()["TEXT_VDIM"]}; border-color: {_c()["BORDER"]}; }}"
            )
        elif any_on:
            # Partial: dimmed version of category color
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}33; color: #ffffffaa; "
                f"border: 1px solid {color}55; "
                f"border-radius: 2px; padding: 0 10px; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 0.5px; }}"
                f"QPushButton:hover {{ background: {color}55; }}"
                f"QPushButton:!checked {{ background: {_c()["BG_LIGHT"]}; "
                f"color: {_c()["TEXT_VDIM"]}; border-color: {_c()["BORDER"]}; }}"
            )

    def _update_chip_labels(self):
        """Update chip text to reflect active count."""
        for cat, btn in self._category_chips.items():
            label = CATEGORY_LABELS_TR.get(cat, cat)
            total = sum(1 for e in self._entities if e.category == cat)
            active = sum(
                1 for i, e in enumerate(self._entities)
                if e.category == cat and self._entity_enabled[i]
            )
            btn.setText(f"{label} ({active}/{total})")

    # ── Select All / None ──

    @Slot()
    def _select_all(self):
        self._updating_table = True
        self._entity_enabled = [True] * len(self._entities)
        for i in range(self.entity_table.rowCount()):
            cb_widget = self.entity_table.cellWidget(i, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(True)
        for btn in self._category_chips.values():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        self._updating_table = False
        self._refresh_views()

    @Slot()
    def _select_none(self):
        self._updating_table = True
        self._entity_enabled = [False] * len(self._entities)
        for i in range(self.entity_table.rowCount()):
            cb_widget = self.entity_table.cellWidget(i, 0)
            if cb_widget:
                cb = cb_widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(False)
        for btn in self._category_chips.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self._updating_table = False
        self._refresh_views()

    # ── Entity table ─────────────────────────────────────────────────

    def _populate_entity_table(self):
        self._updating_table = True
        self.entity_table.setRowCount(len(self._entities))
        for row, entity in enumerate(self._entities):
            color = CATEGORY_COLORS.get(entity.category, _c()["ACCENT"])
            cat_label = CATEGORY_LABELS_TR.get(
                entity.category, entity.category
            )

            # Column 0: checkbox
            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(
                lambda state, r=row: self._on_item_toggled(
                    r, state == Qt.CheckState.Checked.value
                )
            )
            # Center the checkbox in the cell
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.entity_table.setCellWidget(row, 0, cb_container)

            # Column 1: row number
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setForeground(QColor(_c()["TEXT_DIM"]))
            self.entity_table.setItem(row, 1, num_item)

            # Column 2: original text
            orig_item = QTableWidgetItem(entity.original)
            orig_item.setForeground(QColor(_c()["TEXT"]))
            self.entity_table.setItem(row, 2, orig_item)

            # Column 3: category (colored in neon)
            cat_item = QTableWidgetItem(cat_label)
            cat_item.setForeground(QColor(color))
            self.entity_table.setItem(row, 3, cat_item)

            # Column 4: placeholder
            ph_item = QTableWidgetItem(entity.placeholder)
            ph_item.setForeground(QColor(_c()["TEXT_DIM"]))
            self.entity_table.setItem(row, 4, ph_item)

            # Column 5: confidence
            conf = f"{entity.confidence:.0%}" if entity.confidence else "\u2014"
            conf_item = QTableWidgetItem(conf)
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_item.setForeground(
                QColor(
                    _c()["TEXT"]
                    if entity.confidence and entity.confidence >= 0.8
                    else _c()["TEXT_DIM"]
                )
            )
            self.entity_table.setItem(row, 5, conf_item)

        self._updating_table = False

    @Slot(int, int)
    def _on_entity_clicked(self, row: int, col: int):
        if col != 0 and 0 <= row < len(self._entities):
            self.original_view.scrollToAnchor(f"e{row}")

    # ── Export ───────────────────────────────────────────────────────

    @Slot()
    def _export_file(self):
        if not self._current_file or not self._spans:
            return

        active_spans = self._get_active_spans()
        if not active_spans:
            QMessageBox.warning(
                self,
                t("nothing_to_redact", self._lang),
                t("nothing_to_redact_msg", self._lang),
            )
            return

        fmt = self.format_combo.currentText()
        try:
            output_path = export_redacted(
                fmt,
                self._extracted_text,
                active_spans,
                self._current_file,
                age_mode=self.age_mode_cb.isChecked(),
            )
            QMessageBox.information(
                self,
                t("export_complete", self._lang),
                t("export_complete_msg", self._lang, path=output_path),
            )
        except Exception as e:
            self._show_error(t("export_failed", self._lang, error=e))

    # ── Settings ─────────────────────────────────────────────────────

    def _open_settings(self):
        dialog = SettingsDialog(self.llamacpp_manager, self)
        if self.llamacpp_manager.gguf_path:
            dialog.set_gguf(str(self.llamacpp_manager.gguf_path))

        if dialog.exec():
            selected_gguf = dialog.get_selected_gguf()
            if selected_gguf:
                old_path = self.llamacpp_manager.gguf_path
                self.llamacpp_manager.set_gguf(selected_gguf)
                save_settings(gguf_path=str(selected_gguf.path))
                if old_path != selected_gguf.path:
                    self._ensure_llamacpp_ready()
                else:
                    self.status_bar.set_model_status("Qwen3.5 // llama.cpp")

    def _ensure_llamacpp_ready(self):
        self.status_bar.set_model_status(t("starting_server", self._lang))
        worker = AsyncWorker(self.llamacpp_manager.ensure_ready)
        worker.finished.connect(self._on_llamacpp_ready)
        worker.error.connect(self._on_scan_error)
        self._workers.append(worker)
        worker.start()

    @Slot(object)
    def _on_llamacpp_ready(self, success: bool):
        if success:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
            self.status_bar.set_ready_status(True)
        else:
            self.status_bar.set_model_status(t("server_failed", self._lang))
            self.status_bar.set_ready_status(False)

    # ── Utilities ────────────────────────────────────────────────────

    @Slot(str)
    def _show_error(self, msg: str):
        QMessageBox.critical(self, t("error_title", self._lang), msg)
