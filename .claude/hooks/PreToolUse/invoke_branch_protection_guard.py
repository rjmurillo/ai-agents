#!/usr/bin/env python3
"""Block git commit/push on main/master branches.

Claude Code PreToolUse hook that prevents accidental commits and pushes
to protected branches (main, master). Enforces SESSION-PROTOCOL requirement
that work must be done on feature branches.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow operation
    2 = Block operation (on protected branch)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

PROTECTED_BRANCHES = ("main", "master")


def write_block_response(reason: str) -> None:
    """Write a JSON block response to stdout."""
    response = json.dumps({"decision": "block", "reason": reason})
    print(response)


def get_working_directory(hook_input: dict[str, object]) -> str:
    """Resolve the working directory from hook input or environment."""
    cwd = hook_input.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()

    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir

    return os.getcwd()


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = get_working_directory(hook_input)

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

        if result.returncode == 128:
            msg = (
                f"Not a git repository or git not installed in '{cwd}'. "
                "Cannot verify branch safety. Check: git status"
            )
            print(msg, file=sys.stderr)
            write_block_response(msg)
            return 2

        if result.returncode != 0:
            output = result.stderr.strip() or result.stdout.strip()
            msg = (
                f"Cannot determine current git branch in '{cwd}' "
                f"(git failed with exit code {result.returncode}). "
                f"Verify manually: git branch --show-current. Output: {output}"
            )
            print(msg, file=sys.stderr)
            write_block_response(msg)
            return 2

        current_branch = result.stdout.strip()

        if current_branch in PROTECTED_BRANCHES:
            msg = (
                f"Cannot commit or push directly to protected branch '{current_branch}'. "
                "Create a feature branch first: git checkout -b feature/your-feature-name"
            )
            write_block_response(msg)
            return 2

        return 0

    except Exception as exc:
        msg = (
            f"Branch protection check failed in '{cwd}': {exc}. "
            "Verify manually: git branch --show-current."
        )
        print(msg, file=sys.stderr)
        write_block_response(msg)
        return 2


if __name__ == "__main__":
    sys.exit(main())
