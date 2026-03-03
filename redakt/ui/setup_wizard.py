from PySide6.QtCore import Qt, QTimer, Signal, Slot
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

from redakt.core.llamacpp_manager import LlamaCppManager
from redakt.core.sysinfo import (
    format_system_summary,
    get_model_recommendations,
    get_system_info,
)
from redakt.core.worker import AsyncWorker
from redakt.ui import theme as theme_module


def _c():
    tm = getattr(theme_module, "theme_manager", None)
    return tm.get_colors() if tm else theme_module._DARK


class SetupWizard(QDialog):
    """First-run setup: downloads model if needed, starts llama-server."""

    setup_complete = Signal()

    def __init__(self, llamacpp_manager: LlamaCppManager, parent=None):
        super().__init__(parent)
        self.llamacpp_manager = llamacpp_manager
        self._worker: AsyncWorker | None = None
        self._download_cancel = None

        self.setWindowTitle("Redakt Setup")
        self.setMinimumSize(580, 520)
        self.setModal(True)

        self._setup_ui()
        self._connect_signals()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        c = _c()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title
        title = QLabel("REDAKT")
        title.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {c['TEXT']}; "
            f"letter-spacing: 6px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("LOCAL MEDICAL DOCUMENT DE-IDENTIFICATION")
        subtitle.setStyleSheet(
            f"font-size: 10px; color: {c['TEXT_DIM']}; letter-spacing: 2px;"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Accent line
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: qlineargradient(x1:0, x2:1, "
            f"stop:0 transparent, stop:0.3 {c['ACCENT']}, "
            f"stop:0.7 {c['ACCENT']}, stop:1 transparent);"
        )
        layout.addWidget(line)
        layout.addSpacing(4)

        # ── System specs ──────────────────────────────────────────────
        self._sys_info = get_system_info()
        sys_summary = format_system_summary(self._sys_info)

        sys_label = QLabel(f"YOUR SYSTEM: {sys_summary}")
        sys_label.setStyleSheet(
            f"font-size: 10px; color: {c['TEXT']}; letter-spacing: 0.5px; "
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
            f"font-size: 10px; color: {c['TEXT_DIM']}; letter-spacing: 0.5px; "
            f"font-style: italic;"
        )
        privacy_label.setWordWrap(True)
        layout.addWidget(privacy_label)

        layout.addSpacing(6)

        # ── Model selection (download-first flow) ─────────────────────
        self.choice_frame = QVBoxLayout()

        choice_label = QLabel("SELECT AI MODEL")
        choice_label.setStyleSheet(
            f"font-size: 10px; color: {c['TEXT_DIM']}; font-weight: bold; "
            f"letter-spacing: 2px;"
        )
        self.choice_frame.addWidget(choice_label)

        self.radio_q4 = QRadioButton("Q4_K_M  —  ~20 GB  (recommended, fast)")
        self.radio_q8 = QRadioButton("Q8_0  —  ~33 GB  (high quality, slower)")
        self.radio_q4.setChecked(True)

        self.model_group = QButtonGroup(self)
        self.model_group.addButton(self.radio_q4, 0)
        self.model_group.addButton(self.radio_q8, 1)

        self.choice_frame.addWidget(self.radio_q4)
        self.choice_frame.addWidget(self.radio_q8)

        # Model readiness hints
        self.model_hint = QLabel("")
        self.model_hint.setStyleSheet(
            f"font-size: 10px; color: {c['TEXT_DIM']}; margin-left: 24px; "
            f"letter-spacing: 0.5px;"
        )
        self.choice_frame.addWidget(self.model_hint)

        # Memory compatibility info
        recs = get_model_recommendations(self._sys_info)
        q4_rec = next((r for r in recs if "Q4" in r["name"]), None)
        if q4_rec and q4_rec["compatible"]:
            compat_label = QLabel(
                f"[OK] Your system can run the recommended Q4 model. "
                f"{q4_rec['note']}"
            )
            compat_label.setStyleSheet(
                f"font-size: 10px; color: {c['TEXT']}; margin-top: 4px;"
            )
        elif q4_rec:
            compat_label = QLabel(
                f"[WARN] The Q4 model may be tight on your system. "
                f"{q4_rec['note']}"
            )
            compat_label.setStyleSheet(
                f"font-size: 10px; color: {c['WARNING']}; margin-top: 4px;"
            )
        else:
            compat_label = QLabel("")
        compat_label.setWordWrap(True)
        self.choice_frame.addWidget(compat_label)

        layout.addLayout(self.choice_frame)
        layout.addSpacing(4)

        # Continue button
        self.continue_btn = QPushButton("DOWNLOAD & INITIALIZE")
        self.continue_btn.setObjectName("primary")
        self.continue_btn.setMinimumHeight(36)
        self.continue_btn.setMinimumWidth(200)
        self.continue_btn.clicked.connect(self._on_continue)
        layout.addWidget(self.continue_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(4)

        # ── Status area (shown during setup) ──────────────────────────
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {c['TEXT']}; letter-spacing: 0.5px;"
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
            f"font-size: 10px; color: {c['TEXT_DIM']}; letter-spacing: 0.5px;"
        )
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setVisible(False)
        layout.addWidget(self.detail_label)

        layout.addStretch()

        btn_row = QHBoxLayout()

        self.retry_btn = QPushButton("RETRY")
        self.retry_btn.setMinimumHeight(36)
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self._start_setup)
        btn_row.addWidget(self.retry_btn)

        layout.addLayout(btn_row)

    def _connect_signals(self):
        self.llamacpp_manager.status_message.connect(self._on_status)
        self.llamacpp_manager.error_occurred.connect(self._on_error)
        self.llamacpp_manager.server_ready.connect(self._on_ready)

    def showEvent(self, event):
        super().showEvent(event)
        self._detect_state()
        # Auto-proceed when model is already downloaded — no click needed
        if self.llamacpp_manager.is_installed() and self.llamacpp_manager.has_model():
            QTimer.singleShot(100, self._on_continue)

    def _detect_state(self):
        """Auto-detect what's available and adjust UI accordingly."""
        c = _c()
        has_binary = self.llamacpp_manager.is_installed()
        has_model = self.llamacpp_manager.has_model()

        if has_binary and has_model:
            self.model_hint.setText("[OK] Model already downloaded — ready to go")
            self.model_hint.setStyleSheet(
                f"font-size: 10px; color: {c['SUCCESS']}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )
            self.continue_btn.setText("INITIALIZE")
        elif has_binary:
            self.model_hint.setText("Model will be downloaded (~20 GB, one-time)")
            self.model_hint.setStyleSheet(
                f"font-size: 10px; color: {c['TEXT']}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )
        else:
            self.model_hint.setText(
                "[WARN] llama-server not found. Install: brew install llama.cpp"
            )
            self.model_hint.setStyleSheet(
                f"font-size: 10px; color: {c['WARNING']}; margin-left: 24px; "
                f"letter-spacing: 0.5px;"
            )

    def _on_continue(self):
        # Hide selection UI
        self.continue_btn.setVisible(False)
        for i in range(self.choice_frame.count()):
            w = self.choice_frame.itemAt(i).widget()
            if w:
                w.setVisible(False)

        self.status_label.setVisible(True)
        self.detail_label.setVisible(True)

        if not self.llamacpp_manager.has_model():
            self._start_model_download()
        else:
            self._start_setup()

    def _start_model_download(self):
        """Download the GGUF model before starting the server."""
        import asyncio

        from redakt.core.download_manager import (
            AVAILABLE_MODELS,
            download_model,
            get_data_dir,
        )

        # Pick model based on selection
        if self.radio_q8.isChecked():
            model_info = AVAILABLE_MODELS[1]  # Q8_0
        else:
            model_info = AVAILABLE_MODELS[0]  # Q4_K_M

        self.status_label.setText(
            f"DOWNLOADING {model_info.quant} MODEL ({model_info.size_gb} GB)..."
        )
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self._download_cancel = asyncio.Event()

        def on_progress(pct, dl_mb, total_mb, status):
            self.progress_bar.setValue(int(pct))
            self.detail_label.setVisible(True)
            self.detail_label.setText(
                f"{dl_mb:.0f} / {total_mb:.0f} MB  —  {status}"
            )

        async def do_download():
            path = await download_model(
                model_info,
                dest_dir=get_data_dir(),
                on_progress=on_progress,
                cancel_event=self._download_cancel,
            )
            # Update the manager with the new model path
            self.llamacpp_manager.gguf_path = path
            return path

        self._worker = AsyncWorker(do_download)
        self._worker.finished.connect(self._on_download_complete)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @Slot(object)
    def _on_download_complete(self, result):
        self.progress_bar.setValue(100)
        self.detail_label.setText("Download complete!")
        self._start_setup()

    def _start_setup(self):
        c = _c()
        self.retry_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.detail_label.setText("")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {c['TEXT']}; letter-spacing: 0.5px;"
        )

        self.status_label.setText("INITIALIZING LLAMA-SERVER...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self._worker = AsyncWorker(self.llamacpp_manager.ensure_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @Slot(str)
    def _on_status(self, message: str):
        self.status_label.setText(message.upper())
        if "download" in message.lower() or "loading" in message.lower():
            self.progress_bar.setVisible(True)
            if "loading" in message.lower():
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
        c = _c()
        self.status_label.setText("[OK] READY")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {c['TEXT']}; letter-spacing: 1px;"
        )
        self.progress_bar.setVisible(False)
        self.detail_label.setText("")
        self.setup_complete.emit()
        self.accept()

    @Slot(str)
    def _on_error(self, message: str):
        c = _c()
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {c['ERROR']}; letter-spacing: 0.5px;"
        )
        self.progress_bar.setVisible(False)
        self.retry_btn.setVisible(True)
