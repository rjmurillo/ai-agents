#!/usr/bin/env python3
"""Block git commit/push operations on main/master branches.

Claude Code PreToolUse hook that prevents accidental commits and pushes
to protected branches (main, master). Enforces the SESSION-PROTOCOL
requirement that work must be done on feature branches.

Hook Type: PreToolUse
Matcher: Bash(git commit*|git push*)
Exit Codes:
    0 = Success, operation allowed
    2 = Block operation (on protected branch)

Related:
    .agents/SESSION-PROTOCOL.md
    .agents/analysis/claude-code-hooks-opportunity-analysis.md
"""

import json
import os
import subprocess
import sys


PROTECTED_BRANCHES = ("main", "master")


def write_block_response(reason: str) -> None:
    """Output a block response and exit with code 2."""
    response = json.dumps({"decision": "block", "reason": reason})
    print(response)
    sys.exit(2)


def get_working_directory(hook_input: dict) -> str:
    """Determine working directory from hook input, env, or cwd."""
    cwd = hook_input.get("cwd", "")
    if cwd and cwd.strip():
        return cwd.strip()
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env_dir and env_dir.strip():
        return env_dir.strip()
    return os.getcwd()


def get_current_branch(cwd: str) -> str:
    """Run git branch --show-current and return the branch name.

    Raises SystemExit(2) with block response on git failures.
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
    except FileNotFoundError:
        write_block_response(
            f"Git not found in PATH. Cannot verify branch safety in '{cwd}'."
        )
    except subprocess.TimeoutExpired:
        write_block_response(
            f"Git command timed out in '{cwd}'. Cannot verify branch safety."
        )

    if result.returncode == 128:
        write_block_response(
            f"Not a git repository or git not installed in '{cwd}'. "
            "Cannot verify branch safety. Check: git status"
        )
    elif result.returncode != 0:
        output = result.stderr.strip() or result.stdout.strip()
        write_block_response(
            f"Cannot determine current git branch in '{cwd}' "
            f"(git failed with exit code {result.returncode}). "
            f"Verify manually: git branch --show-current. Output: {output}"
        )

    return result.stdout.strip()


def main() -> None:
    """Entry point for the branch protection guard hook."""
    if sys.stdin.isatty():
        sys.exit(0)

    input_text = sys.stdin.read()
    if not input_text or not input_text.strip():
        sys.exit(0)

    try:
        hook_input = json.loads(input_text)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    cwd = get_working_directory(hook_input)

    try:
        current_branch = get_current_branch(cwd)
    except SystemExit:
        raise
    except Exception as exc:
        write_block_response(
            f"Branch protection check failed and cannot verify branch safety "
            f"in '{cwd}'. Verify manually: git branch --show-current. "
            f"Error: {exc}"
        )

    if current_branch in PROTECTED_BRANCHES:
        write_block_response(
            f"Cannot commit or push directly to protected branch "
            f"'{current_branch}'. Create a feature branch first: "
            f"git checkout -b feature/your-feature-name"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
