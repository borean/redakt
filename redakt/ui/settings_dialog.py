import httpx
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from redakt.constants import (
    Backend,
    DEFAULT_MODEL,
    DEV_MODEL_FP16,
    LLAMACPP_HOST,
    LLAMACPP_MODEL,
    OLLAMA_HOST,
    Q8_MODEL,
)
from redakt.core.llamacpp_manager import GGUFInfo, LlamaCppManager
from redakt.core.sysinfo import (
    format_system_summary,
    get_model_recommendations,
    get_system_info,
)

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

# Complete radio button style that preserves checked indicator styling
_RADIO_STYLE = (
    f"QRadioButton {{ color: {_TEXT}; font-weight: bold; spacing: 8px; }}"
    f"QRadioButton::indicator {{ width: 14px; height: 14px; "
    f"  border: 2px solid {_BG_LIGHTER}; border-radius: 9px; background: {_BG_MID}; }}"
    f"QRadioButton::indicator:checked {{ background: {_ACCENT}; border-color: {_ACCENT}; }}"
    f"QRadioButton::indicator:hover {{ border-color: #555555; }}"
)
_RADIO_STYLE_DISABLED = (
    f"QRadioButton {{ color: {_TEXT_DIM}; spacing: 8px; }}"
    f"QRadioButton::indicator {{ width: 14px; height: 14px; "
    f"  border: 2px solid {_BG_LIGHTER}; border-radius: 9px; background: {_BG_MID}; }}"
    f"QRadioButton::indicator:checked {{ background: {_ACCENT}; border-color: {_ACCENT}; }}"
)

# ── Settings keys ─────────────────────────────────────────────────────────────
_KEY_BACKEND = "config/backend"
_KEY_MODEL = "config/model"
_KEY_GGUF_PATH = "config/gguf_path"


def load_settings() -> dict:
    """Load persisted settings. Returns dict with backend, model, gguf_path."""
    s = QSettings()
    return {
        "backend": s.value(_KEY_BACKEND, Backend.LLAMACPP.value),
        "model": s.value(_KEY_MODEL, DEFAULT_MODEL),
        "gguf_path": s.value(_KEY_GGUF_PATH, ""),
    }


def save_settings(backend: str, model: str, gguf_path: str = ""):
    """Persist settings to disk via QSettings."""
    s = QSettings()
    s.setValue(_KEY_BACKEND, backend)
    s.setValue(_KEY_MODEL, model)
    s.setValue(_KEY_GGUF_PATH, gguf_path)
    s.sync()


