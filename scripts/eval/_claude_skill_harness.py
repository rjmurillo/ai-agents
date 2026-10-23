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

Each run fails loud when the `system/init` event does not list the installed
skill, or when an instruction file sits above the sandbox, since either one
would make the pair differ by something other than the skill.

Billing and isolation follow the `claude-cli` transport. The credential order,
the blocked metered variables, and the relocated config directory all come
from `_ClaudeCLIProvider`. Only project settings load, and the workspace holds
nothing but the copied skill. `--tools ""` leaves the model no tool to call.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _claude_cli import PROVIDER_LABEL, _ClaudeCLIProvider
from _claude_stream import parse_stream
from _cli_transport import run_cli, validate_timeout

__all__ = [
    "HarnessReply",
    "ambient_instruction_paths",
    "build_argv",
    "harness_prompt",
    "run_harness",
    "skill_name_error",
]

#: A slash command name the CLI resolves. Anything else could carry text into
#: the user turn, so it is refused before a process starts.
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

_EMPTY_MCP_CONFIG = '{"mcpServers":{}}'


@dataclass(frozen=True, slots=True)
class HarnessReply:
    """What one harness run returned, plus the facts that show the skill loaded."""

    text: str
    model: str | None
    #: None when the result event carried no usage record, never a zero.
    input_tokens_total: int | None
    output_tokens: int | None
    cli_version: str
    tool_calls: tuple[str, ...]
    invocation: str | None
    credential_step: str | None = None


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
    """Return a `run_cli` prepare hook that copies the skill into the workspace.

    A copy failure (a dangling link, an unreadable file) is raised as
    RuntimeError, so the runner records the cell as errored instead of dying.
    """
    source = skill_dir.resolve()

    def _install(workspace: Path) -> None:
        target = workspace / ".claude" / "skills" / skill_name
        try:
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        except (OSError, shutil.Error) as exc:
            raise RuntimeError(
                f"{PROVIDER_LABEL} harness could not install skill {skill_name!r}: "
                f"{type(exc).__name__}"
            ) from None

    return _install


#: Files the CLI reads from a working directory's ancestors. One of them above
#: the sandbox would load into both arms, so the control would not be empty.
_AMBIENT_NAMES = ("CLAUDE.md", "CLAUDE.local.md", ".claude", ".claude/CLAUDE.md")


def ambient_instruction_paths(start: Path) -> list[Path]:
    """Return instruction files or directories in `start` and its ancestors.

    The user's own `~/.claude` directory is skipped. It is the CLI's user
    config directory, which the transport relocates with `CLAUDE_CONFIG_DIR`,
    and `--setting-sources project` does not read user settings. A temp
    directory under the home directory, as on Windows, would otherwise refuse
    every run. A `CLAUDE.md` inside it is still refused, since an ancestor's
    `.claude/CLAUDE.md` can load as project memory.
    """
    user_config = (Path.home() / ".claude").resolve()
    return [
        folder / name
        for folder in (start.resolve(), *start.resolve().parents)
        for name in _AMBIENT_NAMES
        if (folder / name).exists() and (folder / name).resolve() != user_config
    ]


def _stream_extras(stdout: str) -> tuple[list[str] | None, bool]:
    """Return the skills `system/init` listed, and whether `result` carried usage.

    `parse_stream` reads neither. None for the skills means no init event.
    """
    skills: list[str] | None = None
    usage_present = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            listed = event.get("skills")
            skills = [str(name) for name in listed] if isinstance(listed, list) else []
        elif event.get("type") == "result":
            usage_present = isinstance(event.get("usage"), dict)
    return skills, usage_present


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

    Raises RuntimeError on instruction files above the sandbox, a failed
    install or process, an incomplete or limit-cut stream, a skill the CLI did
    not list, an empty answer, or a served model outside the requested family.
    """
    if (skill_dir is None) != (skill_name is None):
        raise ValueError("skill_dir and skill_name are set together or not at all")
    if skill_dir is not None and not (skill_dir / "SKILL.md").is_file():
        raise ValueError(f"skill directory has no SKILL.md: {skill_dir}")
    prompt = harness_prompt(text, skill_name)
    ambient = ambient_instruction_paths(Path(tempfile.gettempdir()))
    if ambient:
        raise RuntimeError(
            f"{PROVIDER_LABEL} harness sandbox sits under instruction files "
            f"({', '.join(str(path) for path in ambient)}); set TMPDIR outside any checkout"
        )
    seconds = validate_timeout(timeout)
    provider = _ClaudeCLIProvider(executable=executable, timeout=seconds)
    prepare = None if skill_dir is None or skill_name is None else _installer(skill_dir, skill_name)
    with tempfile.TemporaryDirectory(prefix="eval-claude-harness-") as profile:
        credential = provider._resolve_credential(executable)
        env = provider._build_env(Path(profile), credential)
        completed = run_cli(
            build_argv(executable, model),
            prompt,
            provider_label=PROVIDER_LABEL,
            env=env,
            timeout=seconds,
            prepare=prepare,
        )
    facts = parse_stream(completed.stdout)
    if not facts.completed or facts.limit_hit:
        raise RuntimeError(
            f"{PROVIDER_LABEL} harness run did not complete: "
            f"error={facts.failure or facts.limit_hit or 'unknown'}; response redacted"
        )
    skills, usage_present = _stream_extras(completed.stdout)
    if skill_name is not None and (skills is None or skill_name not in skills):
        raise RuntimeError(
            f"{PROVIDER_LABEL} did not list the installed skill {skill_name!r}, "
            "so the turn did not load it"
        )
    if not facts.final_text.strip():
        raise RuntimeError(f"{PROVIDER_LABEL} harness run returned no answer text")
    if not all(_ClaudeCLIProvider._model_matches(served, model) for served in facts.models):
        raise RuntimeError(
            f"{PROVIDER_LABEL} model attribution mismatch; model identifiers redacted"
        )
    served = sorted(facts.models, key=len, reverse=True)
    total = facts.input_tokens + facts.cache_read_tokens + facts.cache_write_tokens
    return HarnessReply(
        text=facts.final_text,
        model=served[0] if served else None,
        input_tokens_total=total if usage_present else None,
        output_tokens=facts.output_tokens if usage_present else None,
        cli_version=facts.cli_version,
        tool_calls=facts.tool_calls,
        invocation=None if skill_name is None else f"/{skill_name}",
        credential_step=credential.step,
    )
