"""Command-line entry point for instantdemo.

Subcommand layout:

    instantdemo --version
    instantdemo --help

    instantdemo generate
        --url URL                      (required)
        [--source PATH]                (default: cwd)
        [--describe TEXT]              (optional flow description)
        [--tts {kokoro,google,...}]    (default: kokoro)
        [--output PATH]                (default: demo.mp4 in source)
        [--from-phase N]               (resume from phase N)
        [--no-edit]                    (skip $EDITOR checkpoints)

    instantdemo phase {1..5}
        [--source PATH] [other generate flags as needed]

    instantdemo render <forwarded args>
        (delegates entirely to instantdemo.render.main())

The `render` subcommand is pre-routed before argparse sees its flags so
that `instantdemo render --help` shows the renderer's own help text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from instantdemo import __version__
from . import checkpoints, state
from .phases import (
    Context,
    PHASES,
    phase_name_from_number,
)


TTS_CHOICES = ("kokoro", "google", "elevenlabs", "piper")


def _resolve_context(args: argparse.Namespace) -> Context:
    """Build a Context from parsed CLI args."""
    source = Path(args.source).resolve() if args.source else Path.cwd()
    state_dir = source / ".instantdemo"
    if args.output:
        output = Path(args.output).resolve()
    else:
        output = source / "demo.mp4"
    return Context(
        url=args.url,
        source=source,
        describe=args.describe,
        state_dir=state_dir,
        output=output,
        tts=args.tts,
        no_edit=args.no_edit,
    )


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Flags shared between `generate` and `phase`."""
    parser.add_argument(
        "--url",
        required=True,
        help="URL of the running app to demo (e.g. http://localhost:3000)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Path to the codebase (default: current directory)",
    )
    parser.add_argument(
        "--describe",
        default=None,
        help="What to demo (free-form description, optional)",
    )
    parser.add_argument(
        "--tts",
        choices=TTS_CHOICES,
        default="kokoro",
        help="TTS provider for the render step (default: kokoro)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Final MP4 path (default: <source>/demo.mp4)",
    )
    parser.add_argument(
        "--no-edit",
        action="store_true",
        help="Skip $EDITOR checkpoints between phases",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="instantdemo",
        description="Generate narrated demo videos of web applications.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  generate  Run all 5 phases end-to-end (analyze → render)\n"
            "  phase N   Run a single phase by number (1..5)\n"
            "  render    Render an MP4 from a demo-script.json\n"
            "  serve     Start the GUI server (requires `instantdemo[gui]`)\n"
            "\n"
            "Use `instantdemo <subcommand> --help` for subcommand flags.\n"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"instantdemo {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # generate
    generate = subparsers.add_parser(
        "generate",
        help="Run the full 5-phase workflow end-to-end",
        description="Run all 5 phases end-to-end with optional $EDITOR checkpoints.",
    )
    _add_common_flags(generate)
    generate.add_argument(
        "--from-phase",
        type=int,
        choices=range(1, len(PHASES) + 1),
        default=1,
        metavar="N",
        help="Resume from phase N (1..5). Earlier phases must already have artifacts.",
    )

    # phase
    phase = subparsers.add_parser(
        "phase",
        help="Run a single phase by number (1..5)",
        description="Run a single phase. Useful for debugging and dev iteration.",
    )
    phase.add_argument(
        "number",
        type=int,
        choices=range(1, len(PHASES) + 1),
        metavar="N",
        help="Phase number (1..5)",
    )
    _add_common_flags(phase)

    # serve (GUI)
    serve = subparsers.add_parser(
        "serve",
        help="Start the GUI server (requires `instantdemo[gui]`)",
        description="Start the GUI on http://127.0.0.1:8765",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind (default: 8765)",
    )
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload on code changes (development only)",
    )
    serve.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Project directory to serve (default: current directory)",
    )
    serve.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open the browser automatically",
    )

    return parser


def _import_phase_runner(number: int):
    """Lazy-import the phase module's run() so a missing optional dep
    doesn't blow up the whole CLI at startup."""
    name = phase_name_from_number(number)
    if name == "analyze":
        from .phases import analyze
        return analyze.run
    if name == "narrate":
        from .phases import narrate
        return narrate.run
    if name == "gather":
        from .phases import gather
        return gather.run
    if name == "script":
        from .phases import script
        return script.run
    if name == "validate":
        from .phases import validate
        return validate.run
    raise AssertionError(f"unreachable: phase {name}")  # pragma: no cover


