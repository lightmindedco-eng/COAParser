import os
import sys

from PySide6.QtWidgets import QApplication

from src.gui.main_window import MainWindow


def main() -> int:
    if os.name != "nt":
        if not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    app = QApplication(sys.argv)
    app.setApplicationName("COAParser")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
