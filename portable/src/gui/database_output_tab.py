import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.database_output import (
    create_database_zip,
    default_database_name,
    find_output_files,
)

logger = logging.getLogger("coa_parser")

OUTPUT_DIR = Path("Output")


class DatabaseOutputTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("Database Output")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel(
            "Combine every parsed text output in the Output folder into a "
            "single compressed .zip file."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555;")
        layout.addWidget(desc)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(QLabel("File name:"))
        self._name_edit = QLineEdit(default_database_name())
        self._name_edit.setMinimumWidth(260)
        name_row.addWidget(self._name_edit, stretch=1)
        layout.addLayout(name_row)

        self._file_count_label = QLabel()
        self._file_count_label.setStyleSheet("color: #555;")
        layout.addWidget(self._file_count_label)

        self._create_btn = QPushButton("Create Database Output")
        self._create_btn.setStyleSheet(
            "background: #27ae60; color: #fff; font-weight: 600; padding: 6px 16px;"
        )
        self._create_btn.clicked.connect(self._create_zip)
        layout.addWidget(self._create_btn)

        layout.addStretch()

        self._refresh_file_count()

    def _refresh_file_count(self) -> None:
        files = find_output_files(OUTPUT_DIR)
        self._file_count_label.setText(
            f"{len(files)} text output(s) found in the Output folder."
        )

    def _create_zip(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a file name.")
            return

        files = find_output_files(OUTPUT_DIR)
        if not files:
            QMessageBox.information(
                self, "No Outputs", "No text outputs found in the Output folder."
            )
            return

        default_path = str((Path.cwd() / name).with_suffix(".zip"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Database Output", default_path, "ZIP Archive (*.zip)"
        )
        if not path:
            return

        try:
            count, final_path = create_database_zip(OUTPUT_DIR, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export Failed", f"Could not create ZIP:\n{exc}"
            )
            logger.error("Database ZIP export failed: %s", exc)
            return

        QMessageBox.information(
            self,
            "Export Complete",
            f"Created {final_path.name}\n{count} file(s) compressed.",
        )