# Phase 5 invokes the renderer; there's nothing to review afterwards.
# The pre-render review (when real Phase 5 lands) happens inside the
# phase itself, between validation and the render call.
PHASES_WITH_REVIEW = (1, 2, 3, 4)


async def _run_phase(number: int, context: Context) -> None:
    name = phase_name_from_number(number)
    print(f"\n=== Phase {number}: {name} ===")
    runner = _import_phase_runner(number)
    with state.phase_run(context.state_dir, number):
        await runner(context)
    if number in PHASES_WITH_REVIEW:
        artifact = context.phase_artifact(number)
        checkpoints.review(artifact, no_edit=context.no_edit)


def _init_state(context: Context) -> None:
    """Ensure state.json exists and records the run-level inputs."""
    context.state_dir.mkdir(parents=True, exist_ok=True)
    s = state.load(context.state_dir)
    state.update_inputs(s, url=context.url, describe=context.describe)
    state.save(context.state_dir, s)


async def _run_phases_with_client(
    context: Context, phase_numbers: list[int]
) -> None:
    """Connect a single ClaudeSDKClient and run the requested phases
    sequentially against it. Cold-start cost is paid once at connect()
    instead of per-phase, and per-phase tool allowlists are preserved
    via the PreToolUse hook dispatcher set up in agent_client."""
    from .agent_client import make_agent_client

    client, dispatcher = make_agent_client(cwd=str(context.source))
    await client.connect()
    context.client = client
    context.dispatcher = dispatcher
    try:
        for n in phase_numbers:
            await _run_phase(n, context)
    finally:
        try:
            await client.disconnect()
        finally:
            context.client = None
            context.dispatcher = None


def cmd_generate(args: argparse.Namespace) -> int:
    import asyncio

    context = _resolve_context(args)
    _init_state(context)
    phase_numbers = list(range(args.from_phase, len(PHASES) + 1))
    asyncio.run(_run_phases_with_client(context, phase_numbers))
    print("\nDone.")
    return 0


def cmd_phase(args: argparse.Namespace) -> int:
    import asyncio

    context = _resolve_context(args)
    _init_state(context)
    asyncio.run(_run_phases_with_client(context, [args.number]))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import os
        import threading
        import time
        import webbrowser
        import uvicorn
    except ImportError:
        print(
            "Error: GUI dependencies not installed. Install with:\n"
            "  pip install 'instantdemo[gui]'",
            file=sys.stderr,
        )
        return 1
    if args.project is not None:
        project_path = Path(args.project).resolve()
        if not project_path.is_dir():
            print(f"Error: --project path is not a directory: {project_path}", file=sys.stderr)
            return 1
        os.environ["INSTANTDEMO_PROJECT_DIR"] = str(project_path)
        print(f"Project directory: {project_path}")
    url = f"http://{args.host}:{args.port}"
    print(f"InstantDemo GUI: {url}")
    if not args.no_open and not args.reload:
        # Defer the open() call so uvicorn has time to bind the port.
        # Skipped under --reload because the worker restarts repeatedly.
        def _open_later() -> None:
            time.sleep(1.0)
            try:
                webbrowser.open(url)
            except Exception:  # pragma: no cover
                pass
        threading.Thread(target=_open_later, daemon=True).start()
    uvicorn.run(
        "instantdemo.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else list(argv)

    # Pre-route `render` before argparse claims --help / -h. The
    # render subcommand owns its own argparse via instantdemo.render.main().
    if raw_args and raw_args[0] == "render":
        from .render import main as render_main
        render_main(raw_args[1:])
        return 0

    parser = build_parser()
    args = parser.parse_args(raw_args)

    try:
        if args.command == "generate":
            return cmd_generate(args)
        if args.command == "phase":
            return cmd_phase(args)
        if args.command == "serve":
            return cmd_serve(args)
    except RuntimeError as e:
        # Phase runners raise RuntimeError for known user-facing issues
        # (e.g. missing prior-phase artifact). Print without the traceback.
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
