import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.cli import run_script


def main():
    parser = argparse.ArgumentParser(
        description="Run a script from the scripts directory."
    )

    parser.add_argument(
        "-c",
        "--command",
        required=True,
        help="Script name to run, e.g. test",
    )

    args, remaining = parser.parse_known_args()

    run_script(args.command, remaining)


if __name__ == "__main__":
    main()
