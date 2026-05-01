"""Command-line entry point for instantdemo."""

from __future__ import annotations

import argparse
import sys

from instantdemo import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="instantdemo",
        description="Generate narrated demo videos of web applications.",
        epilog=(
            "Subcommands:\n"
            "  render  Render an MP4 from a demo-script.json (use "
            "`instantdemo render --help` for flags)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"instantdemo {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else list(argv)

    # Pre-route `render` before argparse claims --help / -h. The
    # render subcommand owns its own argparse via instantdemo.render.main().
    if raw_args and raw_args[0] == "render":
        from .render import main as render_main
        render_main(raw_args[1:])
        return 0

    parser = build_parser()
    parser.parse_args(raw_args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
