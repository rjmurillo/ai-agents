#!/usr/bin/env python3
"""Block raw gh commands when validated skill scripts exist.

Claude Code PreToolUse hook that enforces skills-first mandate by blocking
raw gh CLI commands when a tested, validated skill script exists for that
operation.

Uses two-stage skill discovery:
1. Exact mapping via hardcoded operation->action table
2. Fuzzy matching via filesystem scan (fallback)

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not a gh command, or no skill exists)
    2 = Block (skill exists, must use it)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

# Leading tokens that wrap another command. Skipping them (and their option
# flags) keeps `env FOO=bar gh ...`, `sudo -E gh ...`, `nohup gh ...`,
# `time gh ...`, `exec gh ...`, and `command gh ...` resolving to the gh
# invocation rather than the wrapper, so a skill-backed gh call cannot be
# hidden behind a shell dispatcher.
_TRANSPARENT_PREFIXES = frozenset({"env", "sudo", "nohup", "time", "exec", "command"})

# Stage 1: Exact mapping of gh operation/action to skill scripts
SKILL_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "pr": {
        "view": {
            "script": "get_pr_context.py",
            "example": (
                "uv run python .claude/skills/github/scripts/pr/"
                "get_pr_context.py --pull-request 123"
            ),
        },
        "list": {
            "script": "get_pull_requests.py",
            "example": "uv run python .claude/skills/github/scripts/pr/get_pull_requests.py",
        },
        "create": {
            "script": "new_pr.py",
            "example": (
                "uv run python .claude/skills/github/scripts/pr/"
                'new_pr.py --title "..." --body "..."'
            ),
        },
        "comment": {
            "script": "post_pr_comment_reply.py",
            "example": (
                "uv run python .claude/skills/github/scripts/pr/"
                'post_pr_comment_reply.py --pull-request 123 --body "..."'
            ),
        },
        "merge": {
            "script": "merge_pr.py",
            "example": "uv run python .claude/skills/github/scripts/pr/merge_pr.py --pull-request 123",
        },
        "close": {
            "script": "close_pr.py",
            "example": "uv run python .claude/skills/github/scripts/pr/close_pr.py --pull-request 123",
        },
        "checks": {
            "script": "get_pr_checks.py",
            "example": (
                "uv run python .claude/skills/github/scripts/pr/"
                "get_pr_checks.py --pull-request 123"
            ),
        },
    },
    "issue": {
        "view": {
            "script": "get_issue_context.py",
            "example": (
                "uv run python .claude/skills/github/scripts/issue/"
                "get_issue_context.py --issue 456"
            ),
        },
        "create": {
            "script": "new_issue.py",
            "example": (
                "uv run python .claude/skills/github/scripts/issue/"
                'new_issue.py --title "..." --body "..."'
            ),
        },
        "comment": {
            "script": "post_issue_comment.py",
            "example": (
                "uv run python .claude/skills/github/scripts/issue/"
                'post_issue_comment.py --issue 456 --body "..."'
            ),
        },
        "list": {
            "script": "list_issues.py",
            "example": (
                "uv run python .claude/skills/github/scripts/issue/"
                "list_issues.py --state open --label bug"
            ),
        },
    },
}


def _is_env_assignment(token: str) -> bool:
    """True for a leading VAR=value environment assignment (not an option/path)."""
    return "=" in token and not token.startswith(("-", "/"))


def _command_word_basename(token: str) -> str:
    """Reduce a command token to its bare executable name.

    Strips any path prefix across POSIX and Windows separators and a trailing
    .exe so /usr/bin/gh, .\\gh, C:\\bin\\gh, and gh.exe all reduce to gh.
    """
    base = re.split(r"[\\/]", token)[-1]
    if base.lower().endswith(".exe"):
        base = base[: -len(".exe")]
    return base


def _tokenize_command(command: str) -> list[str]:
    """Tokenize a full shell command, quote-aware and separator-aware.

    `punctuation_chars` makes the lexer emit shell control operators
    (`&&`, `||`, `|`, `|&`, `;`, `&`, redirections) as their own tokens while
    honoring quotes, so a separator inside a quoted argument
    (`--title "a | gh issue list"`) stays part of that argument and never
    splits the command (issue #2111). POSIX grouping collapses a quoted
    `VAR='x y'` assignment into one token; disabling escape keeps a Windows
    path such as C:\\bin\\gh intact for basename extraction.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=";()<>|&")
    lex.whitespace_split = True
    lex.escape = ""
    return list(lex)


# Tokens emitted by the punctuation-aware lexer that begin a new command
# context. A gh invocation must be the command word of a segment, so segments
# are delimited by these operator tokens. Only real command separators and
# subshell grouping qualify; redirection operators (`<`, `>`, `>>`, `<<`) do
# not start a new command, so they stay inert inside their segment and a
# redirection target is never mistaken for a command word.
_SEGMENT_OPERATORS = frozenset({";", "|", "||", "&", "&&", "|&", "(", ")"})

# A gh operation/action must be a bare subcommand word. Rejecting anything else
# keeps path-traversal operands such as `..` or `../../etc` out of the skill
# lookup, which joins these values into filesystem paths and glob patterns
# (CWE-22).
_OPERAND_RE = re.compile(r"^\w[\w-]*$")


