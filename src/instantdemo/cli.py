"""Command-line entry point for instantdemo."""

from __future__ import annotations

import argparse
import sys

from instantdemo import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="instantdemo",
        description="Generate narrated demo videos of web applications.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"instantdemo {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    # No subcommand yet — subcommands land in Task #8.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
