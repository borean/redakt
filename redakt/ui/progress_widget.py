import time

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class ProgressWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #7f849c; font-size: 11px;")
        layout.addWidget(self.detail_label)

        # Elapsed time timer
        self._start_time: float = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed)
        self._current_stage = ""

    @Slot(float, str)
    def set_progress(self, percent: float, status: str):
        self.progress_bar.setVisible(True)
        if percent < 0:
            # Indeterminate mode (pulsing bar)
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(percent))
        self.status_label.setText(status)

    def set_stage(self, file_name: str, stage: str, file_num: int = 0, total_files: int = 0):
        """Show detailed stage info during processing."""
        self._current_stage = stage
        if not self._start_time:
            self._start_time = time.time()
            self._timer.start()

        self.progress_bar.setVisible(True)

        if total_files > 0:
            file_pct = (file_num - 1) / total_files * 100
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(file_pct))
            prefix = f"[{file_num}/{total_files}] {file_name}"
        else:
            prefix = file_name

        self.status_label.setText(f"{prefix}")
        self._update_elapsed()

    def set_stage_detail(self, detail: str):
        """Update just the detail line (e.g. chunk progress)."""
        self._current_stage = detail
        self._update_elapsed()

    def _update_elapsed(self):
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            time_str = f"{mins}:{secs:02d}" if mins else f"{secs}s"
            self.detail_label.setText(f"{self._current_stage}  ·  {time_str} elapsed")

    def set_complete(self):
        self._timer.stop()
        elapsed = int(time.time() - self._start_time) if self._start_time else 0
        mins, secs = divmod(elapsed, 60)
        time_str = f"{mins}:{secs:02d}" if mins else f"{secs}s"

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText("Complete / Tamamlandi")
        self.status_label.setStyleSheet("color: #a6e3a1; font-size: 12px;")
        self.detail_label.setText(f"Finished in {time_str}")
        self.detail_label.setStyleSheet("color: #a6e3a1; font-size: 11px;")

    def reset(self):
        self._timer.stop()
        self._start_time = 0
        self._current_stage = ""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.status_label.setText("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.detail_label.setText("")
        self.detail_label.setStyleSheet("color: #7f849c; font-size: 11px;")
