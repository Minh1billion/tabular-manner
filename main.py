import argparse

from tabular_manner.cli import run_script


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
