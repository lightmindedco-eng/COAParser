"""Logging, crash reporting, and global exception hooks."""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOG_DIR = Path.home() / ".coa_parser"


def _ensure_log_dir() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def _log_file_path() -> Path:
    return _ensure_log_dir() / "coa_parser.log"


def _crash_dump_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _ensure_log_dir() / f"crash_{ts}.txt"


def setup_logger() -> logging.Logger:
    """Create a logger that writes to a rotating file and stdout."""
    logger = logging.getLogger("coa_parser")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Rotating file handler (5 MB max, 3 backups)
    log_path = _log_file_path()
    file_handler = RotatingFileHandler(
        str(log_path), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def log_exception(logger: logging.Logger | None = None) -> None:
    """Log the current exception with full traceback and write a crash dump."""
    if logger is None:
        logger = logging.getLogger("coa_parser")
    exc_info = sys.exc_info()
    tb_text = "".join(traceback.format_exception(*exc_info)) if exc_info and exc_info[0] else "No exception info"
    logger.critical("Unhandled exception:\n%s", tb_text)
    # Also write a crash dump to a separate file
    try:
        dump_path = _crash_dump_path()
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(f"COA Parser Crash Report\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
            f.write(f"Args: {sys.argv}\n")
            f.write(f"CWD: {os.getcwd()}\n")
            f.write(f"\nTraceback:\n{tb_text}\n")
        logger.info("Crash dump written to %s", dump_path)
    except Exception as e:
        logger.error("Failed to write crash dump: %s", e)


def install_exception_hook(logger: logging.Logger | None = None) -> None:
    """Install a global sys.excepthook that logs crashes before exiting."""
    if logger is None:
        logger = logging.getLogger("coa_parser")

    def _excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Unhandled exception (%s):\n%s", exc_type.__name__, tb_text)
        try:
            dump_path = _crash_dump_path()
            with open(dump_path, "w", encoding="utf-8") as f:
                f.write(f"COA Parser Crash Report\n")
                f.write(f"Time: {datetime.now().isoformat()}\n")
                f.write(f"Python: {sys.version}\n")
                f.write(f"Platform: {sys.platform}\n")
                f.write(f"Args: {sys.argv}\n")
                f.write(f"CWD: {os.getcwd()}\n")
                f.write(f"\nTraceback:\n{tb_text}\n")
            logger.info("Crash dump written to %s", dump_path)
        except Exception as e:
            logger.error("Failed to write crash dump: %s", e)
        # Call the original excepthook (usually prints to stderr)
        if hasattr(sys, "__excepthook__"):
            original = sys.__excepthook__
        else:
            original = None
        if original:
            original(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


def install_qt_message_handler(logger: logging.Logger | None = None) -> None:
    """Install a Qt message handler that forwards Qt messages to our logger."""
    if logger is None:
        logger = logging.getLogger("coa_parser")
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType

        def _qt_handler(msg_type, context, message):
            level = logging.WARNING
            if msg_type == QtMsgType.QtDebugMsg:
                level = logging.DEBUG
            elif msg_type == QtMsgType.QtInfoMsg:
                level = logging.INFO
            elif msg_type == QtMsgType.QtWarningMsg:
                level = logging.WARNING
            elif msg_type == QtMsgType.QtCriticalMsg:
                level = logging.ERROR
            elif msg_type == QtMsgType.QtFatalMsg:
                level = logging.CRITICAL
            logger.log(level, "Qt: %s (file: %s, line: %d, func: %s)",
                       message, context.file or "?", context.line or 0, context.function or "?")

        qInstallMessageHandler(_qt_handler)
    except ImportError:
        logger.debug("PySide6 not available, Qt message handler not installed")


def get_log_path() -> Path:
    return _log_file_path()


def get_crash_dump_dir() -> Path:
    return _ensure_log_dir()
