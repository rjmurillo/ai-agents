#!/usr/bin/env python3
"""PreToolUse hook that blocks raw gh commands when validated skill scripts exist.

Enforces the skills-first mandate by blocking raw `gh` CLI commands when a tested,
validated skill script exists for that operation. Prevents:

- Duplicated logic across sessions
- Untested inline commands
- Inconsistent error handling
- Loss of reusable abstractions

Uses two-stage skill discovery:
1. Exact mapping via hardcoded operation->action table
2. Fuzzy matching via filesystem scan (fallback)

Part of Tier 2 enforcement hooks (Issue #773, Skills-first mandate).

Hook Type: PreToolUse
Matcher: Bash
Exit Codes:
    0 = Allow (not a gh command, or no skill exists)
    2 = Block (skill exists, must use it)

See: .serena/memories/usage-mandatory.md
"""

import json
import os
import re
import sys
from pathlib import Path

# Skill script mappings: operation -> action -> {script, example}
SKILL_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "pr": {
        "view": {
            "script": "get_pr_context.py",
            "example": 'python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request 123',
        },
        "list": {
            "script": "get_pull_requests.py",
            "example": 'python3 "$SCRIPTS_DIR/pr/get_pull_requests.py"',
        },
        "create": {
            "script": "new_pr.py",
            "example": 'python3 "$SCRIPTS_DIR/pr/new_pr.py" --title "feat: ..." --body "..."',
        },
        "comment": {
            "script": "post_pr_comment_reply.py",
            "example": (
                'python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py"'
                ' --pull-request 123 --body "..."'
            ),
        },
        "merge": {
            "script": "merge_pr.py",
            "example": 'python3 "$SCRIPTS_DIR/pr/merge_pr.py" --pull-request 123',
        },
        "close": {
            "script": "close_pr.py",
            "example": 'python3 "$SCRIPTS_DIR/pr/close_pr.py" --pull-request 123',
        },
        "checks": {
            "script": "get_pr_checks.py",
            "example": 'python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 123',
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
                "python3 .claude/skills/github/scripts/issue/post_issue_comment.py"
                ' --issue 456 --body "..."'
            ),
        },
        "list": {
            "script": "get_issue_context.py",
            "example": "python3 .claude/skills/github/scripts/issue/get_issue_context.py --list",
        },
    },
}


def get_project_directory() -> str:
    """Resolve the project root directory.

    Checks CLAUDE_PROJECT_DIR env var first, then walks up from cwd to find .git.
    Falls back to cwd if project root cannot be determined.
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return env_dir

    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent

    return str(Path.cwd())


def parse_gh_command(command: str) -> dict | None:
    """Parse a gh command string into operation and action.

    Returns dict with operation, action, full_command or None if not a gh command.
    """
    if not command or not command.strip():
        return None

    match = re.search(r"\bgh\s+(\w+)\s+(\w+)", command)
    if not match:
        return None

    return {
        "operation": match.group(1),
        "action": match.group(2),
        "full_command": command,
    }


def get_skill_script(operation: str, action: str, project_dir: str) -> dict | None:
    """Find skill script for the given gh operation and action.

    Stage 1: Exact mapping via hardcoded table.
    Stage 2: Fuzzy matching via filesystem scan (fallback).

    Returns dict with path and example, or None if no skill exists.
    """
    # Stage 1: Exact mapping
    if operation in SKILL_MAPPINGS:
        actions = SKILL_MAPPINGS[operation]
        if action in actions:
            mapping = actions[action]
            script_path = os.path.join(
                project_dir,
                ".claude",
                "skills",
                "github",
                "scripts",
                operation,
                mapping["script"],
            )
            if os.path.isfile(script_path):
                return {"path": script_path, "example": mapping["example"]}

    # Stage 2: Fuzzy matching (fallback)
    search_path = os.path.join(
        project_dir, ".claude", "skills", "github", "scripts", operation
    )
    if not os.path.isdir(search_path):
        return None

    search_dir = Path(search_path)
    matching = sorted(search_dir.glob(f"*{action}*.py"))
    if matching:
        script = matching[0]
        relative_path = f".claude/skills/github/scripts/{operation}/{script.name}"
        return {
            "path": str(script),
            "example": f"python3 {relative_path} [parameters]",
        }

    return None


def format_block_response(blocked_command: str, skill_path: str, example: str) -> str:
    """Format the blocking response message."""
    return f"""
## BLOCKED: Raw GitHub Command Detected

**YOU MUST use the validated skill script instead of raw `gh` commands.**

### Blocked Command
```
{blocked_command}
```

### Required Alternative (Copy-Paste Ready)
```bash
{example}
```

**Why Skills Are Mandatory**:
- Tested with full coverage
- Structured error handling
- Consistent output format
- Centrally maintained
- Raw `gh` commands: None of the above

**This is not optional.** See: `.serena/memories/usage-mandatory.md`
"""


def main() -> int:
    """Main hook execution."""
    try:
        # Read JSON input from stdin
        if sys.stdin.isatty():
            return 0

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            return 0

        hook_input = json.loads(input_text)

        # Extract command from tool_input
        tool_input = hook_input.get("tool_input")
        if not tool_input or not isinstance(tool_input, dict):
            return 0

        command = tool_input.get("command")
        if not command:
            return 0

        # Test if this is a gh command
        gh_command = parse_gh_command(command)
        if gh_command is None:
            return 0

        # Check if skill exists for this operation
        project_dir = get_project_directory()
        skill = get_skill_script(
            gh_command["operation"], gh_command["action"], project_dir
        )

        if skill is None:
            # No skill exists, fail-open (allow new capabilities)
            return 0

        # Skill exists, BLOCK with educational message
        output = format_block_response(
            gh_command["full_command"], skill["path"], skill["example"]
        )
        print(output)
        print(
            f"Blocked: Raw gh command detected. Use skill at {skill['path']}",
            file=sys.stderr,
        )
        return 2

    except Exception as exc:
        # Fail-open on errors (don't block on infrastructure issues)
        print(f"Skill-first guard error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
