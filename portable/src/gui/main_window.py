from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.parser import COAParser
from src.core.batch import BatchProcessor


class _BatchWorker(QObject):
    """Runs BatchProcessor in a background thread."""

    progress = Signal(int, int, str)   # current, total, filename
    finished = Signal(list)            # summary lines

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        super().__init__()
        self._input_dir = input_dir
        self._output_dir = output_dir

    def run(self) -> None:
        processor = BatchProcessor(
            self._input_dir,
            self._output_dir,
            progress_callback=lambda cur, tot, name: self.progress.emit(cur, tot, name),
        )
        processor.process_batch()
        self.finished.emit(processor.summary_lines())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Universal COA Parser")
        self.resize(900, 600)
        self.setMinimumSize(700, 450)

        self.parser = COAParser()
        self.selected_file: str | None = None
        self._batch_thread: QThread | None = None

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

        # Buttons row
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        select_button = QPushButton("Select File")
        select_button.setStyleSheet("padding: 8px; font-size: 14px;")
        select_button.clicked.connect(self.select_file)
        button_row.addWidget(select_button)

        self.batch_button = QPushButton("Batch Process Folder...")
        self.batch_button.setStyleSheet("padding: 8px; font-size: 14px;")
        self.batch_button.clicked.connect(self.select_batch_folder)
        button_row.addWidget(self.batch_button)

        layout.addLayout(button_row)

        # Progress bar (hidden until batch starts)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

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

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def select_batch_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing PDFs")
        if not folder:
            return
        input_dir = Path(folder)
        pdf_count = len(list(input_dir.glob("*.pdf")))
        if pdf_count == 0:
            QMessageBox.information(self, "No PDFs found", f"No PDF files found in:\n{folder}")
            return
        self._run_batch(input_dir, pdf_count)

    def _run_batch(self, input_dir: Path, pdf_count: int) -> None:
        output_dir = Path("Output")

        self.results_list.clear()
        self.results_list.addItem(f"Starting batch: {pdf_count} PDF(s) from {input_dir.name}/")
        self.progress_bar.setMaximum(pdf_count)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.batch_button.setEnabled(False)
        self.label.setText(f"Processing {pdf_count} file(s)...")

        self._batch_worker = _BatchWorker(input_dir, output_dir)
        self._batch_thread = QThread(self)
        self._batch_worker.moveToThread(self._batch_thread)

        self._batch_thread.started.connect(self._batch_worker.run)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.finished.connect(self._batch_thread.quit)
        self._batch_worker.finished.connect(self._batch_worker.deleteLater)
        self._batch_thread.finished.connect(self._batch_thread.deleteLater)

        self._batch_thread.start()

    def _on_batch_progress(self, current: int, total: int, filename: str) -> None:
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current}/{total}  {filename}")
        self.results_list.addItem(f"[{current}/{total}] {filename}")
        self.results_list.scrollToBottom()

    def _on_batch_finished(self, summary_lines: list) -> None:
        self.progress_bar.setVisible(False)
        self.batch_button.setEnabled(True)
        self.results_list.addItem("")
        self.results_list.addItems(summary_lines)
        self.results_list.scrollToBottom()
        self.label.setText("Batch complete. Summary saved to Output/batch_summary.json")
