#!/usr/bin/env python3
"""Auto-lint markdown files after Write/Edit operations.

Claude Code PostToolUse hook that automatically runs markdownlint-cli2 --fix
on .md files after they are written or edited. This ensures consistent markdown
formatting across the project without manual intervention.

Hook Type: PostToolUse
Matcher: Write|Edit
Filter: .md files only
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Skipped or lint succeeded
    2 = Block (malformed hook input or markdown lint failed)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_file_path_from_input(hook_input: dict[str, object]) -> str | None:
    """Extract file_path from hook input's tool_input."""
    tool_input = hook_input.get("tool_input")
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            return file_path.strip()
    return None


def get_project_directory(hook_input: dict[str, object]) -> str:
    """Resolve the project directory from environment or hook input."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir
    cwd = hook_input.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    return os.getcwd()


def should_lint_file(file_path: str | None, project_dir: str) -> bool:
    """Check if the file is a markdown file within the project that exists on disk."""
    if not file_path:
        return False
    if not file_path.lower().endswith(".md"):
        return False
    resolved = Path(file_path).resolve()
    project_resolved = Path(project_dir).resolve()
    if not str(resolved).startswith(str(project_resolved) + os.sep):
        print(
            f"WARNING: Path outside project directory: {file_path}",
            file=sys.stderr,
        )
        return False
    if not resolved.exists():
        print(
            f"WARNING: Markdown file does not exist: {file_path}",
            file=sys.stderr,
        )
        return False
    return True


def read_hook_input() -> dict[str, object] | None:
    """Read and validate hook input from stdin."""
    if sys.stdin.isatty():
        return None
    input_json = sys.stdin.read()
    if not input_json.strip():
        return None
    parsed: object = json.loads(input_json)
    if not isinstance(parsed, dict):
        raise ValueError("hook input JSON must be an object")
    return parsed


def report_missing_npx(file_path: str) -> None:
    """Report that the markdown linter cannot run because npx is missing."""
    print(
        f"ERROR: npx not found. Cannot lint {file_path}",
        file=sys.stderr,
    )
    print(
        "\n**Markdown Auto-Lint ERROR**: npx not found. "
        "Install Node.js and markdownlint-cli2.\n"
    )


def report_lint_failure(file_path: str, result: subprocess.CompletedProcess[str]) -> None:
    """Report a non-zero markdownlint result."""
    output = (result.stderr or result.stdout or "").strip()
    if not output:
        print(
            f"WARNING: Markdown linting failed for {file_path} "
            f"(exit {result.returncode}) with no output. "
            "Linter may not be installed.",
            file=sys.stderr,
        )
        print(
            "\n**Markdown Auto-Lint WARNING**: Linter failed with no output. "
            "Verify installation: `npm list markdownlint-cli2`\n"
        )
        return
    error_summary = output[:200]
    print(
        f"WARNING: Markdown linting failed for {file_path} "
        f"(exit {result.returncode}): {error_summary}",
        file=sys.stderr,
    )
    print(
        f"\n**Markdown Auto-Lint WARNING**: Failed to lint `{file_path}`. "
        f"Exit code: {result.returncode}. "
        f"Run manually: `npx markdownlint-cli2 --fix '{file_path}'`\n"
    )


def run_markdownlint(file_path: str, project_dir: str) -> int:
    """Run markdownlint and return the hook exit code."""
    try:
        # Issue #2523: bounded timeout (release-it.md). Without it, a cold npm
        # cache or unreachable registry blocks every .md Write/Edit turn
        # indefinitely. 30s matches the CodeQL hook budget.
        result = subprocess.run(
            ["npx", "markdownlint-cli2", "--fix", file_path],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            timeout=30,
        )

        if result.returncode != 0:
            report_lint_failure(file_path, result)
            return 2
        print(f"\n**Markdown Auto-Lint**: Fixed formatting in `{file_path}`\n")
        return 0
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: Markdown linting timed out after 30s for {file_path}",
            file=sys.stderr,
        )
        print(
            f"\n**Markdown Auto-Lint WARNING**: Lint timed out for `{file_path}`. "
            f"Run manually: `npx markdownlint-cli2 --fix '{file_path}'`\n"
        )
        return 2
    except FileNotFoundError:
        print(
            f"ERROR: npx not found. Cannot lint {file_path}",
            file=sys.stderr,
        )
        print(
            "\n**Markdown Auto-Lint WARNING**: npx not found. "
            "Install Node.js and markdownlint-cli2.\n"
        )
        return 2
    except OSError as exc:
        print(
            f"ERROR: Markdown auto-lint: File system error for {file_path}: {exc}",
            file=sys.stderr,
        )
        print(
            f"\n**Markdown Auto-Lint ERROR**: Cannot access file `{file_path}`. "
            "Check permissions.\n"
        )
        return 2


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        hook_input = read_hook_input()
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"ERROR: Markdown auto-lint: Failed to parse hook input JSON: {exc}",
            file=sys.stderr,
        )
        return 2
    if hook_input is None:
        return 0

    file_path = get_file_path_from_input(hook_input)
    project_dir = get_project_directory(hook_input)
    if not should_lint_file(file_path, project_dir) or file_path is None:
        return 0

    if not shutil.which("npx"):
        report_missing_npx(file_path)
        return 2

    return run_markdownlint(file_path, project_dir)


if __name__ == "__main__":
    sys.exit(main())
