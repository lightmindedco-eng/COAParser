import os
import shutil

TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def get_tesseract_path() -> str | None:
    candidates = [
        os.environ.get("TESSERACT_CMD"),
        os.environ.get("TESSERACT_PATH"),
        TESSERACT_DEFAULT,
        shutil.which("tesseract"),
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None
