from pathlib import Path
import subprocess
import sys


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    output_dir = project_dir / "installer"
    output_dir.mkdir(exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "COAParserInstaller",
        "--onefile",
        "--windowed",
        "--distpath",
        str(output_dir),
        "--workpath",
        str(project_dir / "build_installer"),
        "--specpath",
        str(project_dir),
        "build_exe.py",
    ]
    subprocess.run(command, check=True, cwd=project_dir)


if __name__ == "__main__":
    main()
