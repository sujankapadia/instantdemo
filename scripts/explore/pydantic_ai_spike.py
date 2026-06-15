"""Throwaway spike — Pydantic AI portability (AGENT_SDK_PORTABILITY.md).

Reproduces ONE Phase-4-shaped task with Pydantic AI, standalone (does
NOT touch the pipeline): the agent must write and run a Playwright
verification script through a *jailed* bash tool, then return findings
that validate against a schema. This exercises the two load-bearing
mechanics the port depends on —

  1. agentic Playwright-via-jailed-bash (a WrapperToolset.call_tool
     intercept = the PreToolUse-hook analog; FilteredToolset = the
     per-phase allowlist),
  2. structured output with retry (output_type + output_validator that
     raises ModelRetry),

— and measures script-success / JSON-validity / tokens / latency so a
cheap candidate model can later be A/B'd against the Claude baseline by
swapping --model. Needs the Evernote fixture app running on :8001.

Run (native Anthropic baseline):
  ANTHROPIC_API_KEY=... python scripts/explore/pydantic_ai_spike.py \
      --model anthropic:claude-sonnet-4-6 --runs 3

Candidate models via OpenRouter (one key, many models):
  OPENROUTER_API_KEY=... python scripts/explore/pydantic_ai_spike.py \
      --model openrouter:openai/gpt-4o-mini --runs 10
  ...  --model openrouter:google/gemini-2.0-flash-001
  ...  --model openrouter:qwen/qwen-2.5-coder-32b-instruct
  ...  --model openrouter:deepseek/deepseek-chat
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import (
    Agent,
    FilteredToolset,
    FunctionToolset,
    ModelRetry,
    RunContext,
    WrapperToolset,
)

# Load the repo-root .env into os.environ (pydantic-ai's providers read
# keys from the environment). python-dotenv handles quoting/export/etc.;
# override=False keeps any real env var ahead of the file. Needs
# `pip install python-dotenv`. The repo's .gitignore keeps .env out of git.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

APP_URL = "http://localhost:8001"

# The scene under verification — the exact select_option reset scene
# from the M8 L5 (known ground truth: selecting export-3 makes the
# count pill read "100 notes").
SCENE = {
    "action": "select_option",
    "selector": "#source-select",
    "value": "evernote-skapadia-export-3.enex",
    "expect": "#note-count should read '100 notes'",
}
GROUND_TRUTH_COUNT = "100"


# ── structured output (output_type) ──────────────────────────────────
class Findings(BaseModel):
    status: Literal["PASS", "FAIL"] = Field(
        description="PASS if the scene verified against the live app"
    )
    selector_resolved: bool = Field(
        description="Did #source-select resolve and accept the value?"
    )
    observed_count: str = Field(
        description="The exact text the count pill showed, e.g. '100 notes'"
    )
    reason: str = Field(description="One sentence of evidence")


# ── the bash tool, in a FunctionToolset ──────────────────────────────
def make_toolset(jail_dir: Path) -> FunctionToolset:
    toolset = FunctionToolset()

    @toolset.tool
    def bash(ctx: RunContext, command: str) -> str:
        """Run a shell command in the sandbox dir. Use it to write a
        Playwright script (heredoc) and run it with `python`. Returns
        combined stdout+stderr (truncated)."""
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(jail_dir),
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return out[-4000:] if len(out) > 4000 else out

    return toolset


# ── the jail: WrapperToolset.call_tool is the PreToolUse-hook analog ──
class Jail(WrapperToolset):
    """Intercept every tool call before execution — block paths that
    escape the sandbox or obviously destructive commands. This is the
    direct analog of the Claude Agent SDK's PreToolUse hook +
    filesystem jail."""

    def __init__(self, wrapped: Any, jail_dir: Path):
        super().__init__(wrapped)
        self._jail = str(jail_dir.resolve())
        self.blocked: list[str] = []

    async def call_tool(self, name, tool_args, ctx, tool):
        cmd = str(tool_args.get("command", ""))
        bad = (
            "rm -rf /" in cmd
            or "sudo" in cmd
            or ":(){" in cmd
            or "/etc/" in cmd
            or " ~/" in cmd
        )
        if bad:
            self.blocked.append(cmd[:80])
            raise ModelRetry(
                "Blocked by the sandbox: stay inside the working "
                "directory and don't touch the system."
            )
        return await super().call_tool(name, tool_args, ctx, tool)


def resolve_model(spec: str):
    """`anthropic:claude-...` (or any provider:model) passes through as a
    native pydantic-ai model string. `openrouter:<id>` routes through
    OpenRouter's OpenAI-compatible endpoint (one key, many models) —
    e.g. `openrouter:openai/gpt-4o-mini`."""
    if spec.startswith("openrouter:"):
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise SystemExit("OPENROUTER_API_KEY is not set.")
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        return OpenAIChatModel(
            spec.split(":", 1)[1], provider=OpenRouterProvider()
        )
    return spec


def build_agent(model: str, jail_dir: Path) -> tuple[Agent, Jail]:
    base = make_toolset(jail_dir)
    jail = Jail(base, jail_dir)
    # FilteredToolset = the per-phase allowlist (only `bash` is exposed).
    allowed = FilteredToolset(jail, lambda ctx, td: td.name == "bash")
    agent = Agent(
        resolve_model(model),
        output_type=Findings,
        retries=2,
        instructions=(
            "You verify one scene of a product demo against the LIVE web "
            f"app running at {APP_URL}. You have a `bash` tool in a "
            "sandbox directory. Write a SHORT Python Playwright script "
            "(sync API, headless chromium) to a file via bash heredoc, "
            "run it with `python`, and read its printed output. The "
            "script must: open the app, perform the action below, and "
            "print what the count pill shows. Then return findings.\n\n"
            f"Scene: {SCENE['action']} on `{SCENE['selector']}` "
            f"= '{SCENE['value']}'. Expectation: {SCENE['expect']}.\n"
            "Do not invent the observed count — read it from the page."
        ),
        toolsets=[allowed],
    )

    # output_validator: structured output + retry. Reject incoherent
    # findings (PASS must mean the selector resolved and a count was
    # read) — raising ModelRetry sends it back to the model.
    @agent.output_validator
    def _coherent(ctx: RunContext, out: Findings) -> Findings:
        if out.status == "PASS" and not out.selector_resolved:
            raise ModelRetry("PASS but selector_resolved is false — recheck.")
        if out.status == "PASS" and not out.observed_count.strip():
            raise ModelRetry("PASS but observed_count is empty — read the pill.")
        return out

    return agent, jail


def one_run(model: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="pai-spike-") as td:
        jail_dir = Path(td)
        agent, jail = build_agent(model, jail_dir)
        t0 = time.monotonic()
        err = None
        out: Findings | None = None
        try:
            result = agent.run_sync(
                "Verify the scene and return findings."
            )
            out = result.output
            usage = result.usage
        except Exception as e:  # noqa: BLE001 — spike: record any failure
            err = f"{type(e).__name__}: {e}"
            usage = None
        elapsed = time.monotonic() - t0

    # Score against ground truth.
    json_valid = out is not None
    correct = bool(
        out
        and out.status == "PASS"
        and GROUND_TRUTH_COUNT in out.observed_count
    )
    return {
        "json_valid": json_valid,
        "correct": correct,
        "observed": out.observed_count if out else None,
        "blocked": len(jail.blocked),
        "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
        "tool_calls": getattr(usage, "tool_calls", None) if usage else None,
        "secs": round(elapsed, 1),
        "error": err,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic:claude-sonnet-4-6")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    print(f"model={args.model}  runs={args.runs}  app={APP_URL}\n")
    rows = []
    for i in range(args.runs):
        r = one_run(args.model)
        rows.append(r)
        flag = "OK " if r["correct"] else ("JSON" if r["json_valid"] else "FAIL")
        print(
            f"  run {i + 1}: {flag}  observed={r['observed']!r}  "
            f"tok={r['input_tokens']}/{r['output_tokens']}  "
            f"tools={r['tool_calls']}  {r['secs']}s"
            + (f"  ERR {r['error']}" if r["error"] else "")
        )

    n = len(rows)
    correct = sum(r["correct"] for r in rows)
    json_ok = sum(r["json_valid"] for r in rows)
    out_tok = [r["output_tokens"] for r in rows if r["output_tokens"]]
    print(
        f"\nsummary: script-success {correct}/{n}  "
        f"json-valid {json_ok}/{n}  "
        f"avg-out-tokens {round(sum(out_tok) / len(out_tok)) if out_tok else '-'}"
    )


if __name__ == "__main__":
    main()
