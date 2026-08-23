from pathlib import Path

def find_repo_root(marker: str = "pyproject.toml") -> Path:
    """Walk up from this file to find the repo root (dev/scripts/tests use only)."""
    for p in Path(__file__).resolve().parents:
        if (p / marker).exists():
            return p
    raise FileNotFoundError(marker)

def samples_dir() -> Path:
    return find_repo_root() / "samples" / "json"

def default_storage_root() -> Path:
    return find_repo_root() / ".tm" / "resource_storage"
