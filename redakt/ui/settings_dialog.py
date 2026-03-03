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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from redakt.constants import LLAMACPP_HOST, LLAMACPP_MODEL
from redakt.core.llamacpp_manager import GGUFInfo, LlamaCppManager
from redakt.ui import theme as theme_module
from redakt.core.sysinfo import (
    format_system_summary,
    get_model_recommendations,
    get_system_info,
)

def _c():
    tm = getattr(theme_module, "theme_manager", None)
    return tm.get_colors() if tm else theme_module._DARK

# ── Settings keys ─────────────────────────────────────────────────────────────
_KEY_GGUF_PATH = "config/gguf_path"
_KEY_THEME = "config/theme"


def load_settings() -> dict:
    """Load persisted settings. Returns dict with gguf_path and theme."""
    s = QSettings()
    return {
        "gguf_path": s.value(_KEY_GGUF_PATH, ""),
        "theme": s.value(_KEY_THEME, "dark"),
    }


def save_settings(gguf_path: str = "", theme: str = ""):
    """Persist settings to disk via QSettings."""
    s = QSettings()
    if gguf_path != "":
        s.setValue(_KEY_GGUF_PATH, gguf_path)
    if theme:
        s.setValue(_KEY_THEME, theme)
    s.sync()


class SettingsDialog(QDialog):
    def __init__(self, llamacpp_manager: LlamaCppManager, parent=None):
        super().__init__(parent)
        self.llamacpp_manager = llamacpp_manager
        self.setWindowTitle("Redakt Config")
        self.setMinimumWidth(620)
        self.setMinimumHeight(480)

        c = _c()
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Appearance (theme) — fixed at top, always visible ─────────
        appearance_group = QGroupBox("APPEARANCE")
        appearance_form = QFormLayout(appearance_group)
        appearance_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light", "System"])
        self.theme_combo.setToolTip(
            "System follows your macOS light/dark mode preference."
        )
        tm = getattr(theme_module, "theme_manager", None)
        if tm:
            pref = tm.get_theme()
            idx = {"dark": 0, "light": 1, "system": 2}.get(pref, 0)
            self.theme_combo.setCurrentIndex(idx)
        appearance_form.addRow("Colors:", self.theme_combo)

        self.style_combo = QComboBox()
        self.style_combo.addItems(["Clinical", "Terminal"])
        self.style_combo.setToolTip(
            "Clinical: clean sans-serif for medical professionals.  "
            "Terminal: compact monospace for power users."
        )
        if tm:
            style_pref = tm.get_ui_style()
            style_idx = {"clinical": 0, "terminal": 1}.get(style_pref, 0)
            self.style_combo.setCurrentIndex(style_idx)
        appearance_form.addRow("Style:", self.style_combo)
        root.addWidget(appearance_group)

        # ── Scrollable content ───────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        # ── System info ──────────────────────────────────────────────
        sys_group = QGroupBox("YOUR SYSTEM")
        sys_form = QFormLayout(sys_group)
        sys_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        sys_helper = QLabel(
            "Hardware detected on this machine.\n"
            "Model compatibility depends on available memory."
        )
        sys_helper.setStyleSheet(f"color: {c['TEXT_DIM']}; font-size: 10px; font-style: italic;")
        sys_helper.setWordWrap(True)
        sys_form.addRow(sys_helper)

        self._sys_info = get_system_info()
        sys_summary = format_system_summary(self._sys_info)
        sys_label = QLabel(sys_summary)
        sys_label.setStyleSheet(f"color: {c['TEXT']}; font-weight: bold;")
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
        detail_label.setStyleSheet(f"color: {c['TEXT_DIM']};")
        detail_label.setWordWrap(True)
        sys_form.addRow(detail_label)

        # Data privacy notice
        privacy_label = QLabel(
            "All processing runs locally on this machine. "
            "No data is sent to any cloud service."
        )
        privacy_label.setStyleSheet(f"color: {c['TEXT_DIM']}; font-style: italic;")
        privacy_label.setWordWrap(True)
        sys_form.addRow(privacy_label)

        layout.addWidget(sys_group)

        # ── llama.cpp GGUF selection ──────────────────────────────────
        self.llamacpp_group = QGroupBox("MODEL")
        llamacpp_form = QFormLayout(self.llamacpp_group)
        llamacpp_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        llamacpp_helper = QLabel(
            "Automatically managed local server. No configuration needed."
        )
        llamacpp_helper.setStyleSheet(f"color: {c['TEXT_DIM']}; font-size: 10px; font-style: italic;")
        llamacpp_helper.setWordWrap(True)
        llamacpp_form.addRow(llamacpp_helper)

        # Binary status
        binary = self.llamacpp_manager.binary_path
        binary_label = QLabel(binary or "Not found")
        binary_label.setWordWrap(True)
        if binary:
            binary_label.setStyleSheet(f"color: {c['TEXT']};")
        else:
            binary_label.setStyleSheet(f"color: {c['ERROR']};")
        llamacpp_form.addRow("Binary:", binary_label)

        # GGUF model selection
        available_ggufs = self.llamacpp_manager.get_available_ggufs()
        self.gguf_button_group = QButtonGroup(self)
        self._gguf_radios: list[tuple[QRadioButton, GGUFInfo]] = []

        if available_ggufs:
            gguf_label = QLabel("Available GGUF models:")
            gguf_label.setStyleSheet(
                f"color: {c['TEXT']}; font-size: 10px; font-weight: bold;"
            )
            llamacpp_form.addRow(gguf_label)

            current_gguf = self.llamacpp_manager.gguf_path
            for idx, info in enumerate(available_ggufs):
                radio_text = f"{info.name}  ({info.size_gb:.1f} GB)"
                radio = QRadioButton(radio_text)
                radio.setStyleSheet(
                    f"QRadioButton {{ color: {c['TEXT']}; font-weight: bold; spacing: 8px; }}"
                    f"QRadioButton::indicator {{ width: 14px; height: 14px; "
                    f"  border: 2px solid {c['BG_LIGHTER']}; border-radius: 9px; background: {c['BG_MID']}; }}"
                    f"QRadioButton::indicator:checked {{ background: {c['ACCENT']}; border-color: {c['ACCENT']}; }}"
                    f"QRadioButton::indicator:hover {{ border-color: {c['BORDER_ACTIVE']}; }}"
                )

                if current_gguf and str(info.path) == str(current_gguf):
                    radio.setChecked(True)

                self.gguf_button_group.addButton(radio, idx)
                self._gguf_radios.append((radio, info))
                llamacpp_form.addRow(radio)

            if not any(r.isChecked() for r, _ in self._gguf_radios):
                self._gguf_radios[0][0].setChecked(True)
        else:
            no_gguf = QLabel(
                "[ERR] No GGUF files found. Use the setup wizard to download "
                "the model from Hugging Face."
            )
            no_gguf.setStyleSheet(f"color: {c['ERROR']}; font-size: 10px;")
            no_gguf.setWordWrap(True)
            llamacpp_form.addRow(no_gguf)

        host_label = QLabel(LLAMACPP_HOST)
        host_label.setWordWrap(True)
        llamacpp_form.addRow("Host:", host_label)

        self.server_status = QLabel("Checking...")
        self.server_status.setStyleSheet(f"color: {c['TEXT_DIM']};")
        self.server_status.setWordWrap(True)
        llamacpp_form.addRow("Status:", self.server_status)

        auto_label = QLabel("Server starts automatically when needed.")
        auto_label.setStyleSheet(f"color: {c['TEXT_DIM']}; font-style: italic;")
        auto_label.setWordWrap(True)
        llamacpp_form.addRow(auto_label)

        layout.addWidget(self.llamacpp_group)

        # ── About ────────────────────────────────────────────────────
        about_group = QGroupBox("ABOUT")
        about_form = QFormLayout(about_group)
        about_form.addRow("App:", QLabel("Redakt"))
        about_form.addRow("License:", QLabel("MIT"))
        layout.addWidget(about_group)

        scroll.setWidget(content)
        root.addWidget(scroll)

        close_btn = QPushButton("CLOSE")
        close_btn.clicked.connect(self._on_close)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._check_server_status()

    def _on_close(self):
        """Save theme + style and apply before closing."""
        tm = getattr(theme_module, "theme_manager", None)
        if not tm:
            self.accept()
            return

        theme_map = {"Dark": "dark", "Light": "light", "System": "system"}
        theme_value = theme_map.get(self.theme_combo.currentText(), "dark")

        style_map = {"Clinical": "clinical", "Terminal": "terminal"}
        style_value = style_map.get(self.style_combo.currentText(), "clinical")

        changed = False
        if tm.get_theme() != theme_value:
            # set_theme emits theme_changed, so defer style change
            from PySide6.QtCore import QSettings
            s = QSettings()
            s.setValue("config/theme", theme_value)
            s.setValue("config/ui_style", style_value)
            s.sync()
            tm.theme_changed.emit()
            changed = True
        elif tm.get_ui_style() != style_value:
            tm.set_ui_style(style_value)
            changed = True

        self.accept()

    def _check_server_status(self):
        c = _c()
        try:
            resp = httpx.get(f"{LLAMACPP_HOST}/health", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    self.server_status.setText("[OK] Server running (model loaded)")
                else:
                    self.server_status.setText(
                        f"[...] Server running (status: {data.get('status', '?')})"
                    )
                self.server_status.setStyleSheet(f"color: {c['TEXT']};")
            else:
                self.server_status.setText(
                    "[IDLE] Not running — will start automatically when needed"
                )
                self.server_status.setStyleSheet(f"color: {c['WARNING']};")
        except Exception:
            self.server_status.setText(
                "[IDLE] Not running — will start automatically when needed"
            )
            self.server_status.setStyleSheet(f"color: {c['WARNING']};")

    def set_gguf(self, gguf_path: str):
        """Pre-select a GGUF radio by its path."""
        for radio, info in self._gguf_radios:
            if str(info.path) == gguf_path:
                radio.setChecked(True)
                break

    def get_selected_gguf(self) -> GGUFInfo | None:
        """Return the selected GGUF model info, or None."""
        if not hasattr(self, "_gguf_radios"):
            return None
        checked_id = self.gguf_button_group.checkedId()
        if 0 <= checked_id < len(self._gguf_radios):
            return self._gguf_radios[checked_id][1]
        return None
