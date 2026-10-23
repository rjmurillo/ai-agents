"""Claude Code CLI run with one project skill installed, for the skill-routed arm.

Issue #6737. The `full` arm of `eval-rule-activation.py` pastes SKILL.md into
the system field of the text-eval envelope. That is not how Claude Code loads
a skill. The envelope also labels its content untrusted and tells the model to
use no tools, and in the 2026-10-23 run one full-arm response read the pasted
skill as a prompt injection and set it aside.

This module runs the CLI the way a user meets the skill. The skill directory
is copied under `.claude/skills/<name>/` in a fresh workspace, and
`--setting-sources project` lets the CLI discover it there. The user turn
invokes it as `/<name> <request>`, so the CLI expands the skill body itself.
The control runs the same argv in an empty workspace with the bare request.
No envelope wraps either turn, so the pair differs only by the skill.

Measured 2026-10-23 on claude 2.1.307 with claude-sonnet-5:
- The `system/init` event listed `spec` among the skills.
- A `/spec` turn reported 4,628 more input tokens than the same text without
  the prefix in the same workspace. SKILL.md is 13,408 bytes, about that size.
- With `--tools ""` the skill still expanded.
- A bare request in a workspace that held the skill did not invoke it, in 1 of
  1 probe. This arm measures a loaded skill, not whether the model routes to it.

Billing and isolation follow the `claude-cli` transport. The credential order,
the blocked metered variables, and the relocated config directory all come
from `_ClaudeCLIProvider`. Only project settings load, and the workspace holds
nothing but the copied skill. `--tools ""` leaves the model no tool to call.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _claude_cli import PROVIDER_LABEL, _ClaudeCLIProvider
from _claude_stream import parse_stream
from _cli_transport import run_cli, validate_timeout

__all__ = ["HarnessReply", "build_argv", "harness_prompt", "run_harness", "skill_name_error"]

#: A slash command name the CLI resolves. Anything else could carry text into
#: the user turn, so it is refused before a process starts.
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

_EMPTY_MCP_CONFIG = '{"mcpServers":{}}'


@dataclass(frozen=True, slots=True)
class HarnessReply:
    """What one harness run returned, plus the facts that show the skill loaded."""

    text: str
    model: str | None
    input_tokens_total: int
    output_tokens: int
    cli_version: str
    tool_calls: tuple[str, ...]
    invocation: str | None


def skill_name_error(name: str) -> str | None:
    """Return why `name` cannot be a slash command, or None when it can."""
    if _SKILL_NAME_RE.fullmatch(name):
        return None
    return f"skill name {name!r} is not a slash command name (lowercase letters, digits, hyphens)"


def harness_prompt(text: str, skill_name: str | None) -> str:
    """Return the user turn: the bare request, or the request behind `/<skill>`."""
    request = text.strip()
    if skill_name is None:
        return request
    error = skill_name_error(skill_name)
    if error is not None:
        raise ValueError(error)
    return f"/{skill_name} {request}"


def build_argv(executable: str, model: str) -> list[str]:
    """Build the shell-free argv. Both arms use it unchanged."""
    return [
        executable,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--mcp-config",
        _EMPTY_MCP_CONFIG,
        "--tools",
        "",
        "--no-session-persistence",
    ]


def _installer(skill_dir: Path, skill_name: str) -> Callable[[Path], None]:
    """Return a `run_cli` prepare hook that copies the skill into the workspace."""
    source = skill_dir.resolve()

    def _install(workspace: Path) -> None:
        target = workspace / ".claude" / "skills" / skill_name
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))

    return _install


def run_harness(
    text: str,
    *,
    model: str,
    skill_dir: Path | None,
    skill_name: str | None,
    executable: str = "claude",
    timeout: float = 900.0,
) -> HarnessReply:
    """Run one turn. With `skill_dir`, install that skill and invoke it by name.

    Raises RuntimeError on a failed process, an incomplete stream, an empty
    answer, or a served model outside the requested family.
    """
    if (skill_dir is None) != (skill_name is None):
        raise ValueError("skill_dir and skill_name are set together or not at all")
    if skill_dir is not None and not (skill_dir / "SKILL.md").is_file():
        raise ValueError(f"skill directory has no SKILL.md: {skill_dir}")
    prompt = harness_prompt(text, skill_name)
    provider = _ClaudeCLIProvider(executable=executable, timeout=validate_timeout(timeout))
    prepare = None if skill_dir is None or skill_name is None else _installer(skill_dir, skill_name)
    with tempfile.TemporaryDirectory(prefix="eval-claude-harness-") as profile:
        credential = provider._resolve_credential(executable)
        env = provider._build_env(Path(profile), credential)
        completed = run_cli(
            build_argv(executable, model),
            prompt,
            provider_label=PROVIDER_LABEL,
            env=env,
            timeout=validate_timeout(timeout),
            prepare=prepare,
        )
    facts = parse_stream(completed.stdout)
    if not facts.completed:
        raise RuntimeError(
            f"{PROVIDER_LABEL} harness run did not complete: "
            f"error={facts.failure or 'unknown'}; response redacted"
        )
    if not facts.final_text.strip():
        raise RuntimeError(f"{PROVIDER_LABEL} harness run returned no answer text")
    if not all(_ClaudeCLIProvider._model_matches(served, model) for served in facts.models):
        raise RuntimeError(
            f"{PROVIDER_LABEL} model attribution mismatch; model identifiers redacted"
        )
    served = sorted(facts.models, key=len, reverse=True)
    return HarnessReply(
        text=facts.final_text,
        model=served[0] if served else None,
        input_tokens_total=facts.input_tokens + facts.cache_read_tokens + facts.cache_write_tokens,
        output_tokens=facts.output_tokens,
        cli_version=facts.cli_version,
        tool_calls=facts.tool_calls,
        invocation=None if skill_name is None else f"/{skill_name}",
    )
