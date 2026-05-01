"""User checkpoints between phases.

After each artifact-producing phase, the CLI invites the user to review
and optionally edit the artifact. Behaviour depends on environment:

  - Interactive TTY + no --no-edit  → open $EDITOR on the artifact, block
    until the editor exits, then continue.
  - Interactive TTY + --no-edit     → print the artifact path and prompt
    "Press Enter to continue (Ctrl+C to abort)".
  - Non-TTY (CI, redirect, pipe)    → print the path and continue
    immediately. CI users should generally pair this with the planned
    `--auto` flag (Issue #1) for predictable behaviour.

Some phases embed an "answer block" at the top of their artifact for
inputs the next phase needs (e.g. which flow to demo, target tone).
`parse_answer_block()` extracts those after the user closes the editor.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

ANSWER_BLOCK_RE = re.compile(
    r"<!--\s*ANSWER\s+THESE\s+BEFORE\s+CONTINUING\s*-->\s*\n"
    r"(?P<body>.*?)"
    r"\n\s*<!--\s*/ANSWER\s*-->",
    re.DOTALL | re.IGNORECASE,
)


def parse_answer_block(text: str) -> dict[str, str]:
    """Extract `key: value` pairs from the artifact's answer block.

    Returns an empty dict if no block is present. Lines without a colon
    are ignored. Values are stripped of surrounding whitespace.
    """
    match = ANSWER_BLOCK_RE.search(text)
    if not match:
        return {}
    answers: dict[str, str] = {}
    for line in match.group("body").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        answers[key.strip()] = value.strip()
    return answers


def _resolve_editor() -> str | None:
    """Pick an editor: $EDITOR → $VISUAL → first available fallback."""
    for env_var in ("EDITOR", "VISUAL"):
        candidate = os.environ.get(env_var)
        if candidate:
            return candidate
    for fallback in ("nano", "vim", "vi"):
        if shutil.which(fallback):
            return fallback
    return None


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def review(artifact: Path, *, no_edit: bool) -> None:
    """Pause the CLI to let the user review (and optionally edit) `artifact`.

    Returns once the user is ready to continue.
    """
    if not artifact.exists():
        # Defensive — phase runners are responsible for writing the artifact.
        # If this fires, treat it as a programming error rather than a checkpoint.
        raise RuntimeError(f"Cannot checkpoint missing artifact: {artifact}")

    interactive = _is_interactive()
    editor = _resolve_editor() if (interactive and not no_edit) else None

    print(f"\n  Review: {artifact}")

    if editor is not None:
        # Auto-launch the editor and block on it.
        try:
            subprocess.run([editor, str(artifact)], check=True)  # nosec B603
        except subprocess.CalledProcessError as e:
            print(
                f"  Editor exited with status {e.returncode}. "
                "Continuing — re-run with --from-phase N to redo this phase.",
                file=sys.stderr,
            )
        return

    if interactive:
        # --no-edit on a TTY: just pause until the user is ready.
        try:
            input("  Press Enter to continue (Ctrl+C to abort)... ")
        except (EOFError, KeyboardInterrupt):
            print()
            raise
        return

    # Non-interactive: print the path and continue. The user can re-run
    # with --from-phase N if they want to revise.
    print("  (non-interactive: continuing without pause)")
