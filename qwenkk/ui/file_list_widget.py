import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class FileListWidget(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMaximumHeight(220)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSpacing(4)
        self.setWidget(container)

        self._items: dict[str, QFrame] = {}

    def add_file(self, file_path: Path):
        key = str(file_path)
        if key in self._items:
            return

        item = QFrame()
        item.setObjectName("fileItem")
        row = QHBoxLayout(item)
        row.setContentsMargins(8, 4, 8, 4)

        name_label = QLabel(file_path.name)
        name_label.setToolTip(str(file_path))
        name_label.setStyleSheet("font-size: 13px;")
        row.addWidget(name_label)
        row.addStretch()

        status_label = QLabel("Ready")
        status_label.setObjectName("status")
        status_label.setStyleSheet("color: #f9e2af; font-size: 12px;")
        row.addWidget(status_label)

        remove_btn = QPushButton("x")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet(
            "QPushButton { color: #f38ba8; border: none; font-weight: bold; }"
            "QPushButton:hover { color: #eba0ac; }"
        )
        remove_btn.clicked.connect(lambda: self._remove_item(key))
        row.addWidget(remove_btn)

        self._layout.addWidget(item)
        self._items[key] = item

    def mark_processing(self, file_path: Path):
        key = str(file_path)
        item = self._items.get(key)
        if not item:
            return
        status = item.findChild(QLabel, "status")
        if status:
            status.setText("⏳ Processing...")
            status.setStyleSheet("color: #89b4fa; font-size: 12px; font-weight: bold;")

    def mark_complete(self, input_path: Path, output_path: Path, entity_count: int):
        key = str(input_path)
        item = self._items.get(key)
        if not item:
            return

        status = item.findChild(QLabel, "status")
        if status:
            status.setText(f"Done - {entity_count} PII found")
            status.setStyleSheet("color: #a6e3a1; font-size: 12px;")

        open_btn = QPushButton("Open")
        open_btn.setStyleSheet(
            "QPushButton { background-color: #313244; color: #89b4fa; "
            "border: 1px solid #89b4fa; border-radius: 4px; padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: #45475a; }"
        )
        open_btn.clicked.connect(lambda: self._open_file(output_path))
        item.layout().insertWidget(item.layout().count() - 1, open_btn)

    def mark_error(self, file_path: Path, message: str):
        key = str(file_path)
        item = self._items.get(key)
        if not item:
            return
        status = item.findChild(QLabel, "status")
        if status:
            status.setText(f"Error: {message[:40]}")
            status.setStyleSheet("color: #f38ba8; font-size: 12px;")
            status.setToolTip(message)

    def get_files(self) -> list[Path]:
        return [Path(key) for key in self._items]

    def clear_all(self):
        for item in self._items.values():
            self._layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()

    def _remove_item(self, key: str):
        item = self._items.pop(key, None)
        if item:
            self._layout.removeWidget(item)
            item.deleteLater()

    @staticmethod
    def _open_file(path: Path):
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)])
        elif sys.platform == "win32":
            subprocess.run(["start", str(path)], shell=True)  # noqa: S603
        else:
            subprocess.run(["xdg-open", str(path)])
