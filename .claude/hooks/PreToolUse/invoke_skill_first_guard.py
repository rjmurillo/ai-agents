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
import sys
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402

_GH_COMMAND_PATTERN = re.compile(r"\bgh\s+(\w+)\s+(\w+)")

# Stage 1: Exact mapping of gh operation/action to skill scripts
SKILL_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "pr": {
        "view": {
            "script": "get_pr_context.py",
            "example": (
                "python3 .claude/skills/github/scripts/pr/"
                "get_pr_context.py --pull-request 123"
            ),
        },
        "list": {
            "script": "get_pull_requests.py",
            "example": "python3 .claude/skills/github/scripts/pr/get_pull_requests.py",
        },
        "create": {
            "script": "new_pr.py",
            "example": (
                "python3 .claude/skills/github/scripts/pr/"
                'new_pr.py --title "..." --body "..."'
            ),
        },
        "comment": {
            "script": "post_pr_comment_reply.py",
            "example": (
                "python3 .claude/skills/github/scripts/pr/"
                'post_pr_comment_reply.py --pull-request 123 --body "..."'
            ),
        },
        "merge": {
            "script": "merge_pr.py",
            "example": "python3 .claude/skills/github/scripts/pr/merge_pr.py --pull-request 123",
        },
        "close": {
            "script": "close_pr.py",
            "example": "python3 .claude/skills/github/scripts/pr/close_pr.py --pull-request 123",
        },
        "checks": {
            "script": "get_pr_checks.py",
            "example": (
                "python3 .claude/skills/github/scripts/pr/"
                "get_pr_checks.py --pull-request 123"
            ),
        },
    },
    "issue": {
        "view": {
            "script": "get_issue_context.py",
            "example": (
                "python3 .claude/skills/github/scripts/issue/"
                "get_issue_context.py --issue 456"
            ),
        },
        "create": {
            "script": "new_issue.py",
            "example": (
                "python3 .claude/skills/github/scripts/issue/"
                'new_issue.py --title "..." --body "..."'
            ),
        },
        "comment": {
            "script": "post_issue_comment.py",
            "example": (
                "python3 .claude/skills/github/scripts/issue/"
                'post_issue_comment.py --issue 456 --body "..."'
            ),
        },
        "list": {
            "script": "get_issue_context.py",
            "example": "python3 .claude/skills/github/scripts/issue/get_issue_context.py",
        },
    },
}


def parse_gh_command(command: str) -> dict[str, str] | None:
    """Parse a gh command into operation and action components.

    Returns dict with 'operation', 'action', 'full_command' or None.
    """
    if not command:
        return None

    match = _GH_COMMAND_PATTERN.search(command)
    if not match:
        return None

    return {
        "operation": match.group(1),
        "action": match.group(2),
        "full_command": command,
    }


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
        runner = "python3" if script.suffix == ".py" else "pwsh"
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
