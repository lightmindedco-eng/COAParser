from pathlib import Path
import subprocess
import sys


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    icon_path = project_dir / "icon.ico"
    portable_dir = project_dir / "dist" / "portable"
    portable_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "COAParserPortable",
        "--onedir",
        "--windowed",
        "--clean",
        "--icon",
        str(icon_path),
        "--distpath",
        str(portable_dir),
        "--workpath",
        str(project_dir / "build"),
        "--specpath",
        str(project_dir),
        "app.py",
    ]
    subprocess.run(command, check=True, cwd=project_dir)


if __name__ == "__main__":
    main()
