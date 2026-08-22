import runpy
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _clean_pycache(root: Path) -> None:
    for cache_dir in root.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


def _available_scripts() -> list[str]:
    return sorted(path.stem for path in SCRIPTS_DIR.glob("*.py"))


def run_script(name: str, args: list[str]) -> None:
    """Run `scripts/<name>.py` with `args` as sys.argv, accepting the name with or without a `.py` suffix."""
    stem = name[:-3] if name.endswith(".py") else name
    script_path = SCRIPTS_DIR / f"{stem}.py"

    if not script_path.is_file():
        print(f"Script not found: {script_path}", file=sys.stderr)
        available = _available_scripts()
        if available:
            print(f"Available scripts: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    sys.argv = [str(script_path), *args]
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    finally:
        _clean_pycache(PROJECT_ROOT)


def main() -> None:
    """Entry point for the `tm` console script: `tm <script>[.py] [args...]`."""
    argv = sys.argv[1:]
    if not argv:
        print("Usage: tm <script>[.py] [args...]", file=sys.stderr)
        available = _available_scripts()
        if available:
            print(f"Available scripts: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    run_script(argv[0], argv[1:])


if __name__ == "__main__":
    main()