def _split_segments(tokens: list[str]) -> list[list[str]]:
    """Partition a token stream into command segments on operator tokens."""
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SEGMENT_OPERATORS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _gh_args_for_segment(tokens: list[str]) -> list[str] | None:
    """Return the tokens after `gh` if this segment's command word is gh.

    Anchors on the command actually being a `gh` invocation rather than text
    that merely mentions a gh subcommand inside a quoted argument, which the
    previous whole-string regex match flagged as a false positive (issue #2111).
    Returns the tokens following `gh`, or None when the segment does not invoke gh.
    """
    idx = 0
    n = len(tokens)
    while idx < n:
        token = tokens[idx]
        if token in _TRANSPARENT_PREFIXES:
            # Skip the wrapper, then any of its option flags and (for env)
            # VAR=value assignments, so `sudo -E gh`, `env -i gh`, and
            # `env FOO=bar gh` all reach the real command word.
            idx += 1
            while idx < n and (tokens[idx].startswith("-") or _is_env_assignment(tokens[idx])):
                idx += 1
            continue
        # Leading VAR=value environment assignments with no wrapper.
        if _is_env_assignment(token):
            idx += 1
            continue
        break
    if idx >= n:
        return None
    if _command_word_basename(tokens[idx]) != "gh":
        return None
    return tokens[idx + 1:]


def parse_gh_command(command: str) -> dict[str, str] | None:
    """Parse a gh command into operation and action components.

    Tokenizes the command quote-aware, splits it into segments on shell
    operators, and inspects each segment's command word. Only a real `gh`
    invocation (gh as the command, not as quoted argument text) whose
    operation and action are bare subcommand words yields a match.

    Returns dict with 'operation', 'action', 'full_command' or None.
    """
    if not command:
        return None

    try:
        tokens = _tokenize_command(command)
    except ValueError:
        # Unbalanced quotes: we cannot reliably locate shell operator
        # boundaries. Re-splitting a naive whitespace tokenization on operator
        # tokens would reintroduce the issue #2111 false positives, because a
        # separator that was meant to live inside the unterminated quote
        # becomes a boundary again and manufactures a spurious gh segment.
        # Treat the whole command as one segment so only its actual command
        # word can match.
        segments = [command.split()]
    else:
        segments = _split_segments(tokens)

    for segment in segments:
        gh_args = _gh_args_for_segment(segment)
        if gh_args is None:
            continue
        positional = [tok for tok in gh_args if not tok.startswith("-")]
        if len(positional) >= 2 and _OPERAND_RE.match(positional[0]) and _OPERAND_RE.match(positional[1]):
            return {
                "operation": positional[0],
                "action": positional[1],
                "full_command": command,
            }

    return None


def find_skill_script(
    operation: str,
    action: str,
    project_dir: str,
) -> dict[str, str] | None:
    """Find the matching skill script for a gh operation/action.

    Stage 1: Check exact mapping.
    Stage 2: Fuzzy filesystem search (fallback).
    Returns dict with 'path' and 'example', or None.
    """
    project_path = Path(project_dir)

    # Stage 1: Exact mapping
    op_mappings = SKILL_MAPPINGS.get(operation)
    if op_mappings:
        action_mapping = op_mappings.get(action)
        if action_mapping:
            script_path = (
                project_path
                / ".claude"
                / "skills"
                / "github"
                / "scripts"
                / operation
                / action_mapping["script"]
            )
            if script_path.is_file():
                return {"path": str(script_path), "example": action_mapping["example"]}

    # Stage 2: Fuzzy matching
    search_path = project_path / ".claude" / "skills" / "github" / "scripts" / operation
    if not search_path.is_dir():
        return None

    matching_scripts = sorted(search_path.glob(f"*{action}*.py"))
    if not matching_scripts:
        matching_scripts = sorted(search_path.glob(f"*{action}*.ps1"))

    if matching_scripts:
        script = matching_scripts[0]
        relative_path = f".claude/skills/github/scripts/{operation}/{script.name}"
        runner = "uv run python" if script.suffix == ".py" else "pwsh"
        return {"path": str(script), "example": f"{runner} {relative_path} [parameters]"}

    return None


def write_block_response(
    blocked_command: str,
    skill_path: str,
    example_usage: str,
    project_dir: str = "",
) -> None:
    """Write an educational block response to stdout."""
    agents_ref = ""
    if project_dir:
        agents_path = Path(project_dir) / "AGENTS.md"
        if agents_path.is_file():
            agents_ref = " See: `AGENTS.md > Skill-First Checkpoint`"
    output = (
        "\n## BLOCKED: Raw GitHub Command Detected\n\n"
        "**YOU MUST use the validated skill script "
        "instead of raw `gh` commands.**\n\n"
        "### Blocked Command\n```\n"
        f"{blocked_command}\n```\n\n"
        "### Required Alternative (Copy-Paste Ready)\n"
        f"```bash\n{example_usage}\n```\n\n"
        "**Why Skills Are Mandatory**:\n"
        "- Tested with pytest (100% coverage)\n"
        "- Structured error handling\n"
        "- Consistent output format\n"
        "- Centrally maintained\n"
        "- Raw `gh` commands: None of the above\n\n"
        f"**This is not optional.**{agents_ref}\n"
    )
    print(output)
    print(f"Blocked: Raw gh command detected. Use skill at {skill_path}", file=sys.stderr)


def main() -> int:
    """Main hook entry point. Returns exit code."""
    if skip_if_consumer_repo("skill-first-guard"):
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not command:
            return 0

        gh_command = parse_gh_command(command)
        if gh_command is None:
            return 0

        project_dir = get_project_directory()
        skill = find_skill_script(gh_command["operation"], gh_command["action"], project_dir)

        if skill is None:
            # No skill exists, fail-open (allow new capabilities)
            return 0

        # Skill exists, BLOCK with educational message
        write_block_response(
            gh_command["full_command"], skill["path"], skill["example"], project_dir
        )
        return 2

    except Exception as exc:
        # Fail-open on errors (don't block on infrastructure issues)
        print(f"Skill-first guard error: {type(exc).__name__} - {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
