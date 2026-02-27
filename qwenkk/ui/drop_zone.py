from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from qwenkk.constants import SUPPORTED_EXTENSIONS

_NORMAL_STYLE = (
    "QLabel#dropLabel { border: 2px dashed #585b70; border-radius: 12px; "
    "padding: 24px; font-size: 14px; color: #a6adc8; }"
)
_HOVER_STYLE = (
    "QLabel#dropLabel { border: 2px dashed #89b4fa; border-radius: 12px; "
    "padding: 24px; font-size: 14px; color: #89b4fa; }"
)


class DropZone(QWidget):
    """Drag-and-drop area for file input."""

    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        self.label = QLabel(
            "Drag & Drop Files Here\n"
            "or Click to Browse\n\n"
            "DOCX  |  PDF  |  XLSX  |  Images"
        )
        self.label.setObjectName("dropLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(_NORMAL_STYLE)
        layout.addWidget(self.label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ext_filter = "Supported Files ({})".format(
                " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
            )
            files, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", ext_filter)
            if files:
                self.files_dropped.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.label.setStyleSheet(_HOVER_STYLE)

    def dragLeaveEvent(self, event):
        self.label.setStyleSheet(_NORMAL_STYLE)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls]
        valid = [
            fp
            for fp in file_paths
            if any(fp.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
        ]
        if valid:
            self.files_dropped.emit(valid)
        self.label.setStyleSheet(_NORMAL_STYLE)
