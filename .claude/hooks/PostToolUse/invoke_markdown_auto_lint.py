#!/usr/bin/env python3
"""Auto-lint markdown files after Write/Edit operations.

Claude Code PostToolUse hook that automatically runs markdownlint-cli2 --fix
on .md files after they are written or edited. This ensures consistent markdown
formatting across the project without manual intervention.

Hook Type: PostToolUse
Matcher: Write|Edit
Filter: .md files only
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (non-blocking hook, all errors are warnings)
"""

from __future__ import annotations

import json
import os
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
        print(
            "WARNING: Markdown auto-lint: Failed to parse hook input JSON",
            file=sys.stderr,
        )
        return 0

    file_path = get_file_path_from_input(hook_input)
    project_dir = get_project_directory(hook_input)
    if not should_lint_file(file_path, project_dir) or file_path is None:
        return 0

    try:
        result = subprocess.run(
            ["npx", "markdownlint-cli2", "--fix", file_path],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )

        if result.returncode != 0:
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
            else:
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
        else:
            print(f"\n**Markdown Auto-Lint**: Fixed formatting in `{file_path}`\n")
    except FileNotFoundError:
        print(
            f"WARNING: npx not found. Cannot lint {file_path}",
            file=sys.stderr,
        )
        print(
            "\n**Markdown Auto-Lint WARNING**: npx not found. "
            "Install Node.js and markdownlint-cli2.\n"
        )
    except OSError as exc:
        print(
            f"WARNING: Markdown auto-lint: File system error for {file_path}: {exc}",
            file=sys.stderr,
        )
        print(
            f"\n**Markdown Auto-Lint ERROR**: Cannot access file `{file_path}`. "
            "Check permissions.\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
