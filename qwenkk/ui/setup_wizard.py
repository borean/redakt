import webbrowser

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from qwenkk.constants import Backend
from qwenkk.core.llamacpp_manager import LlamaCppManager
from qwenkk.core.model_manager import ModelManager
from qwenkk.core.sysinfo import (
    format_system_summary,
    get_model_recommendations,
    get_system_info,
)
from qwenkk.core.worker import AsyncWorker

# ── Factory AI neutral dark theme colors ──────────────────────────────────────
_BG_DARKEST = "#111111"
_BG_DARK = "#1a1a1a"
_BG_MID = "#252525"
_BG_LIGHT = "#303030"
_BG_LIGHTER = "#3d3d3d"
_BORDER = "#333333"
_TEXT = "#d4d4d4"
_TEXT_DIM = "#808080"
_ACCENT = "#e78a4e"
_ACCENT_DIM = "#c47a42"
_ERROR = "#d46b6b"
_WARNING = "#d4a04e"
_SUCCESS = "#6bbd6b"
_BLUE = "#7aabdb"

_OLLAMA_DOWNLOAD_URLS = {
    "darwin": "https://ollama.com/download/mac",
    "win32": "https://ollama.com/download/windows",
    "linux": "https://ollama.com/download/linux",
}


class SetupWizard(QDialog):
    """First-run setup: auto-detects available backends and gets ready."""

    setup_complete = Signal()
    backend_selected = Signal(str)   # Backend.value string

    def __init__(
        self,
        model_manager: ModelManager,
        llamacpp_manager: LlamaCppManager,
        parent=None,
    ):
        super().__init__(parent)
        self.model_manager = model_manager
        self.llamacpp_manager = llamacpp_manager
        self._worker: AsyncWorker | None = None
        self._chosen_backend: Backend | None = None

        self.setWindowTitle("DeIdentify Setup")
        self.setMinimumSize(580, 480)
        self.setModal(True)

        self._setup_ui()
        self._connect_signals()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title
        title = QLabel("DEIDENTIFY")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {_TEXT}; "
            f"letter-spacing: 6px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("LOCAL MEDICAL DOCUMENT ANONYMIZATION")
        subtitle.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; letter-spacing: 2px;"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Accent line
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: qlineargradient(x1:0, x2:1, "
            f"stop:0 transparent, stop:0.3 {_ACCENT}, "
            f"stop:0.7 {_ACCENT}, stop:1 transparent);"
        )
        layout.addWidget(line)
        layout.addSpacing(4)

        # ── System specs ──────────────────────────────────────────────
        self._sys_info = get_system_info()
        sys_summary = format_system_summary(self._sys_info)

        sys_label = QLabel(f"YOUR SYSTEM: {sys_summary}")
        sys_label.setStyleSheet(
            f"font-size: 10px; color: {_TEXT}; letter-spacing: 0.5px; "
            f"font-weight: bold;"
        )
        sys_label.setWordWrap(True)
        layout.addWidget(sys_label)

        # Privacy notice
        privacy_label = QLabel(
            "All AI processing runs 100% locally on this machine. "
            "No data leaves your computer."
        )
        privacy_label.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; letter-spacing: 0.5px; "
            f"font-style: italic;"
        )
        privacy_label.setWordWrap(True)
        layout.addWidget(privacy_label)

        layout.addSpacing(6)

        # ── Backend choice (auto-detected) ────────────────────────────
        self.choice_frame = QVBoxLayout()

        choice_label = QLabel("SELECT AI ENGINE")
        choice_label.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; font-weight: bold; "
            f"letter-spacing: 2px;"
        )
        self.choice_frame.addWidget(choice_label)

        self.radio_ollama = QRadioButton("OLLAMA  -  Qwen3 30B-A3B  (~18GB)")
        self.radio_llamacpp = QRadioButton("LLAMA.CPP  -  Qwen3.5 35B-A3B  (~20GB, faster)")
        self.radio_ollama.setChecked(True)

        self.backend_group = QButtonGroup(self)
        self.backend_group.addButton(self.radio_ollama, 0)
        self.backend_group.addButton(self.radio_llamacpp, 1)

        self.choice_frame.addWidget(self.radio_ollama)
        self.choice_frame.addWidget(self.radio_llamacpp)

        # Availability hints
        self.ollama_hint = QLabel("")
        self.ollama_hint.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; margin-left: 24px; "
            f"letter-spacing: 0.5px;"
        )
        self.choice_frame.addWidget(self.ollama_hint)

        self.llamacpp_hint = QLabel("")
        self.llamacpp_hint.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; margin-left: 24px; "
            f"letter-spacing: 0.5px;"
        )
        self.choice_frame.addWidget(self.llamacpp_hint)

        # Model compatibility info
        recs = get_model_recommendations(self._sys_info)
        q4_rec = next((r for r in recs if "Q4" in r["name"]), None)
        if q4_rec and q4_rec["compatible"]:
            compat_label = QLabel(
                f"[OK] Your system can run the recommended Q4 model. "
                f"{q4_rec['note']}"
            )
            compat_label.setStyleSheet(
                f"font-size: 10px; color: {_TEXT}; margin-top: 4px;"
            )
        elif q4_rec:
            compat_label = QLabel(
                f"[WARN] The Q4 model may be tight on your system. "
                f"{q4_rec['note']}"
            )
            compat_label.setStyleSheet(
                f"font-size: 10px; color: {_WARNING}; margin-top: 4px;"
            )
        else:
            compat_label = QLabel("")
        compat_label.setWordWrap(True)
        self.choice_frame.addWidget(compat_label)

        layout.addLayout(self.choice_frame)

        layout.addSpacing(4)

        # Continue button
        self.continue_btn = QPushButton("INITIALIZE")
        self.continue_btn.setObjectName("primary")
        self.continue_btn.setMinimumHeight(36)
        self.continue_btn.setMinimumWidth(200)
        self.continue_btn.clicked.connect(self._on_continue)
        layout.addWidget(self.continue_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(4)

        # ── Status area (shown during setup) ──────────────────────────
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {_TEXT}; letter-spacing: 0.5px;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet(
            f"font-size: 10px; color: {_TEXT_DIM}; letter-spacing: 0.5px;"
        )
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setVisible(False)
        layout.addWidget(self.detail_label)

        layout.addStretch()

        btn_row = QHBoxLayout()

        self.install_btn = QPushButton("DOWNLOAD OLLAMA")
        self.install_btn.setObjectName("primary")
        self.install_btn.setMinimumHeight(36)
        self.install_btn.setVisible(False)
        self.install_btn.clicked.connect(self._open_ollama_download)
        btn_row.addWidget(self.install_btn)

        self.retry_btn = QPushButton("RETRY")
        self.retry_btn.setMinimumHeight(36)
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self._start_setup)
        btn_row.addWidget(self.retry_btn)

        layout.addLayout(btn_row)

    def _connect_signals(self):
        self.model_manager.status_message.connect(self._on_status)
        self.model_manager.model_pull_progress.connect(self._on_pull_progress)
        self.model_manager.model_ready.connect(self._on_ready)
        self.model_manager.error_occurred.connect(self._on_error)
        self.model_manager.ollama_install_needed.connect(self._on_install_needed)

        self.llamacpp_manager.status_message.connect(self._on_status)
        self.llamacpp_manager.error_occurred.connect(self._on_error)
        self.llamacpp_manager.server_ready.connect(self._on_ready)

    def showEvent(self, event):
        super().showEvent(event)
        self._detect_backends()

    def _detect_backends(self):
        ollama_installed = self.model_manager.is_ollama_installed()
        if ollama_installed:
            self.ollama_hint.setText("[OK] Ollama installed")
            self.ollama_hint.setStyleSheet(
                f"font-size: 10px; color: {_TEXT}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )
        else:
            self.ollama_hint.setText("[ERR] Ollama not found")
            self.ollama_hint.setStyleSheet(
                f"font-size: 10px; color: {_ERROR}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )

        has_binary = self.llamacpp_manager.is_installed()
        has_model = self.llamacpp_manager.has_model()

        if has_binary and has_model:
            self.llamacpp_hint.setText("[OK] llama-server + model found")
            self.llamacpp_hint.setStyleSheet(
                f"font-size: 10px; color: {_TEXT}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )
        elif has_binary:
            self.llamacpp_hint.setText("[WARN] llama-server found, model missing")
            self.llamacpp_hint.setStyleSheet(
                f"font-size: 10px; color: {_WARNING}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )
        else:
            self.llamacpp_hint.setText("[ERR] llama-server not found (brew install llama.cpp)")
            self.llamacpp_hint.setStyleSheet(
                f"font-size: 10px; color: {_ERROR}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )
            self.radio_llamacpp.setEnabled(False)

        if has_binary and has_model:
            self.radio_llamacpp.setChecked(True)
        elif ollama_installed:
            self.radio_ollama.setChecked(True)

    def _on_continue(self):
        if self.radio_llamacpp.isChecked():
            self._chosen_backend = Backend.LLAMACPP
        else:
            self._chosen_backend = Backend.OLLAMA

        self.backend_selected.emit(self._chosen_backend.value)

        self.continue_btn.setVisible(False)
        self.radio_ollama.setVisible(False)
        self.radio_llamacpp.setVisible(False)
        self.ollama_hint.setVisible(False)
        self.llamacpp_hint.setVisible(False)
        for i in range(self.choice_frame.count()):
            w = self.choice_frame.itemAt(i).widget()
            if w:
                w.setVisible(False)

        self.status_label.setVisible(True)
        self.detail_label.setVisible(True)
        self._start_setup()

    def _start_setup(self):
        self.install_btn.setVisible(False)
        self.retry_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.detail_label.setText("")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {_TEXT}; letter-spacing: 0.5px;"
        )

        if self._chosen_backend == Backend.LLAMACPP:
            self.status_label.setText("INITIALIZING LLAMA-SERVER...")
            self._worker = AsyncWorker(self.llamacpp_manager.ensure_ready)
        else:
            self.status_label.setText("PREPARING OLLAMA...")
            self._worker = AsyncWorker(self.model_manager.ensure_ready)

        self._worker.error.connect(self._on_error)
        self._worker.start()

    @Slot(str)
    def _on_status(self, message: str):
        self.status_label.setText(message.upper())
        if "download" in message.lower() or "loading" in message.lower():
            self.progress_bar.setVisible(True)
            if self._chosen_backend == Backend.LLAMACPP and "loading" in message.lower():
                self.progress_bar.setRange(0, 0)
            else:
                self.progress_bar.setRange(0, 100)

    @Slot(float, str)
    def _on_pull_progress(self, percent: float, detail: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(percent))
        self.detail_label.setText(detail)

    @Slot()
    def _on_ready(self):
        engine = "LLAMA.CPP" if self._chosen_backend == Backend.LLAMACPP else "OLLAMA"
        self.status_label.setText(f"[OK] {engine} READY")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {_TEXT}; letter-spacing: 1px;"
        )
        self.progress_bar.setVisible(False)
        self.detail_label.setText("")
        self.setup_complete.emit()
        self.accept()

    @Slot(str)
    def _on_error(self, message: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {_ERROR}; letter-spacing: 0.5px;"
        )
        self.progress_bar.setVisible(False)
        self.retry_btn.setVisible(True)

    @Slot()
    def _on_install_needed(self):
        self.status_label.setText(
            "Ollama is required but not installed.\n\n"
            "Click below to download it (free, ~100 MB).\n"
            "After installing, click Retry."
        )
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {_WARNING}; letter-spacing: 0.5px;"
        )
        self.install_btn.setVisible(True)
        self.retry_btn.setVisible(True)

    def _open_ollama_download(self):
        import sys

        url = _OLLAMA_DOWNLOAD_URLS.get(sys.platform, "https://ollama.com/download")
        webbrowser.open(url)
