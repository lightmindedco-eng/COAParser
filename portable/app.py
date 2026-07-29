import os
import sys

from PySide6.QtWidgets import QApplication

from src.core.logger import (
    install_exception_hook,
    install_qt_message_handler,
    setup_logger,
)
from src.gui.main_window import MainWindow


def main() -> int:
    # Initialize logging first
    logger = setup_logger()
    logger.info("COA Parser starting up")
    logger.debug("Python %s on %s (args: %s)", sys.version, sys.platform, sys.argv)

    # Install crash handlers
    install_exception_hook()
    install_qt_message_handler()

    if os.name != "nt":
        if not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    app = QApplication(sys.argv)
    app.setApplicationName("COAParser")

    window = MainWindow()
    window.show()

    logger.info("Application window shown, entering event loop")
    exit_code = app.exec()
    logger.info("Application exiting with code %d", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
