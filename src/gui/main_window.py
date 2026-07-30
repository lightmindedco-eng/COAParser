from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QTabWidget

from src.gui.coa_parser_tab import COAParserTab
from src.gui.metrc_downloader_tab import METRCDownloaderTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("COA Parser")
        self.resize(1600, 1000)
        self.setMinimumSize(1200, 700)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.metrc_tab = METRCDownloaderTab()
        self.tabs.addTab(self.metrc_tab, "METRC Downloader")

        self.coa_tab = COAParserTab()
        self.tabs.addTab(self.coa_tab, "COA Parser")

        self.metrc_tab.pdf_downloaded.connect(self._on_pdf_downloaded)

    def _on_pdf_downloaded(self, path: str) -> None:
        self.coa_tab.refresh_file_list()
