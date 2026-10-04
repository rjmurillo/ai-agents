"""Codex harness adapter for the live durable-outcome driver (issue #5768).

`_durable_live.py` runs `claude -p`. This module supplies the three pieces a
`codex exec` run needs in its place: the argv, the environment, and a parser
that turns the run's output into the same `StreamFacts` the Claude parser
returns. Nothing else in the driver changes, so a Codex record and a Claude
record are built by one code path and grade on one corpus.

What each piece rests on (observed on codex-cli 0.157.1, 2026-10-03, and in
the committed fixtures under `tests/eval/fixtures/harness_capability/`):

* argv: `codex exec --json --skip-git-repo-check --ignore-user-config
  --ignore-rules --ephemeral -s workspace-write -m MODEL
  -c model_reasoning_effort=EFFORT -c developer_instructions=TEXT -- PROMPT`.
  `developer_instructions` is the Codex config key for text appended to the
  model's instructions; it plays the part of Claude's
  `--append-system-prompt-file`. The prompt is positional, as in `_codex_cli`.
* environment: an allowlisted copy of the caller's environment, with metered
  keys removed so the stored login bills. `CODEX_HOME` is left as the
  operator has it, so the CLI reads its own login. The driver never creates a
  link to, copy of, or read of any credential file. Ambient `~/.codex/AGENTS.md`
  and skills still load in every run, under both controls, so the control text
  is not the only instruction source; `--ignore-user-config` drops only
  `config.toml`. Read the reduced-control result with that constant in mind.
  `-s workspace-write` limits writes, not reads, so a model-generated command
  can read files outside the workspace. The Claude driver has the same limit.
* stdout (`--json`): `thread.started`, `turn.started`, `item.completed`,
  `turn.completed` with `usage`, and `turn.failed` or `error` on failure. It
  carries no model and no effort, which is why the model and effort come from
  stderr.
* stderr: with `RUST_LOG=tungstenite::protocol=trace` Codex writes the
  backend's websocket frames. `_codex_frames.response_spans` reads the model
  and reasoning effort the backend reported for each response. That is backend
  evidence, unlike the request flags.

Stricter than the Claude parser: a run with no `turn.completed` event is a
harness failure, and so is one carrying `turn.failed` or `error`. Codex has no
turn or budget limit exit to grade as a task outcome, so there is no
`limit_hit`.

Different from the Claude parser: Codex reports no cost, and no per-token
rate is published for the Codex models (`_eval_common` carries no row on
purpose, issue #3905), so `cost_usd` is `0.0` here and means "unavailable",
never "free". Compare Codex runs on tokens, not on cost per accepted task.
`input_tokens` is the Codex `input_tokens` less `cached_input_tokens`, and
`cache_read_tokens` is the cached part, so the two fields do not overlap.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from _claude_stream import StreamFacts
from _cli_transport import BASE_ENV_ALLOWLIST, minimal_process_env
from _codex_frames import CodexFrameError, parse_codex_frames, response_spans

CODEX_RUST_LOG = "tungstenite::protocol=trace"
#: Tool names the driver's `unapproved_actions` treats as allowed, keyed by the
#: Codex item type that does the same job.
_TOOL_NAME = {"command_execution": "Bash", "file_change": "Edit"}
_FAILURE_EVENTS = frozenset({"turn.failed", "error"})
_BLOCKED_BILLING_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"})
_ENV_ALLOWLIST = BASE_ENV_ALLOWLIST | {"CODEX_HOME"}


def _toml_string(text: str) -> str:
    """A TOML basic string for `text`. JSON escapes control characters but leaves DEL raw."""
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def codex_argv(model: str, effort: str, control_text: str, prompt: str) -> list[str]:
    """Shell-free argv for one `codex exec` run. The control text is a TOML string."""
    return [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "workspace-write",
        "-m",
        model,
        "-c",
        f"model_reasoning_effort={effort}",
        "-c",
        f"developer_instructions={_toml_string(control_text)}",
        "--",
        prompt,
    ]


def codex_env() -> dict[str, str]:
    """Allowlisted environment with backend frame logging. `CODEX_HOME` passes through."""
    env: dict[str, str] = minimal_process_env(
        allow=_ENV_ALLOWLIST,
        blocked=_BLOCKED_BILLING_ENV,
        overrides={"RUST_LOG": CODEX_RUST_LOG},
    )
    return env


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _events(stdout: str) -> list[Mapping[str, object]]:
    events: list[Mapping[str, object]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _item_failed(item: Mapping[str, object]) -> bool:
    exit_code = item.get("exit_code")
    nonzero = isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
    return nonzero or item.get("status") == "failed"


def _backend_models(stderr: str) -> tuple[str, ...]:
    try:
        spans = response_spans(parse_codex_frames(stderr))
    except CodexFrameError:
        return ()
    models: list[str] = []
    for span in spans:
        if span.model and span.model not in models:
            models.append(span.model)
    return tuple(models)


def backend_efforts(stderr: str) -> tuple[str, ...]:
    """Distinct reasoning efforts the backend reported, in first-seen order. Empty when none."""
    try:
        spans = response_spans(parse_codex_frames(stderr))
    except CodexFrameError:
        return ()
    efforts: list[str] = []
    for span in spans:
        if span.effort and span.effort not in efforts:
            efforts.append(span.effort)
    return tuple(efforts)


def parse_codex_run(stdout: str, stderr: str, cli_version: str = "") -> StreamFacts:
    """Fold one `codex exec --json` run and its stderr trace into `StreamFacts`."""
    events = _events(stdout)
    tools: list[str] = []
    tool_errors = 0
    final_text = ""
    usage = {"input": 0, "cached": 0, "output": 0}
    turns = 0
    failure = ""
    for event in events:
        kind = str(event.get("type", ""))
        if kind in _FAILURE_EVENTS and not failure:
            failure = kind
        elif kind == "turn.completed":
            turns += 1
            raw = event.get("usage")
            counts = raw if isinstance(raw, dict) else {}
            usage["input"] += _int(counts.get("input_tokens"))
            usage["cached"] += _int(counts.get("cached_input_tokens"))
            usage["output"] += _int(counts.get("output_tokens"))
        elif kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict):
                item_type = str(item.get("type", ""))
                if item_type == "agent_message":
                    final_text = str(item.get("text", ""))
                elif item_type not in ("reasoning", "error", "todo_list"):
                    tools.append(_TOOL_NAME.get(item_type, item_type))
                    tool_errors += 1 if _item_failed(item) else 0
    completed = turns > 0 and not failure
    return StreamFacts(
        models=_backend_models(stderr),
        efforts=backend_efforts(stderr),
        cli_version=cli_version,
        input_tokens=max(0, usage["input"] - usage["cached"]),
        output_tokens=usage["output"],
        cache_read_tokens=usage["cached"],
        turns=turns,
        tool_calls=tuple(tools),
        tool_errors=tool_errors,
        final_text=final_text,
        completed=completed,
        failure="" if completed else (failure or "no turn.completed event in stream"),
    )
