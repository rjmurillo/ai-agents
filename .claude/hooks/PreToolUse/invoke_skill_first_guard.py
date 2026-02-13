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
import re
import sys
from pathlib import Path

# Add project root to path for imports
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.hook_utilities.utilities import get_project_directory  # noqa: E402

_GH_COMMAND_PATTERN = re.compile(r"\bgh\s+(\w+)\s+(\w+)")

# Stage 1: Exact mapping of gh operation/action to skill scripts
SKILL_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "pr": {
        "view": {
            "script": "Get-PRContext.ps1",
            "example": "pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 123",
        },
        "list": {
            "script": "Get-PullRequests.ps1",
            "example": "pwsh .claude/skills/github/scripts/pr/Get-PullRequests.ps1",
        },
        "create": {
            "script": "New-PR.ps1",
            "example": 'pwsh .claude/skills/github/scripts/pr/New-PR.ps1 -Title "..." -Body "..."',
        },
        "comment": {
            "script": "Post-PRCommentReply.ps1",
            "example": (
                "pwsh .claude/skills/github/scripts/pr/"
                'Post-PRCommentReply.ps1 -PullRequest 123 -Body "..."'
            ),
        },
        "merge": {
            "script": "Merge-PR.ps1",
            "example": "pwsh .claude/skills/github/scripts/pr/Merge-PR.ps1 -PullRequest 123",
        },
        "close": {
            "script": "Close-PR.ps1",
            "example": "pwsh .claude/skills/github/scripts/pr/Close-PR.ps1 -PullRequest 123",
        },
        "checks": {
            "script": "Get-PRChecks.ps1",
            "example": "pwsh .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest 123",
        },
    },
    "issue": {
        "view": {
            "script": "Get-IssueContext.ps1",
            "example": "pwsh .claude/skills/github/scripts/issue/Get-IssueContext.ps1 -Issue 456",
        },
        "create": {
            "script": "New-Issue.ps1",
            "example": (
                'pwsh .claude/skills/github/scripts/issue/New-Issue.ps1 -Title "..." -Body "..."'
            ),
        },
        "comment": {
            "script": "Post-IssueComment.ps1",
            "example": (
                "pwsh .claude/skills/github/scripts/issue/"
                'Post-IssueComment.ps1 -Issue 456 -Body "..."'
            ),
        },
        "list": {
            "script": "Get-Issues.ps1",
            "example": "pwsh .claude/skills/github/scripts/issue/Get-Issues.ps1",
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

    matching_scripts = sorted(search_path.glob(f"*{action}*.ps1"))
    if not matching_scripts:
        # Also check for Python skill scripts
        matching_scripts = sorted(search_path.glob(f"*{action}*.py"))

    if matching_scripts:
        script = matching_scripts[0]
        relative_path = f".claude/skills/github/scripts/{operation}/{script.name}"
        return {"path": str(script), "example": f"pwsh {relative_path} [parameters]"}

    return None


def write_block_response(
    blocked_command: str,
    skill_path: str,
    example_usage: str,
) -> None:
    """Write an educational block response to stdout."""
    output = (
        "\n## BLOCKED: Raw GitHub Command Detected\n\n"
        "**YOU MUST use the validated skill script "
        "instead of raw `gh` commands.**\n\n"
        "### Blocked Command\n```\n"
        f"{blocked_command}\n```\n\n"
        "### Required Alternative (Copy-Paste Ready)\n"
        f"```powershell\n{example_usage}\n```\n\n"
        "**Why Skills Are Mandatory**:\n"
        "- Tested with Pester (100% coverage)\n"
        "- Structured error handling\n"
        "- Consistent output format\n"
        "- Centrally maintained\n"
        "- Raw `gh` commands: None of the above\n\n"
        "**This is not optional.** "
        "See: `.serena/memories/usage-mandatory.md`\n"
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
        write_block_response(gh_command["full_command"], skill["path"], skill["example"])
        return 2

    except Exception as exc:
        # Fail-open on errors (don't block on infrastructure issues)
        print(f"Skill-first guard error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
