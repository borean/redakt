"""Main application window — visual document redaction workflow.

Features:
- Split view: highlighted document text | redacted preview
- Entity table with per-item checkboxes (toggle individual redactions)
- Category chips to toggle entire PII categories at once
- Export as PDF / DOCX / TXT / Markdown
- Document summarization
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

from qwenkk.constants import Backend, SUPPORTED_EXTENSIONS, Language
from qwenkk.core.anonymizer import Anonymizer
from qwenkk.core.entities import PIIEntity, PIIResponse
from qwenkk.core.llamacpp_manager import LlamaCppManager
from qwenkk.core.model_manager import ModelManager
from qwenkk.core.redactor import (
    CATEGORY_COLORS,
    CATEGORY_LABELS_TR,
    TextSpan,
    find_entity_spans,
    render_highlighted_html,
    render_redacted_html,
)
from qwenkk.core.worker import AsyncWorker
from qwenkk.core.md_renderer import render_markdown
from qwenkk.exporters import (
    EXPORT_FORMATS,
    SUMMARY_EXPORT_FORMATS,
    export_redacted,
    export_summary,
)
from qwenkk.parsers import get_parser
from qwenkk.ui.i18n import t
from qwenkk.ui.settings_dialog import SettingsDialog
from qwenkk.ui.setup_wizard import SetupWizard
from qwenkk.ui.status_bar import OllamaStatusBar

# ── Factory AI neutral dark theme ─────────────────────────────────────────
_BG_DARKEST = "#111111"
_BG_DARK = "#1a1a1a"
_BG_MID = "#252525"
_BG_LIGHT = "#303030"
_BG_LIGHTER = "#3d3d3d"
_BORDER = "#333333"
_TEXT = "#d4d4d4"
_TEXT_DIM = "#808080"
_TEXT_VDIM = "#555555"
_ACCENT = "#e78a4e"
_ACCENT_DIM = "#c47a42"
_ERROR = "#d46b6b"
_WARNING = "#d4a04e"
_SUCCESS = "#6bbd6b"
_BLUE = "#7aabdb"

_MONO = (
    "'SF Mono', 'Fira Code', 'JetBrains Mono', "
    "Menlo, Consolas, monospace"
)


class MainWindow(QMainWindow):
    _sig_scan_status = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeIdentify // QwenKK")
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
        self._last_summary: str = ""  # store last summary for export
        self._original_placeholders: dict[str, str] = {}
        self._is_image: bool = False

        # ── Managers ──
        self.model_manager = ModelManager()
        self.llamacpp_manager = LlamaCppManager()
        self.anonymizer = Anonymizer()
        self._workers: list[AsyncWorker] = []

        # Category chip buttons (built after scan)
        self._category_chips: dict[str, QPushButton] = {}

        self._setup_ui()
        self._connect_signals()
        self._set_ui_state("empty")

    # ── UI Construction ──────────────────────────────────────────────

    @staticmethod
    def _tech_label(text: str, color: str = _TEXT_DIM) -> QLabel:
        """Create a tech-style section label."""
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {color}; "
            f"letter-spacing: 2px; padding: 2px 0;"
        )
        return lbl

    @staticmethod
    def _section_hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-size: 9px; color: #555555; "
            "padding: 0 0 2px 0; font-style: italic;"
        )
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
        title = QLabel("DEIDENTIFY")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {_ACCENT}; "
            f"letter-spacing: 6px;"
        )
        top.addWidget(title)

        subtitle = QLabel("QWENKK")
        subtitle.setStyleSheet(
            f"font-size: 11px; color: {_TEXT_DIM}; letter-spacing: 3px; "
            f"padding-top: 8px;"
        )
        top.addWidget(subtitle)

        top.addStretch()
        self.settings_btn = QPushButton("CONFIG")
        self.settings_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 4px 14px; font-size: 10px; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}"
        )
        self.settings_btn.setToolTip("Configure model, backend, and language settings")
        self.settings_btn.clicked.connect(self._open_settings)
        top.addWidget(self.settings_btn)
        root.addLayout(top)

        # Thin accent line under title
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: qlineargradient(x1:0, x2:1, "
            f"stop:0 {_TEXT_DIM}, stop:0.5 {_TEXT_DIM}44, stop:1 transparent);"
        )
        root.addWidget(line)

        # ── File bar ──
        file_bar = QHBoxLayout()
        self.file_label = QLabel("NO FILE LOADED")
        self.file_label.setStyleSheet(
            f"font-size: 11px; color: {_TEXT_DIM}; padding: 4px 0; "
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
        self._workflow_hint.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_VDIM}; letter-spacing: 1px; "
            f"padding: 2px 0; font-family: {_MONO};"
        )
        self._workflow_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self.original_view.setStyleSheet(
            f"QTextBrowser {{ background-color: {_BG_MID}; color: {_TEXT}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; padding: 12px; "
            f"font-size: 12px; font-family: {_MONO}; }}"
        )
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
        self.redacted_view.setStyleSheet(
            f"QTextBrowser {{ background-color: {_BG_DARKEST}; color: {_TEXT}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; padding: 12px; "
            f"font-size: 12px; font-family: {_MONO}; }}"
        )
        right_layout.addWidget(self.redacted_view)
        text_splitter.addWidget(right)

        text_splitter.setSizes([500, 500])
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
        self.select_all_btn.setFixedHeight(22)
        self.select_all_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_LIGHT}; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"font-size: 9px; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}"
        )
        self.select_all_btn.setToolTip("Enable all detected entities for redaction")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_all_btn.setVisible(False)
        header_row.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("SELECT NONE")
        self.select_none_btn.setFixedHeight(22)
        self.select_none_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_LIGHT}; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"font-size: 9px; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ color: {_ERROR}; border-color: {_ERROR}; }}"
        )
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
            ["", "#", "ORIGINAL", "TYPE", "REPLACEMENT", "CONF"]
        )
        hdr = self.entity_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(0, 36)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(1, 32)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(5, 50)
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

        self.summarize_btn = QPushButton("SUMMARY")
        self.summarize_btn.setFixedHeight(22)
        self.summarize_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_LIGHT}; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 0 12px; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 0.5px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}"
            f"QPushButton:disabled {{ background: {_BG_LIGHT}; color: {_TEXT_VDIM}; "
            f"border-color: {_BORDER}; }}"
        )
        self.summarize_btn.setToolTip("Generate a concise clinical summary")
        self.summarize_btn.clicked.connect(self._summarize_document)
        self.summarize_btn.setEnabled(False)
        chat_header.addWidget(self.summarize_btn)

        self.detailed_btn = QPushButton("DETAILED")
        self.detailed_btn.setFixedHeight(22)
        self.detailed_btn.setToolTip(
            "Generate a comprehensive summary with lab values, growth data, and clinical progression"
        )
        self.detailed_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 4px 8px; font-size: 10px; font-weight: bold; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}"
            f"QPushButton:disabled {{ color: {_TEXT_VDIM}; border-color: {_BG_LIGHT}; }}"
        )
        self.detailed_btn.setEnabled(False)
        self.detailed_btn.clicked.connect(self._detailed_summarize)
        chat_header.addWidget(self.detailed_btn)

        self.clear_chat_btn = QPushButton("CLEAR CHAT")
        self.clear_chat_btn.setFixedHeight(22)
        self.clear_chat_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_LIGHT}; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 0 12px; font-size: 10px; letter-spacing: 0.5px; }}"
            f"QPushButton:hover {{ color: {_ERROR}; border-color: {_ERROR}; }}"
        )
        self.clear_chat_btn.setToolTip("Clear conversation history")
        self.clear_chat_btn.clicked.connect(self._clear_chat)
        chat_header.addWidget(self.clear_chat_btn)

        # Summary export controls
        self.summary_format_combo = QComboBox()
        for fmt in SUMMARY_EXPORT_FORMATS:
            self.summary_format_combo.addItem(fmt)
        self.summary_format_combo.setFixedWidth(75)
        self.summary_format_combo.setFixedHeight(22)
        self.summary_format_combo.setVisible(False)
        chat_header.addWidget(self.summary_format_combo)

        self.export_summary_btn = QPushButton("EXPORT SUMMARY")
        self.export_summary_btn.setFixedHeight(22)
        self.export_summary_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_LIGHT}; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 0 12px; font-size: 10px; letter-spacing: 0.5px; }}"
            f"QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}"
        )
        self.export_summary_btn.setToolTip("Export the summary as a file")
        self.export_summary_btn.clicked.connect(self._export_summary)
        self.export_summary_btn.setVisible(False)
        chat_header.addWidget(self.export_summary_btn)

        chat_layout.addLayout(chat_header)
        self._ai_hint = self._section_hint(
            "AI-powered document analysis. Generate summaries or ask questions."
        )
        chat_layout.addWidget(self._ai_hint)

        # Chat message display
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.setStyleSheet(
            f"QTextBrowser {{ background-color: {_BG_DARKEST}; color: {_TEXT}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; padding: 10px; "
            f"font-size: 12px; font-family: {_MONO}; }}"
        )
        self.chat_view.setHtml("")  # placeholder set by _relabel_ui / _set_ui_state
        chat_layout.addWidget(self.chat_view)

        # Chat input row
        chat_input_row = QHBoxLayout()
        chat_input_row.setSpacing(6)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask a question about the document...")
        self.chat_input.setStyleSheet(
            f"QLineEdit {{ background-color: {_BG_LIGHT}; color: {_TEXT}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 6px 10px; font-size: 12px; font-family: {_MONO}; }}"
            f"QLineEdit:focus {{ border-color: {_BLUE}; }}"
        )
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.chat_input.setEnabled(False)
        chat_input_row.addWidget(self.chat_input)

        self.send_btn = QPushButton("SEND")
        self.send_btn.setFixedSize(70, 30)
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background: {_BG_LIGHTER}; color: {_TEXT}; "
            f"border: none; border-radius: 2px; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 1px; }}"
            f"QPushButton:hover {{ background: {_TEXT_DIM}; }}"
            f"QPushButton:disabled {{ background: {_BG_LIGHT}; color: {_TEXT_VDIM}; }}"
        )
        self.send_btn.setToolTip("Send your question to the AI")
        self.send_btn.clicked.connect(self._send_chat_message)
        self.send_btn.setEnabled(False)
        chat_input_row.addWidget(self.send_btn)

        chat_layout.addLayout(chat_input_row)
        self.main_splitter.addWidget(self.chat_panel)

        self.main_splitter.setSizes([400, 180, 200])
        root.addWidget(self.main_splitter, stretch=1)

        # ── Progress bar (hidden by default) ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        root.addWidget(self.progress_bar)

        # ── Controls bar ──
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self._lang_label = QLabel("LANG:")
        self._lang_label.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; letter-spacing: 1px;"
        )
        controls.addWidget(self._lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("TR", Language.TR)
        self.lang_combo.addItem("EN", Language.EN)
        self.lang_combo.setFixedWidth(60)
        self.lang_combo.currentIndexChanged.connect(self._relabel_ui)
        controls.addWidget(self.lang_combo)

        controls.addSpacing(8)

        self.age_mode_cb = QCheckBox("AGE-BASED DATES")
        self.age_mode_cb.setStyleSheet(
            f"QCheckBox {{ color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 0.5px; }}"
            f"QCheckBox::indicator {{ width: 14px; height: 14px; }}"
            f"QCheckBox::indicator:checked {{ background: {_ACCENT}; border: 2px solid {_ACCENT}; border-radius: 2px; }}"
            f"QCheckBox::indicator:unchecked {{ background: {_BG_MID}; border: 2px solid {_BG_LIGHTER}; border-radius: 2px; }}"
        )
        self.age_mode_cb.setToolTip(
            "When a birth date is found, replace other dates with patient age "
            "(e.g., 'at age 3.5 yrs'). Useful for pediatric documents."
        )
        self.age_mode_cb.setChecked(False)
        self.age_mode_cb.toggled.connect(self._on_age_mode_toggled)
        controls.addWidget(self.age_mode_cb)

        controls.addSpacing(8)

        self.scan_btn = QPushButton("SCAN FOR PII")
        self.scan_btn.setToolTip("Run AI analysis to detect all personal data in the document")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setMinimumWidth(160)
        self.scan_btn.setMinimumHeight(32)
        self.scan_btn.clicked.connect(self._start_scan)
        controls.addWidget(self.scan_btn)

        controls.addSpacing(12)

        # ── Model/backend indicator (clickable to open settings) ──
        self.model_label = QPushButton("Qwen3 // ollama")
        self.model_label.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_TEXT_DIM}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; "
            f"padding: 4px 12px; font-size: 10px; letter-spacing: 0.5px; "
            f"font-family: {_MONO}; }}"
            f"QPushButton:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}"
        )
        self.model_label.setToolTip("Click to open model and backend settings")
        self.model_label.clicked.connect(self._open_settings)
        controls.addWidget(self.model_label)

        controls.addStretch()

        self._export_label = QLabel("EXPORT:")
        self._export_label.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; letter-spacing: 1px;"
        )
        controls.addWidget(self._export_label)
        self.format_combo = QComboBox()
        for fmt in EXPORT_FORMATS:
            self.format_combo.addItem(fmt)
        self.format_combo.setFixedWidth(90)
        controls.addWidget(self.format_combo)

        self.export_btn = QPushButton("EXPORT REDACTED")
        self.export_btn.setToolTip("Export the redacted document with PII removed")
        self.export_btn.setMinimumHeight(32)
        self.export_btn.clicked.connect(self._export_file)
        controls.addWidget(self.export_btn)
        root.addLayout(controls)

        # ── Status bar ──
        self.status_bar = OllamaStatusBar()
        root.addWidget(self.status_bar)

        # Apply initial localization
        self._relabel_ui()

    # ── Localization ──────────────────────────────────────────────────

    @property
    def _lang(self):
        """Current UI language from the language combo."""
        data = self.lang_combo.currentData()
        return data if data else Language.EN

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

        # Select All / None buttons
        self.select_all_btn.setText(t("select_all", lang))
        self.select_all_btn.setToolTip(t("tip_select_all", lang))
        self.select_none_btn.setText(t("select_none", lang))
        self.select_none_btn.setToolTip(t("tip_select_none", lang))

        # Chat panel header
        self.chat_label.setText(t("document_ai", lang))
        self.summarize_btn.setText(t("summary", lang))
        self.summarize_btn.setToolTip(t("tip_summary", lang))
        self.detailed_btn.setText(t("detailed", lang))
        self.detailed_btn.setToolTip(t("tip_detailed", lang))
        self.clear_chat_btn.setText(t("clear_chat", lang))
        self.clear_chat_btn.setToolTip(t("tip_clear_chat", lang))
        self.chat_input.setPlaceholderText(t("ask_placeholder", lang))
        self.send_btn.setText(t("send", lang))
        self.send_btn.setToolTip(t("tip_send", lang))
        self.export_summary_btn.setText(t("export_summary", lang))
        self.export_summary_btn.setToolTip(t("tip_export_summary", lang))

        # Controls bar
        self._lang_label.setText(t("lang", lang))
        self.scan_btn.setText(t("scan_for_pii", lang))
        self.scan_btn.setToolTip(t("tip_scan", lang))
        self.age_mode_cb.setText(t("age_based_dates", lang))
        self.age_mode_cb.setToolTip(t("tip_age_mode", lang))
        self._export_label.setText(t("export", lang))
        self.export_btn.setText(t("export_redacted", lang))
        self.export_btn.setToolTip(t("tip_export", lang))
        self.model_label.setToolTip(t("tip_model_label", lang))

    def _connect_signals(self):
        self.model_manager.ollama_status_changed.connect(
            self.status_bar.set_ollama_status
        )
        self.model_manager.model_status_changed.connect(
            self.status_bar.set_model_status
        )
        self.model_manager.error_occurred.connect(self._show_error)
        self.model_manager.model_ready.connect(self._on_model_ready)

        self.llamacpp_manager.server_ready.connect(self._on_model_ready)
        self.llamacpp_manager.error_occurred.connect(self._show_error)

        self._sig_scan_status.connect(self._slot_scan_status)

    # ── UI state management ──────────────────────────────────────────

    def _set_ui_state(self, state: str):
        if state == "empty":
            self.scan_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.summarize_btn.setEnabled(False)
            self.detailed_btn.setEnabled(False)
            self.chat_input.setEnabled(False)
            self.send_btn.setEnabled(False)
            lang = self._lang
            self.original_view.setHtml(
                f'<p style="color: {_TEXT_VDIM}; font-size: 13px; text-align: center; '
                f"padding-top: 60px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('drop_here', lang)}</p>"
            )
            self.redacted_view.setHtml(
                f'<p style="color: {_TEXT_VDIM}; font-size: 13px; text-align: center; '
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
            self.summarize_btn.setEnabled(self._model_ready)
            self.detailed_btn.setEnabled(self._model_ready)
            self.chat_input.setEnabled(self._model_ready)
            self.send_btn.setEnabled(self._model_ready)
            self.redacted_view.setHtml(
                f'<p style="color: {_TEXT_VDIM}; font-size: 13px; text-align: center; '
                f"padding-top: 60px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('click_scan', lang)}</p>"
            )
            self.entity_table.setRowCount(0)
            self.table_label.setText(t("detected_pii", lang))
            self._clear_category_chips()
        elif state == "scanning":
            self.scan_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.summarize_btn.setEnabled(False)
            self.detailed_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
        elif state == "scanned":
            self.scan_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
            self.summarize_btn.setEnabled(True)
            self.detailed_btn.setEnabled(True)
            self.chat_input.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.select_all_btn.setVisible(True)
            self.select_none_btn.setVisible(True)
        elif state == "error":
            self.scan_btn.setEnabled(True)
            self.export_btn.setEnabled(False)
            self.summarize_btn.setEnabled(bool(self._extracted_text))
            self.detailed_btn.setEnabled(bool(self._extracted_text))
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
        wizard = SetupWizard(
            self.model_manager, self.llamacpp_manager, parent=self
        )
        wizard.setup_complete.connect(self._on_model_ready)
        wizard.backend_selected.connect(self._on_backend_selected)
        wizard.exec()

    @Slot(str)
    def _on_backend_selected(self, backend_value: str):
        backend = Backend(backend_value)
        self.anonymizer.backend = backend
        if backend == Backend.LLAMACPP:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
            self.model_label.setText("Qwen3.5 // llama.cpp")
        else:
            self.status_bar.set_model_status("READY")
            self.model_label.setText("Qwen3 // ollama")

    @Slot()
    def _on_model_ready(self):
        self._model_ready = True
        self.status_bar.set_ollama_status(True)
        if self.anonymizer.backend == Backend.LLAMACPP:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
            self.model_label.setText("Qwen3.5 // llama.cpp")
        else:
            self.status_bar.set_model_status("READY")
            self.model_label.setText("Qwen3 // ollama")
        if self._current_file:
            self.scan_btn.setEnabled(True)
            self.summarize_btn.setEnabled(True)
            self.detailed_btn.setEnabled(True)
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
                    f"Unsupported file type: {path.suffix}\n\n"
                    f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                )

    @Slot()
    def _open_file_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Medical Document",
            str(Path.home() / "Desktop"),
            f"Supported Files ({exts});;All Files (*)",
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path):
        try:
            parser = get_parser(path)
            result = parser.extract_text(path)
        except Exception as e:
            self._show_error(f"Failed to read file:\n{e}")
            return

        self._current_file = path
        self._extracted_text = result.text
        self._is_image = result.metadata.get("requires_vision", False)
        self._entities = []
        self._spans = []
        self._entity_enabled = []
        self._chat_history = []

        lang = self._lang
        if self._is_image:
            char_count = 0
            self.file_label.setText(f"{path.name}  |  IMAGE")
            self.file_label.setStyleSheet(
                f"font-size: 11px; color: {_TEXT}; padding: 4px 0; "
                f"letter-spacing: 0.5px;"
            )
            self.left_label.setText(t("document_text", lang))
            img_msg = t("image_file_loaded", lang, name=_html.escape(path.name))
            parts = img_msg.split("\n\n", 1)
            self.original_view.setHtml(
                f'<p style="color: {_TEXT_DIM}; font-size: 13px; text-align: center; '
                f"padding-top: 40px; font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{_html.escape(parts[0])}<br><br>"
                f'<span style="color: {_TEXT_VDIM};">'
                f"{_html.escape(parts[1]) if len(parts) > 1 else ''}</span></p>"
            )
        else:
            char_count = len(result.text)
            self.file_label.setText(
                f"{path.name}  |  {char_count:,} chars"
            )
            self.file_label.setStyleSheet(
                f"font-size: 11px; color: {_TEXT}; padding: 4px 0; "
                f"letter-spacing: 0.5px;"
            )
            self.left_label.setText(
                f"{t('document_text', lang)}  ({char_count:,} chars)"
            )
            self.original_view.setPlainText(result.text)

        self._set_ui_state("file_loaded")

        # Update chat panel
        chat_msg = t("file_loaded_chat", lang, name=_html.escape(path.name))
        chat_lines = chat_msg.split("\n", 1)
        self.chat_view.setHtml(
            f'<p style="color: {_TEXT_DIM}; font-size: 11px; '
            f"font-family: {_MONO}; letter-spacing: 0.5px;\">"
            f"{chat_lines[0]}<br>"
            f'<span style="color: {_TEXT_DIM};">'
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
            lines = [f"PII detected in image ({len(self._entities)} entities):", ""]
            for e in self._entities:
                lines.append(f"  [{e.category.upper()}] {e.original}")
            self._extracted_text = "\n".join(lines)
            self.original_view.setPlainText(self._extracted_text)
            self.left_label.setText(f"DETECTED TEXT  ({len(self._entities)} entities)")

        self._spans = find_entity_spans(self._extracted_text, self._entities)
        self._entity_enabled = [True] * len(self._entities)

        # Build category chips + table + views
        self._build_category_chips()
        self._populate_entity_table()
        self._refresh_views()
        self._set_ui_state("scanned")

    @Slot(str)
    def _on_scan_error(self, error: str):
        self.status_bar.set_active_inference(False)
        self._set_ui_state("error")
        self._show_error(f"Scan failed:\n{error}")

    @Slot(str)
    def _slot_scan_status(self, msg: str):
        self.status_bar.set_model_status(msg)

    @Slot(bool)
    def _on_age_mode_toggled(self, checked: bool):
        """Toggle between standard date redaction and age-based conversion."""
        if not self._entities:
            return

        if checked:
            # Save current placeholders before converting
            self._original_placeholders = {
                e.original: e.placeholder for e in self._entities
                if e.category == "date"
            }
            self._entities = self.anonymizer._apply_age_conversion(self._entities)
        else:
            # Restore original placeholders
            for e in self._entities:
                if e.original in self._original_placeholders:
                    e.placeholder = self._original_placeholders[e.original]
            self._original_placeholders.clear()

        # Rebuild spans and refresh all views
        self._spans = find_entity_spans(self._extracted_text, self._entities)
        self._populate_entity_table()
        self._refresh_views()

    # ==================================================================
    #  SUMMARIZE DOCUMENT
    # ==================================================================

    @Slot()
    def _summarize_document(self):
        """Generate a summary of the loaded document."""
        if not self._extracted_text:
            return
        self.status_bar.set_active_inference(True)
        self.summarize_btn.setEnabled(False)
        self.detailed_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_bar.set_model_status(t("generating_summary", self._lang))

        self.anonymizer.language = self.lang_combo.currentData()

        # Show "thinking" in chat view
        self._append_chat_html(
            f'<span style="color: {_TEXT_DIM}; letter-spacing: 1px;">'
            f"{t('generating_summary', self._lang)}</span>"
        )

        worker = AsyncWorker(
            self.anonymizer.summarize_document, self._extracted_text
        )
        worker.finished.connect(self._on_summary_complete)
        worker.error.connect(self._on_chat_error)
        self._workers.append(worker)
        worker.start()

    @Slot()
    def _detailed_summarize(self):
        """Generate a detailed clinical summary of the loaded document."""
        if not self._extracted_text:
            return
        self.status_bar.set_active_inference(True)
        self.summarize_btn.setEnabled(False)
        self.detailed_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_bar.set_model_status(t("generating_detailed", self._lang))

        self.anonymizer.language = self.lang_combo.currentData()

        # Show "thinking" in chat view
        self._append_chat_html(
            f'<span style="color: {_TEXT_DIM}; letter-spacing: 1px;">'
            f"{t('generating_detailed', self._lang)}</span>"
        )

        worker = AsyncWorker(
            self.anonymizer.summarize_document_detailed, self._extracted_text
        )
        worker.finished.connect(self._on_summary_complete)
        worker.error.connect(self._on_chat_error)
        self._workers.append(worker)
        worker.start()

    @Slot(object)
    def _on_summary_complete(self, summary: str):
        self.status_bar.set_active_inference(False)
        self.summarize_btn.setEnabled(True)
        self.detailed_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.progress_bar.setVisible(False)

        if self.anonymizer.backend == Backend.LLAMACPP:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
        else:
            self.status_bar.set_model_status("READY")

        # Store for export
        self._last_summary = summary
        self.export_summary_btn.setVisible(True)
        self.summary_format_combo.setVisible(True)

        # Render markdown summary
        rendered = render_markdown(summary)
        self._append_chat_html(
            f'<div style="margin: 6px 0; padding: 8px 12px; '
            f"background-color: {_BG_MID}; border-left: 3px solid {_TEXT_DIM}; "
            f'border-radius: 2px;">'
            f'<span style="color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px; '
            f'font-weight: bold;">SUMMARY</span><br>'
            f"{rendered}</div>"
        )

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
        self.summarize_btn.setEnabled(False)
        self.detailed_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_bar.set_model_status("THINKING...")

        self.anonymizer.language = self.lang_combo.currentData()

        # Show user question in chat
        self._append_chat_html(
            f'<div style="margin: 6px 0; padding: 6px 12px; '
            f"background-color: {_BG_MID}; border-left: 3px solid {_TEXT_DIM}; "
            f'border-radius: 2px;">'
            f'<span style="color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px; '
            f'font-weight: bold;">YOU</span><br>'
            f'<span style="color: {_TEXT};">{_html.escape(question)}</span></div>'
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
        self.summarize_btn.setEnabled(True)
        self.detailed_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if self.anonymizer.backend == Backend.LLAMACPP:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
        else:
            self.status_bar.set_model_status("READY")

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
            f"background-color: {_BG_MID}; border-left: 3px solid {_TEXT_DIM}; "
            f'border-radius: 2px;">'
            f'<span style="color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px; '
            f'font-weight: bold;">AI</span><br>'
            f"{rendered}</div>"
        )

    @Slot(str)
    def _on_chat_error(self, error: str):
        self.status_bar.set_active_inference(False)
        self.chat_input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.summarize_btn.setEnabled(True)
        self.detailed_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if self.anonymizer.backend == Backend.LLAMACPP:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
        else:
            self.status_bar.set_model_status("READY")

        self._append_chat_html(
            f'<div style="margin: 6px 0; padding: 6px 12px; '
            f"border-left: 3px solid {_ERROR}; border-radius: 2px;\">"
            f'<span style="color: {_ERROR}; font-size: 10px;">ERROR: '
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
                f'<p style="color: {_TEXT_DIM}; font-size: 11px; '
                f"font-family: {_MONO}; letter-spacing: 0.5px;\">"
                f"{chat_lines[0]}<br>"
                f'<span style="color: {_TEXT_DIM};">'
                f"{chat_lines[1] if len(chat_lines) > 1 else ''}</span></p>"
            )
        else:
            self.chat_view.setHtml(
                f'<p style="color: {_TEXT_VDIM}; font-size: 11px; '
                f"font-family: {_MONO}; letter-spacing: 1px;\">"
                f"{t('load_file_chat', lang)}</p>"
            )

    @Slot()
    def _export_summary(self):
        """Export the last summary in the selected format."""
        if not self._last_summary or not self._current_file:
            return
        fmt = self.summary_format_combo.currentText()
        try:
            output_path = export_summary(fmt, self._last_summary, self._current_file)
            QMessageBox.information(
                self, "Export Complete",
                f"Summary saved:\n{output_path}",
            )
        except Exception as e:
            self._show_error(f"Summary export failed:\n{e}")

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
            render_redacted_html(self._extracted_text, active_spans)
        )

        # Restore scroll positions
        self.original_view.verticalScrollBar().setValue(orig_scroll)
        self.redacted_view.verticalScrollBar().setValue(redacted_scroll)
        self.left_label.setText(
            f"DOCUMENT TEXT  ({n_active}/{n_total} PII HIGHLIGHTED)"
        )
        self.right_label.setText(
            f"REDACTED PREVIEW  ({n_active}/{n_total} REDACTED)"
        )
        self.table_label.setText(
            f"DETECTED PII  ({n_active}/{n_total} ACTIVE)"
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
            color = CATEGORY_COLORS.get(cat, _ACCENT)
            label = CATEGORY_LABELS_TR.get(cat, cat)
            count = sum(1 for e in self._entities if e.category == cat)

            btn = QPushButton(f"{label} ({count})")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}33; color: {color}; "
                f"border: 1px solid {color}66; "
                f"border-radius: 2px; padding: 0 10px; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 0.5px; }}"
                f"QPushButton:hover {{ background: {color}55; }}"
                f"QPushButton:!checked {{ background: {_BG_LIGHT}; "
                f"color: {_TEXT_VDIM}; border-color: {_BORDER}; }}"
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
        color = CATEGORY_COLORS.get(category, _ACCENT)
        if all_on:
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}33; color: {color}; "
                f"border: 1px solid {color}66; "
                f"border-radius: 2px; padding: 0 10px; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 0.5px; }}"
                f"QPushButton:hover {{ background: {color}55; }}"
                f"QPushButton:!checked {{ background: {_BG_LIGHT}; "
                f"color: {_TEXT_VDIM}; border-color: {_BORDER}; }}"
            )
        elif any_on:
            # Partial: dimmed version of category color
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}18; color: {color}88; "
                f"border: 1px solid {color}44; "
                f"border-radius: 2px; padding: 0 10px; font-size: 10px; "
                f"font-weight: bold; letter-spacing: 0.5px; }}"
                f"QPushButton:hover {{ background: {color}33; }}"
                f"QPushButton:!checked {{ background: {_BG_LIGHT}; "
                f"color: {_TEXT_VDIM}; border-color: {_BORDER}; }}"
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
            color = CATEGORY_COLORS.get(entity.category, _ACCENT)
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
            num_item.setForeground(QColor(_TEXT_DIM))
            self.entity_table.setItem(row, 1, num_item)

            # Column 2: original text
            orig_item = QTableWidgetItem(entity.original)
            orig_item.setForeground(QColor(_TEXT))
            self.entity_table.setItem(row, 2, orig_item)

            # Column 3: category (colored in neon)
            cat_item = QTableWidgetItem(cat_label)
            cat_item.setForeground(QColor(color))
            self.entity_table.setItem(row, 3, cat_item)

            # Column 4: placeholder
            ph_item = QTableWidgetItem(entity.placeholder)
            ph_item.setForeground(QColor(_TEXT_DIM))
            self.entity_table.setItem(row, 4, ph_item)

            # Column 5: confidence
            conf = f"{entity.confidence:.0%}" if entity.confidence else "\u2014"
            conf_item = QTableWidgetItem(conf)
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_item.setForeground(
                QColor(
                    _TEXT
                    if entity.confidence and entity.confidence >= 0.8
                    else _TEXT_DIM
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
                "Nothing to redact",
                "No PII items are selected for redaction.\n"
                "Check at least one item and try again.",
            )
            return

        fmt = self.format_combo.currentText()
        try:
            output_path = export_redacted(
                fmt,
                self._extracted_text,
                active_spans,
                self._current_file,
            )
            QMessageBox.information(
                self,
                "Export Complete",
                f"Redacted file saved:\n{output_path}",
            )
        except Exception as e:
            self._show_error(f"Export failed:\n{e}")

    # ── Settings ─────────────────────────────────────────────────────

    def _open_settings(self):
        dialog = SettingsDialog(self.llamacpp_manager, self)
        # Pre-select the currently active backend so the user doesn't have to
        dialog.set_backend(self.anonymizer.backend)
        if dialog.exec():
            backend = dialog.get_selected_backend()
            old_backend = self.anonymizer.backend
            self.anonymizer.backend = backend

            if backend == Backend.LLAMACPP:
                # Check if user selected a different GGUF
                selected_gguf = dialog.get_selected_gguf()
                if selected_gguf:
                    self.llamacpp_manager.set_gguf(selected_gguf)
                self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
                self.model_label.setText("Qwen3.5 // llama.cpp")
                if old_backend != Backend.LLAMACPP:
                    self._ensure_llamacpp_ready()
            else:
                model = dialog.get_selected_model()
                if model:
                    self.model_manager.current_model = model
                    self.anonymizer.model = model
                self.status_bar.set_model_status("READY")
                self.model_label.setText("Qwen3 // ollama")

    def _ensure_llamacpp_ready(self):
        self.status_bar.set_model_status("STARTING LLAMA-SERVER...")
        worker = AsyncWorker(self.llamacpp_manager.ensure_ready)
        worker.finished.connect(self._on_llamacpp_ready)
        worker.error.connect(self._on_scan_error)
        self._workers.append(worker)
        worker.start()

    @Slot(object)
    def _on_llamacpp_ready(self, success: bool):
        if success:
            self.status_bar.set_model_status("Qwen3.5 // llama.cpp")
            self.model_label.setText("Qwen3.5 // llama.cpp")
            self.status_bar.set_ollama_status(True)
        else:
            self.status_bar.set_model_status("LLAMA-SERVER FAILED")
            self.status_bar.set_ollama_status(False)

    # ── Utilities ────────────────────────────────────────────────────

    @Slot(str)
    def _show_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
