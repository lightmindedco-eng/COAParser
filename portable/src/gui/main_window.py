import re
import subprocess
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.visual_output import VisualOutputWidget
from src.parser import COAParser
from src.core.batch import BatchProcessor

INPUT_DIR = Path("Input")
_OUTPUT_ROLE = Qt.UserRole + 1
_PRODUCT_ROLE = Qt.UserRole + 2
_CATEGORY_ROLE = Qt.UserRole + 3
_DATE_ROLE = Qt.UserRole + 4
_COMPANY_ROLE = Qt.UserRole + 5

SORT_ALPHA_ASC = 0
SORT_ALPHA_DESC = 1
SORT_TEST_DATE = 2
SORT_FILE_DATE = 3


class _BatchWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(list)

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


class _PreloadWorker(QObject):
    updated = Signal(str, str, str, str, str, str)  # file_path, product_name, output_name, category, date, company
    progress = Signal(int, int)  # current, total
    finished = Signal()

    def run(self) -> None:
        parser = COAParser()
        pdfs = sorted(INPUT_DIR.glob("*.pdf"))
        total = len(pdfs)
        for idx, pdf in enumerate(pdfs, 1):
            try:
                result = parser.parse_file(str(pdf), output_dir="Output")
                prod_name = result.metadata.get("product_name") or ""
                out_name = Path(result.output_path).name if result.output_path else ""
                category = result.metadata.get("metrc_category") or ""
                date = result.metadata.get("report_date") or ""
                company = result.metadata.get("company_name") or ""
            except Exception:
                prod_name = out_name = category = date = company = ""
            self.updated.emit(str(pdf), prod_name, out_name, category, date, company)
            self.progress.emit(idx, total)
        self.finished.emit()


def _get_base_name(stem: str) -> str:
    while True:
        new = re.sub(r'-\d+$', '', stem)
        if new == stem:
            break
        stem = new
    return stem


