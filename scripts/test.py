import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent

_TARGET_FLAGS = {
    "--unit": "tests/unit",
    "--integration": "tests/integration",
}


def build_command(args: list[str]) -> list[str]:
    targets = [_TARGET_FLAGS[flag] for flag in args if flag in _TARGET_FLAGS]
    passthrough = [arg for arg in args if arg not in _TARGET_FLAGS]

    if not targets:
        targets = ["tests"]

    return [sys.executable, "-m", "pytest", *targets, *passthrough]


def main() -> int:
    cmd = build_command(sys.argv[1:])
    print(f"$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=project_root)


if __name__ == "__main__":
    sys.exit(main())
