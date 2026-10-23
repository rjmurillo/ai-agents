"""Claude Code adapter for the routing benchmark live backend (issue #5426).

`_routing_live.LiveBackend` runs one harness CLI process per invocation. This
module supplies the three Claude pieces: the argv, the environment, and a
parser that turns `claude -p --output-format stream-json --verbose` output into
the facts an `Observation` needs. Observed on claude 2.1.309, 2026-10-23, and
recorded under `tests/eval/fixtures/harness_capability/claude-2.1.309/`.

Billing. The run must spend the operator's Claude subscription, never an API
key. `claude_routing_env` starts from `_durable_process.claude_env`, which drops
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and the
Bedrock, Vertex, and Foundry switches. The stream is the second check: the
`system/init` event carries `apiKeySource`, which read `none` on every
subscription run. Any other value, or a stream with no init event, is a harness
failure, so an API-billed run is never scored as a pass. The login lives under
`HOME`, so `HOME` stays in the environment. Nothing here reads, copies, or links
a credential file.

Permission mode. Workers need to edit files in the scenario workdir and run
Python checks, and nothing else. The argv uses `--restricted` with
`--permission-mode acceptEdits`, an explicit `--tools` list, an `--allowedTools`
list, and `--permission-prompts none`. Measured on 2.1.309: `--restricted`
refused a `Write` to `../outside.txt`, `acceptEdits` alone did not, and a
command outside the allowlist (`ls /`) was denied with no prompt.
`--restricted` also refuses `bypassPermissions`. Weaker than Codex
`-s workspace-write`: there is no OS sandbox, and an allowed `python3 -c` call
wrote `../outside2.txt` outside the workdir. The Claude
sandbox setting (`--settings` with `sandbox.enabled`) failed on the probe host
with `nested userns is capability-restricted`, so it is not used.

Ambient context. `--setting-sources ""` and `--restricted` drop user, project,
and local settings and their hooks. `--strict-mcp-config` with no MCP config
drops MCP servers. `--disable-slash-commands` drops skills.
`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` drops CLAUDE.md and rules discovery, and
`--no-session-persistence` writes no transcript. An audit run on 2.1.309 listed
CLAUDE.md, rules, memory, skills, and hooks as absent. Not isolated: the
built-in system prompt, and the account email and display name that the
`userEmail` and `gitStatus` reminders carry. Setting `GIT_CONFIG_GLOBAL` to
`/dev/null` did not remove the name, so the name comes from the login, not git.

Effort. The stream names no reasoning effort. `system/init` carries only
`per_turn_effort_active`, and a debug log of the same run named none. This
adapter therefore never reports an observed effort, so the runner records the
requested effort as `UNVERIFIED`, never as honored.

Token convention, matching `_durable_codex.parse_codex_run`: `input_tokens` is
the prompt tokens that were not read from the cache, `cache_read_tokens` is the
cached part, and the two do not overlap. Anthropic usage already excludes cache
reads from `input_tokens`, so the uncached figure is `input_tokens` plus
`cache_creation_input_tokens`. `output_tokens` includes thinking tokens, as the
API bills them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from _capability_probes import TRUSTED_REQUEST_TEMPLATES
from _durable_process import claude_env

#: Tools that exist in a worker session. Excludes `Agent`, so every process is
#: a single agent and the runner owns all fan-out.
CLAUDE_TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
#: Tools pre-approved. Bash is limited to Python, so a check can run and a
#: shell escape cannot. Mirrors `_durable_process.ALLOWED_TOOLS`.
CLAUDE_ALLOWED_TOOLS = (
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    "Bash(python:*)",
    "Bash(python3:*)",
)
CLAUDE_SANDBOX_LABEL = "claude:--restricted acceptEdits"
SUBSCRIPTION_KEY_SOURCE = "none"
#: Recorded on every Claude result row: what the run could not isolate. Measured by an
#: audit run on 2.1.309 (2026-10-23) that listed each other source as absent.
CLAUDE_AMBIENT_HOME: Mapping[str, object] = {
    "claude_home": "real login, instruction files dropped",
    "isolated": [
        "CLAUDE.md and rules (CLAUDE_CODE_DISABLE_CLAUDE_MDS=1)",
        "user, project, and local settings and hooks (--setting-sources, --restricted)",
        "MCP servers (--strict-mcp-config)",
        "skills and slash commands (--disable-slash-commands)",
        "session transcript (--no-session-persistence)",
    ],
    "not_isolated": [
        "Claude Code built-in system prompt",
        "account email and display name, in the userEmail and gitStatus reminders",
        "Bash(python) can write outside the workdir: no OS sandbox",
    ],
}
_SYNTHETIC_MODEL = "<synthetic>"
_DETAIL_LIMIT = 500
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


def claude_routing_argv(model: str, effort: str, prompt: str) -> list[str]:
    """Shell-free argv for one `claude -p` invocation.

    The prompt follows `-p` directly, as in `_durable_process.claude_argv`,
    because `--allowedTools` is variadic and would swallow a later positional.
    A prompt that starts with `-` would parse as an option, so it is refused.
    """
    if not prompt or prompt.startswith("-"):
        raise ValueError("claude prompt must be non-empty and must not start with '-'")
    model_flag = TRUSTED_REQUEST_TEMPLATES[("claude", "model_override")]
    effort_flag = TRUSTED_REQUEST_TEMPLATES[("claude", "effort_override")]
    return [
        "claude",
        "-p",
        prompt,
        model_flag.flag,
        model_flag.render(model),
        effort_flag.flag,
        effort_flag.render(effort),
        "--permission-mode",
        "acceptEdits",
        "--restricted",
        "--tools",
        CLAUDE_TOOLS,
        "--allowedTools",
        *CLAUDE_ALLOWED_TOOLS,
        "--permission-prompts",
        "none",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def claude_routing_env() -> dict[str, str]:
    """Allowlisted environment that bills the subscription login.

    Different from `claude_env` only by `DISABLE_AUTOUPDATER`: the CLI replaced
    2.1.307 with 2.1.309 in the middle of the probe session, and a version that
    changes between rows would break the matrix pin. Billing variables stay
    removed because `claude_env` removes them.
    """
    env: dict[str, str] = claude_env()
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


@dataclass(frozen=True, slots=True)
class ClaudeRunFacts:
    """What one stream-json run reported. Effort is absent: the stream has none."""

    models: tuple[str, ...] = ()
    cli_version: str = ""
    api_key_source: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    completed: bool = False
    failure: str = ""


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _events(stdout: str) -> list[Mapping[str, Any]]:
    events: list[Mapping[str, Any]] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def clean_detail(text: str) -> str:
    """One line, control characters removed, capped. CLI text is provider-controlled."""
    flat = " ".join(_CONTROL_CHARS.sub(" ", text).split())
    return flat if len(flat) <= _DETAIL_LIMIT else flat[:_DETAIL_LIMIT] + "..."


def _models(events: list[Mapping[str, Any]]) -> tuple[str, ...]:
    """Distinct models the backend named on assistant messages, first-seen order."""
    seen: list[str] = []
    for event in events:
        message = event.get("message") if event.get("type") == "assistant" else None
        model = message.get("model") if isinstance(message, dict) else None
        if isinstance(model, str) and model != _SYNTHETIC_MODEL and model not in seen:
            seen.append(model)
    return tuple(seen)


def _failure(init: Mapping[str, Any] | None, result: Mapping[str, Any] | None, stderr: str) -> str:
    """Why the run is not a completed one, or an empty string."""
    if result is None:
        suffix = f": {clean_detail(stderr)}" if stderr.strip() else ""
        return "no result event in stream" + suffix
    source = None if init is None else init.get("apiKeySource")
    if source != SUBSCRIPTION_KEY_SOURCE:
        return (
            f"billing guard: init apiKeySource is {source!r}, expected "
            f"{SUBSCRIPTION_KEY_SOURCE!r} (subscription login)"
        )
    if result.get("is_error") is True:
        status = result.get("api_error_status")
        terminal = result.get("terminal_reason")
        text = clean_detail(str(result.get("result", "")))
        return f"claude error (api_error_status={status}, terminal_reason={terminal}): {text}"
    if result.get("subtype") != "success":
        return f"result subtype {result.get('subtype')}"
    return ""


def parse_claude_run(stdout: str, stderr: str = "") -> ClaudeRunFacts:
    """Fold one stream-json run into `ClaudeRunFacts`. A missing result is a failure.

    The last `result` event is cumulative, so it carries the run's usage.
    """
    events = _events(stdout)
    init = next(
        (e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None
    )
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    failure = _failure(init, result, stderr)
    raw = None if result is None else result.get("usage")
    usage: Mapping[str, Any] = raw if isinstance(raw, dict) else {}
    key_source = None if init is None else init.get("apiKeySource")
    return ClaudeRunFacts(
        models=_models(events),
        cli_version="" if init is None else str(init.get("claude_code_version", "")),
        api_key_source=key_source if isinstance(key_source, str) else None,
        input_tokens=_int(usage.get("input_tokens"))
        + _int(usage.get("cache_creation_input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
        completed=not failure,
        failure=failure,
    )
