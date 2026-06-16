# test_agent_backend.py Spec

Source: `src/instantdemo/agent_backend.py` (M9 — the Pydantic AI agent
backend's tools + jail + per-phase allowlist; the SDK-shipped pieces
reimplemented).
Test: `tests/test_agent_backend.py`

## Methods not tested (and why)

| Method | Reason |
|---|---|
| `make_tools` / `build_phase_toolset` wiring through a live Agent | Needs a model; integration-tested when a phase is ported. The tool *bodies*, the jail *rule*, and the allowlist are unit-tested here. |
| `JailToolset.call_tool` interception end-to-end | Needs Pydantic AI's tool-call plumbing (ctx/tool); the *decision* it enforces (`_jail_violation`) is tested directly. |

## Tool bodies

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| AB1 | `tool_read` on a 3-line file | Returns 1-based numbered lines (`1\tfoo`); offset/limit window the output | Agents get mis-numbered/incomplete source — selectors land on wrong lines |
| AB2 | `tool_glob('*.py', cwd)` | Returns the matching files under cwd, files only | Phase 3 can't enumerate source — selector discovery blind |
| AB3 | `tool_grep` for a regex | Returns `file:line: text` for each match; capped | Phase 3's convention survey returns nothing |

## Jail + allowlist (the SDK-shipped safety, reimplemented)

| ID | Scenario | Assertion | Risk if broken |
|----|----------|-----------|----------------|
| AB4 | `phase_allows` for each phase | phase1 allows Bash/Read/Glob/Grep; phase3 allows Read/Glob/Grep but NOT Bash; phase2 allows nothing; unknown phase denies all | A phase gains a tool it shouldn't (e.g. phase 2 running Bash) or loses one it needs |
| AB5 | The jail rule (`_jail_violation`, as `JailToolset` uses it) | A Read whose `file_path` is outside `allowed_roots` is a violation; one inside is allowed; Bash is never a path violation | The agent reads/writes outside the project — the filesystem jail is the security boundary |
