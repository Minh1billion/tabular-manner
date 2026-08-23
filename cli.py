import runpy
import shutil
import sys
from pathlib import Path

def _find_repo_root(marker: str = "pyproject.toml") -> Path:
    """Walk up from the current working directory to find the repo root.

    Resolves from cwd (where `tm` is invoked), not from this file's own
    location, because `scripts/` and this file are shipped as static copies
    inside the installed package (see force-include in pyproject.toml) and
    no longer live next to the actual dev checkout. `tm` is meant to be run
    from inside a cloned `tabular-manner` repo.
    """
    for p in [Path.cwd(), *Path.cwd().resolve().parents]:
        if (p / marker).exists():
            return p
    raise FileNotFoundError(
        f"Could not find '{marker}' above {Path.cwd()}. "
        "Run `tm` from inside a tabular-manner checkout."
    )

PROJECT_ROOT = _find_repo_root()
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