class _DuplicateDialog(QDialog):
    def __init__(self, groups: dict[str, list[str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate Files Detected")
        self.setMinimumWidth(520)
        self.resize(520, 420)

        layout = QVBoxLayout(self)

        msg = QLabel(
            "The following files appear to be duplicates "
            "(same base name with -1, -2, etc. suffixes).\n"
            "Check the files you want to DELETE, then click the button."
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self._checkboxes: list[tuple[QCheckBox, str]] = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        for base_name in sorted(groups):
            files = groups[base_name]
            header = QLabel(f"<b>{base_name}</b>  ({len(files)} files)")
            header.setStyleSheet("font-size: 13px; margin-top: 6px;")
            scroll_layout.addWidget(header)
            for fp in sorted(files):
                cb = QCheckBox(Path(fp).name)
                self._checkboxes.append((cb, fp))
                scroll_layout.addWidget(cb)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        self._delete_btn = QPushButton("Delete Checked")
        self._delete_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Keep All")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self._delete_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_files_to_delete(self) -> list[str]:
        return [fp for cb, fp in self._checkboxes if cb.isChecked()]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Universal COA Parser")
        self.resize(1400, 800)
        self.setMinimumSize(1100, 600)

        self.parser = COAParser()
        self.selected_file: str | None = None
        self._batch_thread: QThread | None = None
        self._preload_thread: QThread | None = None
        self._pdf_document = QPdfDocument(self)
        self._sort_mode = SORT_ALPHA_ASC
        self._ignore_filter_signal = False

        container = QWidget(self)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(8)

        title = QLabel("Universal COA Parser")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        main_layout.addWidget(title)

        self.label = QLabel("Select a file from the list on the left, or drag & drop a COA file.")
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 12px; color: #444;")
        main_layout.addWidget(self.label)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        select_button = QPushButton("Select File...")
        select_button.setStyleSheet("padding: 6px; font-size: 13px;")
        select_button.clicked.connect(self.select_file)
        button_row.addWidget(select_button)

        self.batch_button = QPushButton("Batch Process All...")
        self.batch_button.setStyleSheet("padding: 6px; font-size: 13px;")
        self.batch_button.clicked.connect(self.select_batch_folder)
        button_row.addWidget(self.batch_button)

        main_layout.addLayout(button_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        splitter = QSplitter(Qt.Horizontal)

        # --- Left panel ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        input_label = QLabel("Input Files")
        input_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        left_layout.addWidget(input_label)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files...")
        self.search_box.textChanged.connect(self._apply_filters)
        left_layout.addWidget(self.search_box)

        # Filter / sort bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Sort A-Z", SORT_ALPHA_ASC)
        self.sort_combo.addItem("Sort Z-A", SORT_ALPHA_DESC)
        self.sort_combo.addItem("Test Date", SORT_TEST_DATE)
        self.sort_combo.addItem("File Date", SORT_FILE_DATE)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_row.addWidget(self.sort_combo)

        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", "")
        self.category_combo.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.category_combo)

        left_layout.addLayout(filter_row)

        filter_row2 = QHBoxLayout()
        filter_row2.setSpacing(6)
        filter_row2.addWidget(QLabel("Company:"))
        self.company_combo = QComboBox()
        self.company_combo.addItem("All Companies", "")
        self.company_combo.currentIndexChanged.connect(self._apply_filters)
        filter_row2.addWidget(self.company_combo, stretch=1)
        left_layout.addLayout(filter_row2)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(350)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_context_menu)
        self.file_list.currentItemChanged.connect(self._on_file_selected)
        left_layout.addWidget(self.file_list)

        splitter.addWidget(left_widget)

        # --- Center panel ---
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        output_label = QLabel("Parsed Output")
        output_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        center_layout.addWidget(output_label)

        self.output_tabs = QTabWidget()

        self.output_visual = VisualOutputWidget()
        self.output_tabs.addTab(self.output_visual, "Visual")

        self.output_text_view = QPlainTextEdit()
        self.output_text_view.setReadOnly(True)
        self.output_text_view.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        self.output_tabs.addTab(self.output_text_view, "Text")

        center_layout.addWidget(self.output_tabs)

        splitter.addWidget(center_widget)

        # --- Right panel ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        pdf_label = QLabel("Original PDF")
        pdf_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        right_layout.addWidget(pdf_label)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(32)
        zoom_in_btn.clicked.connect(self._zoom_in)
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedWidth(32)
        zoom_out_btn.clicked.connect(self._zoom_out)
        zoom_fit_btn = QPushButton("Fit")
        zoom_fit_btn.clicked.connect(self._zoom_fit)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("font-size: 12px; min-width: 40px;")
        zoom_row.addWidget(zoom_in_btn)
        zoom_row.addWidget(zoom_out_btn)
        zoom_row.addWidget(zoom_fit_btn)
        zoom_row.addWidget(self._zoom_label)
        zoom_row.addStretch()
        right_layout.addLayout(zoom_row)

        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(None)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.pdf_view.setZoomFactor(1.0)
        right_layout.addWidget(self.pdf_view)

        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)

        main_layout.addWidget(splitter, stretch=1)

        self.setCentralWidget(container)
        self.setAcceptDrops(True)

        self._handle_duplicates()
        self._refresh_file_list()

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def _handle_duplicates(self) -> None:
        pdfs = list(INPUT_DIR.glob("*.pdf"))
        groups: dict[str, list[str]] = defaultdict(list)
        for p in pdfs:
            groups[_get_base_name(p.stem)].append(str(p))
        groups = {k: v for k, v in groups.items() if len(v) > 1}
        if not groups:
            return

        dialog = _DuplicateDialog(groups, self)
        if dialog.exec() != QDialog.Accepted:
            return
        to_delete = dialog.get_files_to_delete()
        if not to_delete:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to permanently delete {len(to_delete)} file(s)?\n\n"
            + "\n".join(Path(f).name for f in to_delete),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for fp in to_delete:
            try:
                Path(fp).unlink()
            except OSError as e:
                QMessageBox.warning(self, "Error", f"Could not delete {Path(fp).name}: {e}")

    # ------------------------------------------------------------------
    # File list
    # ------------------------------------------------------------------

    def _refresh_file_list(self) -> None:
        self.file_list.blockSignals(True)
        self.file_list.clear()
        pdfs = sorted(INPUT_DIR.glob("*.pdf"))
        for p in pdfs:
            self.file_list.addItem(p.name)
            item = self.file_list.item(self.file_list.count() - 1)
            item.setData(Qt.UserRole, str(p))
        self.file_list.blockSignals(False)
        if pdfs:
            self.file_list.setCurrentRow(0)
        self._start_preload()

    def _start_preload(self) -> None:
        if self._preload_thread and self._preload_thread.isRunning():
            self._preload_thread.quit()
            self._preload_thread.wait()

        self.label.setText("Pre-loading output names...")

        total = self.file_list.count()
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"Pre-loading 0/{total}")
            self.progress_bar.setVisible(True)

        self._preload_worker = _PreloadWorker()
        self._preload_thread = QThread(self)
        self._preload_worker.moveToThread(self._preload_thread)

        self._preload_thread.started.connect(self._preload_worker.run)
        self._preload_worker.updated.connect(self._on_preload_updated)
        self._preload_worker.progress.connect(self._on_preload_progress)
        self._preload_worker.finished.connect(self._preload_thread.quit)
        self._preload_worker.finished.connect(self._preload_worker.deleteLater)
        self._preload_thread.finished.connect(self._preload_thread.deleteLater)
        self._preload_thread.finished.connect(self._on_preload_finished)

        self._preload_thread.start()

    def _on_preload_updated(self, file_path: str, product_name: str, output_name: str, category: str, date: str, company: str) -> None:
        self._update_list_item(file_path, product_name or None, output_name or None, category or None, date or None, company or None)

    def _on_preload_progress(self, current: int, total: int) -> None:
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Pre-loading {current}/{total}")

    def _on_preload_finished(self) -> None:
        self.progress_bar.setVisible(False)
        self._populate_category_combo()
        self._populate_company_combo()
        self._sort_and_rebuild()
        self._apply_filters()
        if not self.selected_file:
            self.label.setText("Ready. Select a file from the list on the left.")

    def _populate_category_combo(self) -> None:
        cats = set()
        for i in range(self.file_list.count()):
            cat = self.file_list.item(i).data(_CATEGORY_ROLE) or ""
            if cat:
                cats.add(cat)
        self._ignore_filter_signal = True
        current = self.category_combo.currentText()
        self.category_combo.clear()
        self.category_combo.addItem("All Categories", "")
        for c in sorted(cats):
            self.category_combo.addItem(c, c)
        idx = self.category_combo.findText(current)
        if idx >= 0:
            self.category_combo.setCurrentIndex(idx)
        self._ignore_filter_signal = False

    def _populate_company_combo(self) -> None:
        companies = set()
        for i in range(self.file_list.count()):
            co = self.file_list.item(i).data(_COMPANY_ROLE) or ""
            if co:
                companies.add(co)
        self._ignore_filter_signal = True
        current = self.company_combo.currentText()
        self.company_combo.clear()
        self.company_combo.addItem("All Companies", "")
        for c in sorted(companies):
            self.company_combo.addItem(c, c)
        idx = self.company_combo.findText(current)
        if idx >= 0:
            self.company_combo.setCurrentIndex(idx)
        self._ignore_filter_signal = False

    # ------------------------------------------------------------------
    # Sort
    # ------------------------------------------------------------------

    def _on_sort_changed(self) -> None:
        self._sort_mode = self.sort_combo.currentData()
        self._sort_and_rebuild()
        self._apply_filters()

    def _sort_and_rebuild(self) -> None:
        items_data = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            items_data.append({
                "file_path": item.data(Qt.UserRole),
                "output_name": item.data(_OUTPUT_ROLE),
                "product_name": item.data(_PRODUCT_ROLE),
                "category": item.data(_CATEGORY_ROLE),
                "date": item.data(_DATE_ROLE),
                "company": item.data(_COMPANY_ROLE),
                "text": item.text(),
            })

        def _sort_key(d: dict) -> tuple:
            mode = self._sort_mode
            if mode == SORT_ALPHA_ASC:
                return (d["text"] or "").lower(),
            elif mode == SORT_ALPHA_DESC:
                return (d["text"] or "").lower(),
            elif mode == SORT_TEST_DATE:
                return d.get("date") or "",
            elif mode == SORT_FILE_DATE:
                fp = d["file_path"]
                if fp:
                    try:
                        mtime = Path(fp).stat().st_mtime
                    except OSError:
                        mtime = 0
                else:
                    mtime = 0
                return mtime,
            return (d["text"] or "").lower(),

        reverse = self._sort_mode == SORT_ALPHA_DESC
        items_data.sort(key=_sort_key, reverse=reverse)

        selected_fp = self.file_list.currentItem().data(Qt.UserRole) if self.file_list.currentItem() else None

        self.file_list.blockSignals(True)
        self.file_list.clear()
        for d in items_data:
            self.file_list.addItem(d["text"])
            item = self.file_list.item(self.file_list.count() - 1)
            item.setData(Qt.UserRole, d["file_path"])
            item.setData(_OUTPUT_ROLE, d["output_name"])
            item.setData(_PRODUCT_ROLE, d["product_name"])
            item.setData(_CATEGORY_ROLE, d["category"])
            item.setData(_DATE_ROLE, d["date"])
            item.setData(_COMPANY_ROLE, d["company"])
        self.file_list.blockSignals(False)

        if selected_fp:
            for i in range(self.file_list.count()):
                if self.file_list.item(i).data(Qt.UserRole) == selected_fp:
                    self.file_list.setCurrentRow(i)
                    break

    # ------------------------------------------------------------------
    # Search / filter
    # ------------------------------------------------------------------

    def _apply_filters(self) -> None:
        if self._ignore_filter_signal:
            return
        query = self.search_box.text().strip().lower()
        cat_filter = self.category_combo.currentData() or ""
        co_filter = self.company_combo.currentData() or ""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            text_match = not query or query in item.text().lower() or (item.data(_COMPANY_ROLE) or "").lower().startswith(query)
            cat_match = not cat_filter or (item.data(_CATEGORY_ROLE) or "") == cat_filter
            co_match = not co_filter or (item.data(_COMPANY_ROLE) or "") == co_filter
            item.setHidden(not (text_match and cat_match and co_match))

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        item = self.file_list.itemAt(pos)
        if not item:
            return
        file_path = item.data(Qt.UserRole)
        if not file_path:
            return
        output_name = item.data(_OUTPUT_ROLE)

        menu = QMenu(self)

        act_input = QAction("Open Input File Location", self)
        act_input.triggered.connect(lambda: _open_file_location(file_path))
        menu.addAction(act_input)

        if output_name:
            out_path = str(Path("Output") / output_name)
            act_output = QAction("Open Output File Location", self)
            act_output.triggered.connect(lambda: _open_file_location(out_path))
            menu.addAction(act_output)

        menu.exec(self.file_list.mapToGlobal(pos))

    def _update_list_item(self, file_path: str, product_name: str | None, output_name: str | None, category: str | None = None, date: str | None = None, company: str | None = None) -> None:
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item and item.data(Qt.UserRole) == file_path:
                item.setData(_OUTPUT_ROLE, output_name)
                item.setData(_PRODUCT_ROLE, product_name)
                item.setData(_CATEGORY_ROLE, category)
                item.setData(_DATE_ROLE, date)
                item.setData(_COMPANY_ROLE, company)
                pdf_name = Path(file_path).name
                parts = []
                if company:
                    parts.append(f"({company})")
                if product_name:
                    parts.append(product_name)
                parts.append(f"[{pdf_name}]")
                text = "  ".join(parts) if parts else pdf_name
                item.setText(text)
                break

    def _on_file_selected(self, current, _previous) -> None:
        if current is None:
            return
        file_path = current.data(Qt.UserRole)
        if not file_path:
            return
        self.selected_file = file_path
        self.label.setText(f"Selected: {Path(file_path).name}")
        self._parse_and_display()

    # ------------------------------------------------------------------
    # Parse & display
    # ------------------------------------------------------------------

    def _parse_and_display(self) -> None:
        if not self.selected_file:
            return
        try:
            result = self.parser.parse_file(self.selected_file, output_dir="Output")
            product_name = result.metadata.get("product_name")
            output_name = Path(result.output_path).name if result.output_path else None
            category = result.metadata.get("metrc_category")
            date = result.metadata.get("report_date")
            company = result.metadata.get("company_name")
            output_path = result.output_path
            if output_path and Path(output_path).exists():
                text = Path(output_path).read_text(encoding="utf-8")
                self.output_text_view.setPlainText(text)
                self.output_visual.display(result, text)
                msg = f"Parsed {Path(self.selected_file).name} as {result.format_name}"
            else:
                self.output_text_view.setPlainText("Output file not found.")
                self.output_visual.display(result, "")
                msg = f"Parsed {Path(self.selected_file).name} as {result.format_name} (no output file)"
            self.label.setText(msg)
            self._update_list_item(self.selected_file, product_name, output_name, category, date, company)
        except Exception as exc:
            self._update_list_item(self.selected_file, None, None)
            QMessageBox.critical(self, "Parse failed", str(exc))

        self._load_pdf(self.selected_file)

    def _zoom_in(self) -> None:
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(self.pdf_view.zoomFactor() * 1.25)
        self._update_zoom_label()

    def _zoom_out(self) -> None:
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(self.pdf_view.zoomFactor() / 1.25)
        self._update_zoom_label()

    def _zoom_fit(self) -> None:
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        mode = self.pdf_view.zoomMode()
        if mode == QPdfView.ZoomMode.FitToWidth:
            self._zoom_label.setText("Fit")
        else:
            pct = int(self.pdf_view.zoomFactor() * 100)
            self._zoom_label.setText(f"{pct}%")

    def _load_pdf(self, path: str) -> None:
        pdf_path = Path(path)
        if not pdf_path.exists():
            self.pdf_view.setDocument(None)
            return
        self._pdf_document.close()
        self._pdf_document.load(str(pdf_path))
        self.pdf_view.setDocument(self._pdf_document)
        self._zoom_fit()

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

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
                self._parse_and_display()

    # ------------------------------------------------------------------
    # Select file button
    # ------------------------------------------------------------------

    def select_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select COA File", filter="PDF Files (*.pdf)"
        )
        if file_name:
            self.selected_file = file_name
            self.label.setText(f"Selected: {Path(file_name).name}")
            self._parse_and_display()

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def select_batch_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing PDFs")
        if not folder:
            folder = str(INPUT_DIR)
        input_dir = Path(folder)
        pdf_count = len(list(input_dir.glob("*.pdf")))
        if pdf_count == 0:
            QMessageBox.information(self, "No PDFs found", f"No PDF files found in:\n{folder}")
            return
        self._run_batch(input_dir, pdf_count)

    def _run_batch(self, input_dir: Path, pdf_count: int) -> None:
        output_dir = Path("Output")

        self.output_text_view.setPlainText("")
        self.output_text_view.appendPlainText(f"Starting batch: {pdf_count} PDF(s) from {input_dir.name}/")
        self.output_tabs.setCurrentIndex(1)
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
        self.output_text_view.appendPlainText(f"[{current}/{total}] {filename}")
        self.output_text_view.verticalScrollBar().setValue(
            self.output_text_view.verticalScrollBar().maximum()
        )

    def _on_batch_finished(self, summary_lines: list) -> None:
        self.progress_bar.setVisible(False)
        self.batch_button.setEnabled(True)
        self.output_text_view.appendPlainText("")
        for line in summary_lines:
            self.output_text_view.appendPlainText(line)
        self.label.setText("Batch complete. Summary saved to Output/batch_summary.json")
        # Don't clear the list — just re-preload to update names
        self._start_preload()
        if self.file_list.count() > 0:
            self.file_list.setCurrentRow(0)


def _open_file_location(path: str) -> None:
    path_obj = Path(path)
    if not path_obj.exists():
        QMessageBox.warning(None, "File Not Found", f"File not found:\n{path}")
        return
    try:
        subprocess.Popen(["explorer", "/select,", str(path_obj.resolve())])
    except Exception as exc:
        QMessageBox.critical(None, "Error", f"Could not open file location:\n{exc}")
