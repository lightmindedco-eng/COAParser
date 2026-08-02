import logging
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core import firebase_sync
from src.core.database_output import (
    copy_images,
    create_database_zip,
    default_database_name,
    default_images_dir,
    find_image_files,
    find_output_files,
)

logger = logging.getLogger("coa_parser")

OUTPUT_DIR = Path("Output")


class _DeployWorker(QObject):
    output = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, command: str, project_dir: str) -> None:
        super().__init__()
        self._command = command
        self._project_dir = project_dir

    def run(self) -> None:
        try:
            proc = subprocess.Popen(
                self._command,
                cwd=self._project_dir,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            self.finished.emit(False, f"Could not start firebase: {exc}")
            return
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                if line.strip():
                    self.output.emit(line)
            proc.wait()
        finally:
            if proc.stdout:
                proc.stdout.close()
        if proc.returncode == 0:
            self.finished.emit(True, "Images deployed to Firebase Hosting.")
        else:
            self.finished.emit(
                False, f"firebase deploy failed (exit code {proc.returncode})."
            )


class _PublishWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def __init__(self, service_account: str, output_dir: str, collection: str) -> None:
        super().__init__()
        self._service_account = service_account
        self._output_dir = output_dir
        self._collection = collection

    def run(self) -> None:
        try:
            result = firebase_sync.publish_to_catalog(
                self._service_account,
                self._output_dir,
                self._collection,
                on_progress=lambda done, total, msg: self.progress.emit(done, total, msg),
            )
        except firebase_sync.FirebaseSyncError as exc:
            self.finished.emit(False, str(exc))
            return
        except Exception as exc:
            logger.error("Publish to catalog failed: %s", exc)
            self.finished.emit(False, f"Publish failed: {exc}")
            return
        self.finished.emit(
            True,
            f"Published {result['published']} product(s) to the catalog "
            f"(collection '{result['collection']}').",
        )


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
            "single compressed .zip file, and copy the matching web images "
            "into the COAWeb images folder."
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

        self._deploy_check = QCheckBox(
            "Deploy images to Firebase Hosting after copying"
        )
        self._deploy_check.setChecked(True)
        layout.addWidget(self._deploy_check)

        self._deploy_status = QLabel()
        self._deploy_status.setStyleSheet("color: #555;")
        self._deploy_status.setWordWrap(True)
        self._deploy_status.hide()
        layout.addWidget(self._deploy_status)

        self._deploy_log = QPlainTextEdit()
        self._deploy_log.setReadOnly(True)
        self._deploy_log.setMaximumBlockCount(2000)
        self._deploy_log.setVisible(False)
        self._deploy_log.setMinimumHeight(120)
        layout.addWidget(self._deploy_log)

        catalog_title = QLabel("Firestore Catalog")
        catalog_title.setStyleSheet("font-weight: 600; color: #333;")
        layout.addWidget(catalog_title)

        sa_row = QHBoxLayout()
        sa_row.setSpacing(6)
        sa_row.addWidget(QLabel("Service account:"))
        self._sa_edit = QLineEdit()
        default_sa = firebase_sync.find_service_account_file()
        if default_sa:
            self._sa_edit.setText(str(default_sa))
        self._sa_edit.setPlaceholderText("Path to firebase-service-account.json")
        self._sa_edit.setMinimumWidth(280)
        sa_row.addWidget(self._sa_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_service_account)
        sa_row.addWidget(browse_btn)
        layout.addLayout(sa_row)

        self._publish_check = QCheckBox("Publish to Firestore catalog after copying")
        self._publish_check.setChecked(True)
        layout.addWidget(self._publish_check)

        self._publish_btn = QPushButton("Publish to Catalog Now")
        self._publish_btn.setStyleSheet("padding: 6px 16px;")
        self._publish_btn.clicked.connect(self._publish_now)
        layout.addWidget(self._publish_btn)

        layout.addStretch()

        self._refresh_file_count()

    def _refresh_file_count(self) -> None:
        txt = find_output_files(OUTPUT_DIR)
        images = find_image_files(OUTPUT_DIR)
        self._file_count_label.setText(
            f"{len(txt)} text output(s) and {len(images)} image(s) found in "
            f"the Output folder."
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
            copied, images_dir = copy_images(OUTPUT_DIR, default_images_dir())
        except OSError as exc:
            QMessageBox.critical(
                self, "Export Failed", f"Could not create database output:\n{exc}"
            )
            logger.error("Database output failed: %s", exc)
            return

        summary = (
            f"Created {final_path.name}\n"
            f"{count} text file(s) compressed.\n"
            f"{copied} image(s) copied to {images_dir}"
        )

        publish_wanted = copied > 0 and self._publish_check.isChecked()
        deploy_wanted = copied > 0 and self._deploy_check.isChecked()

        sa_path = self._sa_edit.text().strip()
        if publish_wanted and not sa_path:
            QMessageBox.warning(
                self,
                "Service Account Missing",
                summary
                + "\n\nTo publish to the catalog, add your Firebase service-account JSON "
                "(Firebase Console → Project settings → Service accounts → Generate new "
                "private key) and choose it below.",
            )
            publish_wanted = False

        firebase = self._find_firebase() if deploy_wanted else None
        if deploy_wanted and not firebase:
            QMessageBox.warning(
                self,
                "Firebase CLI Not Found",
                summary
                + "\n\nThe firebase CLI was not found on PATH. Install it with:\n"
                "npm install -g firebase-tools\n\n"
                "Then run 'firebase deploy --only hosting' in the COAWeb folder.",
            )
            deploy_wanted = False

        if not publish_wanted and not deploy_wanted:
            QMessageBox.information(
                self,
                "Export Complete",
                summary
                + "\nRun 'firebase deploy --only hosting' in COAWeb to publish new images.",
            )
            return

        if publish_wanted:
            self._pending_deploy = (firebase, images_dir) if deploy_wanted else None
            self._start_publish(sa_path, summary)
        else:
            self._start_deploy(firebase, images_dir, summary)

    @staticmethod
    def _find_firebase() -> str | None:
        firebase = shutil.which("firebase")
        if firebase:
            return firebase
        for base in (
            os.environ.get("APPDATA", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            candidate = Path(base) / "npm" / "firebase.cmd"
            if candidate.exists():
                return str(candidate)
        return None

    @staticmethod
    def _deploy_command(firebase_path: str) -> str:
        return f'"{firebase_path}" deploy --only hosting --non-interactive'

    def _start_deploy(
        self, firebase_path: str, images_dir: Path, summary: str
    ) -> None:
        self._last_export_summary = summary
        self._create_btn.setEnabled(False)
        self._publish_btn.setEnabled(False)
        self._deploy_log.clear()
        self._deploy_log.show()
        self._deploy_status.setText("Deploying images to Firebase Hosting...")
        self._deploy_status.show()

        project_dir = str(images_dir.parent)
        command = self._deploy_command(firebase_path)
        worker = _DeployWorker(command, project_dir)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.output.connect(self._on_deploy_output)
        worker.finished.connect(self._on_deploy_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._deploy_worker = worker
        self._deploy_thread = thread
        thread.start()

    def _on_deploy_output(self, line: str) -> None:
        self._deploy_log.appendPlainText(line)

    def _on_deploy_finished(self, ok: bool, message: str) -> None:
        self._create_btn.setEnabled(True)
        self._publish_btn.setEnabled(True)
        self._deploy_status.setText(message)
        summary = getattr(self, "_last_export_summary", "")
        if ok:
            QMessageBox.information(
                self,
                "Deploy Complete",
                f"{summary}\n\n{message}\n\n"
                "Check https://coa-catalog.web.app for the new images.",
            )
        else:
            QMessageBox.critical(
                self,
                "Deploy Failed",
                f"{summary}\n\n{message}\n\nSee the log above for details.",
            )

    def _browse_service_account(self) -> None:
        start = str(Path.cwd())
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Firebase Service Account", start, "JSON (*.json)"
        )
        if path:
            self._sa_edit.setText(path)

    def _publish_now(self) -> None:
        sa_path = self._sa_edit.text().strip()
        if not sa_path:
            QMessageBox.warning(
                self,
                "Service Account Missing",
                "Choose your Firebase service-account JSON first "
                "(Firebase Console → Project settings → Service accounts → "
                "Generate new private key).",
            )
            return
        self._start_publish(sa_path, None)

    def _start_publish(self, service_account: str, summary: str | None) -> None:
        self._last_export_summary = summary
        self._create_btn.setEnabled(False)
        self._publish_btn.setEnabled(False)
        self._deploy_log.clear()
        self._deploy_log.show()
        self._deploy_status.setText("Publishing to Firestore catalog...")
        self._deploy_status.show()

        worker = _PublishWorker(
            service_account, str(OUTPUT_DIR), firebase_sync.DEFAULT_COLLECTION
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_publish_progress)
        worker.finished.connect(self._on_publish_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._publish_worker = worker
        self._publish_thread = thread
        thread.start()

    def _on_publish_progress(self, done: int, total: int, message: str) -> None:
        self._deploy_status.setText(message)
        self._deploy_log.appendPlainText(message)

    def _on_publish_finished(self, ok: bool, message: str) -> None:
        self._deploy_status.setText(message)
        summary = getattr(self, "_last_export_summary", None)
        pending = getattr(self, "_pending_deploy", None)
        if ok and pending:
            firebase, images_dir = pending
            self._pending_deploy = None
            self._start_deploy(firebase, images_dir, summary or message)
            return
        self._create_btn.setEnabled(True)
        self._publish_btn.setEnabled(True)
        if ok:
            QMessageBox.information(
                self,
                "Publish Complete",
                (summary + "\n\n" if summary else "") + message,
            )
        else:
            QMessageBox.critical(self, "Publish Failed", message)
