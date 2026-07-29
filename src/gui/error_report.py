from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


_REPORTS_FILE = Path("User_Reports.txt")


class ErrorReportDialog(QDialog):
    def __init__(self, input_path: str, output_path: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Submit Error Report")
        self.setMinimumSize(500, 350)

        self._input_path = input_path
        self._output_path = output_path

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel(f"Input:  {Path(input_path).name}"))
        if output_path:
            layout.addWidget(QLabel(f"Output: {Path(output_path).name}"))

        layout.addSpacing(8)
        layout.addWidget(QLabel("Describe the error:"))

        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText("What went wrong? Be as specific as possible...")
        layout.addWidget(self._text_edit, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self._submit)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(submit_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _submit(self) -> None:
        desc = self._text_edit.toPlainText().strip()
        if not desc:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "=== Error Report ===",
            f"Date:    {now}",
            f"Input:   {self._input_path}",
        ]
        if self._output_path:
            lines.append(f"Output:  {self._output_path}")
        lines.append("")
        lines.append("Description:")
        for paragraph in desc.split("\n"):
            lines.append(f"  {paragraph}")
        lines.append("")
        lines.append("=" * 18)
        lines.append("")

        _REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(str(_REPORTS_FILE), "a", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.accept()
