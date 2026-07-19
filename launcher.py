import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_python() -> str | None:
    candidates = []
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


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    python_exe = find_python()
    if not python_exe:
        print("Python interpreter not found.")
        return 1

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "windows")
    env.setdefault("PYTHONUTF8", "1")

    if os.name == "nt" and "pythonw.exe" in python_exe.lower():
        cmd = [python_exe, str(project_dir / "app.py")]
    elif os.name == "nt" and python_exe.lower().endswith("py.exe"):
        cmd = [python_exe, "-3", str(project_dir / "app.py")]
    else:
        cmd = [python_exe, str(project_dir / "app.py")]

    return subprocess.call(cmd, cwd=str(project_dir), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