class SettingsDialog(QDialog):
    def __init__(self, llamacpp_manager: LlamaCppManager, parent=None):
        super().__init__(parent)
        self.llamacpp_manager = llamacpp_manager
        self.setWindowTitle("Redakt Config")
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── System info ──────────────────────────────────────────────
        sys_group = QGroupBox("YOUR SYSTEM")
        sys_form = QFormLayout(sys_group)
        sys_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        sys_helper = QLabel(
            "Hardware detected on this machine.\n"
            "Model compatibility depends on available memory."
        )
        sys_helper.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px; font-style: italic;")
        sys_helper.setWordWrap(True)
        sys_form.addRow(sys_helper)

        self._sys_info = get_system_info()
        sys_summary = format_system_summary(self._sys_info)
        sys_label = QLabel(sys_summary)
        sys_label.setStyleSheet(f"color: {_TEXT}; font-weight: bold;")
        sys_label.setWordWrap(True)
        sys_form.addRow(sys_label)

        # Show details
        ram = self._sys_info.get("unified_memory_gb") or self._sys_info.get("ram_gb", 0)
        mem_type = "Unified Memory" if self._sys_info.get("apple_silicon") else "RAM"
        detail_parts = [f"{mem_type}: {ram}GB"]
        if self._sys_info.get("os"):
            detail_parts.append(
                f"OS: {self._sys_info['os']} {self._sys_info.get('os_version', '')}"
            )
        detail_label = QLabel(" | ".join(detail_parts))
        detail_label.setStyleSheet(f"color: {_TEXT_DIM};")
        detail_label.setWordWrap(True)
        sys_form.addRow(detail_label)

        # Data privacy notice
        privacy_label = QLabel(
            "All processing runs locally on this machine. "
            "No data is sent to any cloud service."
        )
        privacy_label.setStyleSheet(f"color: {_TEXT_DIM}; font-style: italic;")
        privacy_label.setWordWrap(True)
        sys_form.addRow(privacy_label)

        layout.addWidget(sys_group)

        recommendations = get_model_recommendations(self._sys_info)

        # ── Backend selector ──────────────────────────────────────────
        backend_group = QGroupBox("ENGINE")
        backend_form = QFormLayout(backend_group)
        backend_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        engine_helper = QLabel("Choose which AI backend runs on your machine.")
        engine_helper.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px; font-style: italic;")
        engine_helper.setWordWrap(True)
        backend_form.addRow(engine_helper)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem(
            "LLAMA.CPP  \u2014  Qwen3.5 35B-A3B", Backend.LLAMACPP.value
        )
        self.backend_combo.addItem(
            "OLLAMA  \u2014  Qwen3 30B-A3B", Backend.OLLAMA.value
        )
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        backend_form.addRow("Engine:", self.backend_combo)

        self.backend_status = QLabel("Checking...")
        self.backend_status.setStyleSheet(f"color: {_TEXT_DIM};")
        self.backend_status.setWordWrap(True)
        backend_form.addRow("Status:", self.backend_status)

        layout.addWidget(backend_group)

        # ── Model settings (ollama only) ──────────────────────────────
        self.model_group = QGroupBox("MODEL QUANTIZATION (OLLAMA)")
        model_form = QFormLayout(self.model_group)
        model_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        model_helper = QLabel(
            "Select a quantization level. Higher quality requires more memory."
        )
        model_helper.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px; font-style: italic;")
        model_helper.setWordWrap(True)
        model_form.addRow(model_helper)

        # Build compatibility lookup from recommendations
        q4_compat = any(
            "Q4_K_M" in r["name"] and r["compatible"]
            for r in recommendations
        )
        q8_compat = any(
            "Q8_0" in r["name"] and r["compatible"]
            for r in recommendations
        )
        bf16_compat = any(
            "BF16" in r["name"] and r["compatible"]
            for r in recommendations
        )

        # Radio button group for model selection
        self.model_button_group = QButtonGroup(self)
        self._model_radios = []
        self._radio_compat = []

        model_tiers = [
            (
                "Qwen3 30B-A3B \u2014 Q4_K_M  (~19 GB)",
                DEFAULT_MODEL,
                q4_compat,
                "RECOMMENDED" if q4_compat else "NEEDS MORE MEMORY",
                "Balanced speed and quality.",
            ),
            (
                "Qwen3 30B-A3B \u2014 Q8_0  (~33 GB)",
                Q8_MODEL,
                q8_compat,
                "HIGH QUALITY" if q8_compat else "NEEDS MORE MEMORY",
                "Higher quality output, needs more memory.",
            ),
            (
                "Qwen3 30B-A3B \u2014 FP16  (~61 GB)",
                DEV_MODEL_FP16,
                bf16_compat,
                "FULL PRECISION" if bf16_compat else "NEEDS MORE MEMORY",
                "Full precision. Maximum quality.",
            ),
        ]

        first_compatible_selected = False
        for idx, (label_text, model_tag, is_compat, compat_tag, description) in enumerate(model_tiers):
            radio = QRadioButton(f"{label_text}  [{compat_tag}]")
            if is_compat:
                radio.setStyleSheet(_RADIO_STYLE)
                if not first_compatible_selected:
                    radio.setChecked(True)
                    first_compatible_selected = True
            else:
                radio.setEnabled(False)
                radio.setStyleSheet(_RADIO_STYLE_DISABLED)

            self.model_button_group.addButton(radio, idx)
            self._model_radios.append((radio, model_tag))
            self._radio_compat.append(is_compat)
            model_form.addRow(radio)

            desc_label = QLabel(description)
            desc_color = _ACCENT if is_compat else _TEXT_DIM
            desc_label.setStyleSheet(
                f"color: {desc_color}; font-size: 10px; margin-left: 22px;"
            )
            desc_label.setWordWrap(True)
            model_form.addRow("", desc_label)

        # Hidden by default — only shown when Ollama backend is selected
        self.model_group.setVisible(False)
        layout.addWidget(self.model_group)

        # ── llama.cpp GGUF selection ──────────────────────────────────
        self.llamacpp_group = QGroupBox("MODEL (LLAMA.CPP)")
        llamacpp_form = QFormLayout(self.llamacpp_group)
        llamacpp_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        llamacpp_helper = QLabel(
            "Automatically managed local server. No configuration needed."
        )
        llamacpp_helper.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px; font-style: italic;")
        llamacpp_helper.setWordWrap(True)
        llamacpp_form.addRow(llamacpp_helper)

        # Binary status
        binary = self.llamacpp_manager.binary_path
        binary_label = QLabel(binary or "Not found")
        binary_label.setWordWrap(True)
        if binary:
            binary_label.setStyleSheet(f"color: {_TEXT};")
        else:
            binary_label.setStyleSheet(f"color: {_ERROR};")
        llamacpp_form.addRow("Binary:", binary_label)

        # GGUF model selection
        available_ggufs = self.llamacpp_manager.get_available_ggufs()
        self.gguf_button_group = QButtonGroup(self)
        self._gguf_radios: list[tuple[QRadioButton, GGUFInfo]] = []

        if available_ggufs:
            gguf_label = QLabel("Available GGUF models:")
            gguf_label.setStyleSheet(
                f"color: {_TEXT}; font-size: 10px; font-weight: bold;"
            )
            llamacpp_form.addRow(gguf_label)

            current_gguf = self.llamacpp_manager.gguf_path
            for idx, info in enumerate(available_ggufs):
                radio_text = f"{info.name}  ({info.size_gb:.1f} GB)"
                radio = QRadioButton(radio_text)
                radio.setStyleSheet(_RADIO_STYLE)

                if current_gguf and str(info.path) == str(current_gguf):
                    radio.setChecked(True)

                self.gguf_button_group.addButton(radio, idx)
                self._gguf_radios.append((radio, info))
                llamacpp_form.addRow(radio)

            if not any(r.isChecked() for r, _ in self._gguf_radios):
                self._gguf_radios[0][0].setChecked(True)
        else:
            no_gguf = QLabel(
                "[ERR] No GGUF files found. Download with:\n"
                "  ollama pull hf.co/unsloth/Qwen3.5-35B-A3B-GGUF:Q4_K_M"
            )
            no_gguf.setStyleSheet(f"color: {_ERROR}; font-size: 10px;")
            no_gguf.setWordWrap(True)
            llamacpp_form.addRow(no_gguf)

        host_label = QLabel(LLAMACPP_HOST)
        host_label.setWordWrap(True)
        llamacpp_form.addRow("Host:", host_label)

        auto_label = QLabel("Server starts automatically when this backend is selected.")
        auto_label.setStyleSheet(f"color: {_TEXT_DIM}; font-style: italic;")
        auto_label.setWordWrap(True)
        llamacpp_form.addRow(auto_label)

        layout.addWidget(self.llamacpp_group)

        # ── About ────────────────────────────────────────────────────
        about_group = QGroupBox("ABOUT")
        about_form = QFormLayout(about_group)
        about_form.addRow("App:", QLabel("Redakt"))
        about_form.addRow("License:", QLabel("MIT"))
        layout.addWidget(about_group)

        layout.addStretch()

        close_btn = QPushButton("CLOSE")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # Initial backend visibility
        self._on_backend_changed(self.backend_combo.currentIndex())
        self._check_backend_status()

    def _on_backend_changed(self, index: int):
        is_llamacpp = self.backend_combo.currentData() == Backend.LLAMACPP.value
        # Show only the relevant model section
        self.llamacpp_group.setVisible(is_llamacpp)
        self.model_group.setVisible(not is_llamacpp)
        self._check_backend_status()

    def _check_backend_status(self):
        backend = self.backend_combo.currentData()
        try:
            if backend == Backend.LLAMACPP.value:
                resp = httpx.get(f"{LLAMACPP_HOST}/health", timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "ok":
                        self.backend_status.setText(
                            "[OK] llama-server running (model loaded)"
                        )
                    else:
                        self.backend_status.setText(
                            f"[...] llama-server running (status: {data.get('status', '?')})"
                        )
                    self.backend_status.setStyleSheet(f"color: {_TEXT};")
                else:
                    self.backend_status.setText(
                        "[IDLE] Server not running \u2014 will start automatically"
                    )
                    self.backend_status.setStyleSheet(f"color: {_WARNING};")
            else:
                resp = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
                if resp.status_code == 200:
                    self.backend_status.setText("[OK] Ollama running")
                    self.backend_status.setStyleSheet(f"color: {_TEXT};")
                else:
                    self.backend_status.setText("[ERR] Ollama not responding")
                    self.backend_status.setStyleSheet(f"color: {_ERROR};")
        except Exception:
            if backend == Backend.LLAMACPP.value:
                self.backend_status.setText(
                    "[IDLE] Server not running \u2014 will start automatically"
                )
                self.backend_status.setStyleSheet(f"color: {_WARNING};")
            else:
                self.backend_status.setText("[ERR] Server not reachable")
                self.backend_status.setStyleSheet(f"color: {_ERROR};")

    def set_backend(self, backend: Backend):
        """Set the currently selected backend (e.g., from onboarding)."""
        for i in range(self.backend_combo.count()):
            if self.backend_combo.itemData(i) == backend.value:
                self.backend_combo.setCurrentIndex(i)
                break

    def set_model(self, model_tag: str):
        """Pre-select a model radio by its tag."""
        for idx, (radio, tag) in enumerate(self._model_radios):
            if tag == model_tag:
                radio.setChecked(True)
                break

    def set_gguf(self, gguf_path: str):
        """Pre-select a GGUF radio by its path."""
        for radio, info in self._gguf_radios:
            if str(info.path) == gguf_path:
                radio.setChecked(True)
                break

    def get_selected_backend(self) -> Backend:
        val = self.backend_combo.currentData()
        return Backend(val)

    def get_selected_model(self) -> str:
        checked_id = self.model_button_group.checkedId()
        if 0 <= checked_id < len(self._model_radios):
            return self._model_radios[checked_id][1]
        return DEFAULT_MODEL

    def get_selected_gguf(self) -> GGUFInfo | None:
        """Return the selected GGUF model info, or None."""
        if not hasattr(self, "_gguf_radios"):
            return None
        checked_id = self.gguf_button_group.checkedId()
        if 0 <= checked_id < len(self._gguf_radios):
            return self._gguf_radios[checked_id][1]
        return None
