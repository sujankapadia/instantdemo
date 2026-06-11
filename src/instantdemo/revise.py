"""The whole-demo style/pace pass (M4): validation + application
logic for the one revision kind that beats direct editing — an
instruction about everything ("less jargon", "slower") interpreted
into concrete narration/pacing changes.

No classifier ceremony: there is exactly one target (the whole
film), so a single structured interpretation suffices. The SDK call
and HTTP shape live in server/routes/revise.py; this module is the
pure, unit-tested core.
"""

from __future__ import annotations

from typing import Any

KINDS = ("rewrite", "pace", "voice", "structural", "unclear")

# Display-text hygiene: narration is spoken verbatim and shown as
# captions — markup of any kind is a contract violation.
_MARKUP_TOKENS = ("```", "<", "**", "##")

PACE_MIN, PACE_MAX = 0.6, 1.5


def validate_style_payload(
    payload: dict[str, Any], *, segment_count: int
) -> list[str]:
    """run_structured_query validator: returns problems (empty =
    valid). Enforces one-kind semantics and display-text rules."""
    problems: list[str] = []
    kind = payload.get("kind")
    if kind not in KINDS:
        problems.append(f"'kind' must be one of {KINDS}, got {kind!r}")
        return problems

    explanation = payload.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        problems.append("'explanation' must be a non-empty string")

    rewrites = payload.get("rewrites")
    if kind == "rewrite":
        if not isinstance(rewrites, dict) or not rewrites:
            problems.append("kind=rewrite requires a non-empty 'rewrites' map")
        else:
            for key, text in rewrites.items():
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    problems.append(f"rewrites key {key!r} is not an integer")
                    continue
                if not (1 <= idx <= segment_count):
                    problems.append(
                        f"rewrites index {idx} out of range (1..{segment_count})"
                    )
                if not isinstance(text, str) or not text.strip():
                    problems.append(f"rewrites[{key}] must be non-empty text")
                elif any(tok in text for tok in _MARKUP_TOKENS) or (
                    text.lstrip().startswith(("#", "-", "*"))
                ):
                    problems.append(
                        f"rewrites[{key}] contains markup — narration must "
                        "be plain spoken text"
                    )
    elif rewrites:
        problems.append(f"kind={kind} must not carry 'rewrites'")

    factor = payload.get("pace_factor")
    if kind == "pace":
        if not isinstance(factor, (int, float)):
            problems.append("kind=pace requires a numeric 'pace_factor'")
        elif not (PACE_MIN <= float(factor) <= PACE_MAX) or factor == 1:
            problems.append(
                f"'pace_factor' must be within {PACE_MIN}-{PACE_MAX} and not 1"
            )
    elif factor not in (None, 0):
        problems.append(f"kind={kind} must not carry 'pace_factor'")

    if kind == "voice" and not (payload.get("suggestion") or "").strip():
        problems.append("kind=voice requires a 'suggestion'")

    return problems


def apply_rewrites(
    segments: list[dict[str, Any]], rewrites: dict[str, str]
) -> list[int]:
    """Mutate segments' narration in place; return 0-based indices
    changed (sorted)."""
    changed: list[int] = []
    for key, text in rewrites.items():
        idx = int(key) - 1
        if segments[idx].get("narration") != text:
            segments[idx]["narration"] = text
            changed.append(idx)
    return sorted(changed)


def apply_pace(
    segments: list[dict[str, Any]], factor: float
) -> list[int]:
    """Scale every segment's pause_after_ms in place; return 0-based
    indices whose pause actually changed."""
    changed: list[int] = []
    for i, seg in enumerate(segments):
        pause = seg.get("pause_after_ms")
        if isinstance(pause, (int, float)) and pause > 0:
            new = int(round(pause * factor))
            if new != pause:
                seg["pause_after_ms"] = new
                changed.append(i)
    return changed
