import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_python(project_dir: Path) -> str | None:
    candidates: list[str] = []

    if os.name == "nt":
        candidates.extend(
            [
                str(project_dir / ".venv" / "Scripts" / "python.exe"),
                str(project_dir / "venv" / "Scripts" / "python.exe"),
                str(project_dir / "python.exe"),
                str(project_dir / "python3.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                str(project_dir / ".venv" / "bin" / "python"),
                str(project_dir / "venv" / "bin" / "python"),
            ]
        )

    if sys.executable:
        candidates.append(sys.executable)
    if os.environ.get("PYTHON"):
        candidates.append(os.environ["PYTHON"])

    if os.name == "nt":
        candidates.extend(["py.exe", "python.exe", "pythonw.exe", "python3.exe"])
    else:
        candidates.extend(["python3", "python"])

    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isabs(candidate):
            path = Path(candidate)
            if path.exists():
                return str(path)
        else:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

    return None


def build_python_cmd(python_exe: str, *args: str) -> list[str]:
    if os.name == "nt" and python_exe.lower().endswith("py.exe"):
        return [python_exe, "-3", *args]
    return [python_exe, *args]


def pyside6_available(python_exe: str) -> bool:
    check_cmd = build_python_cmd(python_exe, "-c", "import PySide6")
    result = subprocess.run(check_cmd, capture_output=True, text=True)
    return result.returncode == 0


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    python_exe = find_python(project_dir)
    if not python_exe:
        print("Python interpreter not found.")
        return 1

    if not pyside6_available(python_exe):
        print(f"PySide6 is not available in: {python_exe}")
        print("Install dependencies with:")
        if os.name == "nt":
            print(r"  .\.venv\Scripts\python.exe -m pip install -r requirements.txt")
        else:
            print("  ./.venv/bin/python -m pip install -r requirements.txt")
        return 2

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "windows")
    env.setdefault("PYTHONUTF8", "1")

    cmd = build_python_cmd(python_exe, str(project_dir / "app.py"))

    return subprocess.call(cmd, cwd=str(project_dir), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
