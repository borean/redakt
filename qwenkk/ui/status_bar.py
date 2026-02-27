import psutil
from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

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


class OllamaStatusBar(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        self.ollama_indicator = QLabel("ENGINE: CHECKING...")
        self.ollama_indicator.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px;"
        )
        self.model_indicator = QLabel("MODEL: --")
        self.model_indicator.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px;"
        )

        layout.addWidget(self.ollama_indicator)
        layout.addWidget(self.model_indicator)

        layout.addStretch()

        # CPU usage
        self._cpu_label = QLabel("CPU: --%")
        self._cpu_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px;")
        layout.addWidget(self._cpu_label)

        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setFixedSize(60, 10)
        self._cpu_bar.setTextVisible(False)
        self._cpu_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {_BG_MID};
                border: 1px solid {_BORDER};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {_TEXT_DIM};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._cpu_bar)

        layout.addSpacing(8)

        # RAM usage
        self._ram_label = QLabel("RAM: --/--GB")
        self._ram_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px;")
        layout.addWidget(self._ram_label)

        self._ram_bar = QProgressBar()
        self._ram_bar.setRange(0, 100)
        self._ram_bar.setFixedSize(60, 10)
        self._ram_bar.setTextVisible(False)
        self._ram_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {_BG_MID};
                border: 1px solid {_BORDER};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {_TEXT_DIM};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._ram_bar)

        layout.addSpacing(10)

        # LOCAL badge — permanent indicator
        self._local_badge = QLabel("LOCAL")
        self._local_badge.setStyleSheet(
            f"color: {_SUCCESS}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 1.5px; border: 1px solid {_SUCCESS}40; "
            f"border-radius: 2px; padding: 1px 6px;"
        )
        layout.addWidget(self._local_badge)

        self.setStyleSheet(
            f"OllamaStatusBar {{ background-color: {_BG_DARKEST}; "
            f"border: 1px solid {_BORDER}; border-radius: 2px; }}"
        )

        # Resource monitor timer
        self._resource_timer = QTimer(self)
        self._resource_timer.timeout.connect(self._update_resources)
        self._resource_timer.start(2000)  # every 2 seconds
        self._update_resources()  # initial update

    @Slot(bool)
    def set_ollama_status(self, running: bool):
        if running:
            self.ollama_indicator.setText("ENGINE: CONNECTED")
            self.ollama_indicator.setStyleSheet(
                f"color: {_TEXT}; font-size: 10px; letter-spacing: 1px;"
            )
        else:
            self.ollama_indicator.setText("ENGINE: OFFLINE")
            self.ollama_indicator.setStyleSheet(
                f"color: {_ERROR}; font-size: 10px; letter-spacing: 1px;"
            )

    @Slot(bool)
    def set_active_inference(self, active: bool):
        """Switch resource monitor between idle and active visual modes."""
        if active:
            self.ollama_indicator.setText("ENGINE: INFERENCING...")
            self.ollama_indicator.setStyleSheet(
                f"color: {_ACCENT}; font-size: 10px; letter-spacing: 1px;"
            )
            self._resource_timer.setInterval(500)  # faster polling during inference
            bar_style = f"""
                QProgressBar {{
                    background: {_BG_MID};
                    border: 1px solid {_ACCENT}40;
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background: {_ACCENT};
                    border-radius: 2px;
                }}
            """
            self._cpu_bar.setStyleSheet(bar_style)
            self._ram_bar.setStyleSheet(bar_style)
            self._cpu_label.setStyleSheet(f"color: {_TEXT}; font-size: 10px;")
            self._ram_label.setStyleSheet(f"color: {_TEXT}; font-size: 10px;")
        else:
            self.ollama_indicator.setText("ENGINE: CONNECTED")
            self.ollama_indicator.setStyleSheet(
                f"color: {_TEXT}; font-size: 10px; letter-spacing: 1px;"
            )
            self._resource_timer.setInterval(2000)  # slow polling when idle
            bar_style = f"""
                QProgressBar {{
                    background: {_BG_MID};
                    border: 1px solid {_BORDER};
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background: {_TEXT_DIM};
                    border-radius: 2px;
                }}
            """
            self._cpu_bar.setStyleSheet(bar_style)
            self._ram_bar.setStyleSheet(bar_style)
            self._cpu_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px;")
            self._ram_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px;")

    @Slot(str)
    def set_model_status(self, status: str):
        self.model_indicator.setText(f"MODEL: {status.upper()}")
        if "ready" in status.lower() or "qwen" in status.lower():
            self.model_indicator.setStyleSheet(
                f"color: {_TEXT}; font-size: 10px; letter-spacing: 1px;"
            )
        elif "starting" in status.lower() or "loading" in status.lower() or "scanning" in status.lower():
            self.model_indicator.setStyleSheet(
                f"color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px;"
            )
        elif "failed" in status.lower() or "error" in status.lower():
            self.model_indicator.setStyleSheet(
                f"color: {_ERROR}; font-size: 10px; letter-spacing: 1px;"
            )
        else:
            self.model_indicator.setStyleSheet(
                f"color: {_TEXT_DIM}; font-size: 10px; letter-spacing: 1px;"
            )

    @Slot()
    def _update_resources(self):
        """Poll system CPU and RAM usage."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()

            self._cpu_bar.setValue(int(cpu))
            self._cpu_label.setText(f"CPU: {int(cpu)}%")

            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            self._ram_bar.setValue(int(mem.percent))
            self._ram_label.setText(f"RAM: {used_gb:.0f}/{total_gb:.0f}GB")
        except Exception:
            pass  # psutil can occasionally fail, just skip
