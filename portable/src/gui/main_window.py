from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.parser import COAParser


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Universal COA Parser")
        self.resize(900, 600)
        self.setMinimumSize(700, 450)

        self.parser = COAParser()
        self.selected_file: str | None = None

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Universal COA Parser")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        self.label = QLabel("Drag and drop a COA file here or choose one below.")
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 12px; color: #444;")
        layout.addWidget(self.label)

        select_button = QPushButton("Select File")
        select_button.setStyleSheet("padding: 8px; font-size: 14px;")
        select_button.clicked.connect(self.select_file)
        layout.addWidget(select_button)

        self.results_list = QListWidget()
        layout.addWidget(self.results_list)

        self.setCentralWidget(container)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path:
                self.selected_file = file_path
                self.label.setText(f"Selected: {Path(file_path).name}")
                self.parse_file()

    def select_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Select COA File")
        if file_name:
            self.selected_file = file_name
            self.label.setText(f"Selected: {Path(file_name).name}")
            self.parse_file()

    def parse_file(self) -> None:
        if not self.selected_file:
            QMessageBox.information(self, "No file selected", "Please choose a COA file first.")
            return

        try:
            result = self.parser.parse_file(self.selected_file, output_dir="Output")
            self.results_list.clear()
            self.results_list.addItems([f"Format: {result.format_name}", f"Lines: {result.metadata['line_count']}"])
            if result.items:
                self.results_list.addItems([f"Item: {item}" for item in result.items[:10]])
            message = (
                f"Parsed {Path(self.selected_file).name} as {result.format_name}"
                f"\nOutput: {result.output_path or 'N/A'}"
            )
            self.label.setText(message)
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Parse failed", str(exc))
