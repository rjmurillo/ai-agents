#!/usr/bin/env python3
"""PostToolUse hook that auto-lints markdown files after Write/Edit operations.

Automatically runs markdownlint-cli2 --fix on .md files after they are written
or edited. Ensures consistent markdown formatting across the project.

Part of the hooks expansion implementation (Issue #773, Phase 1).

Hook Type: PostToolUse
Matcher: Write|Edit
Filter: .md files only
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)

See: .agents/analysis/claude-code-hooks-opportunity-analysis.md
"""

import json
import os
import subprocess
import sys


def get_file_path_from_input(hook_input: dict) -> str | None:
    """Extract file path from hook input."""
    tool_input = hook_input.get("tool_input")
    if not tool_input or not isinstance(tool_input, dict):
        return None
    return tool_input.get("file_path")


def get_project_directory(hook_input: dict) -> str | None:
    """Get project directory from env var or hook input cwd."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return env_dir
    return hook_input.get("cwd")


def should_lint_file(file_path: str | None) -> bool:
    """Check if the file should be linted.

    Returns True only for existing .md files.
    """
    if not file_path or not file_path.strip():
        return False

    if not file_path.lower().endswith(".md"):
        return False

    if not os.path.isfile(file_path):
        print(f"Warning: Markdown file does not exist: {file_path}", file=sys.stderr)
        return False

    return True


def run_lint(file_path: str, project_dir: str | None) -> None:
    """Run markdownlint-cli2 --fix on the file.

    Always non-blocking. Errors are reported as warnings.
    """
    cwd = project_dir if project_dir and os.path.isdir(project_dir) else None

    try:
        result = subprocess.run(
            ["npx", "markdownlint-cli2", "--fix", file_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
    except FileNotFoundError:
        print(
            f"\n**Markdown Auto-Lint WARNING**: npx not found."
            f" Verify Node.js installation.\n"
        )
        return
    except subprocess.TimeoutExpired:
        print(
            f"\n**Markdown Auto-Lint WARNING**: Linting timed out for `{file_path}`.\n"
        )
        return

    if result.returncode != 0:
        output_text = result.stdout + result.stderr
        if not output_text.strip():
            print(
                f"Warning: Markdown linting failed for {file_path}"
                f" (exit {result.returncode}) with no output."
                f" Linter may not be installed.",
                file=sys.stderr,
            )
            print(
                f"\n**Markdown Auto-Lint WARNING**: Linter failed with no output."
                f" Verify installation: `npm list markdownlint-cli2`\n"
            )
        else:
            error_summary = output_text[:200]
            print(
                f"Warning: Markdown linting failed for {file_path}"
                f" (exit {result.returncode}): {error_summary}",
                file=sys.stderr,
            )
            print(
                f"\n**Markdown Auto-Lint WARNING**: Failed to lint `{file_path}`."
                f" Exit code: {result.returncode}."
                f" Run manually: `npx markdownlint-cli2 --fix '{file_path}'`\n"
            )
    else:
        print(f"\n**Markdown Auto-Lint**: Fixed formatting in `{file_path}`\n")


def main() -> int:
    """Main hook execution. Always returns 0 (non-blocking)."""
    try:
        if sys.stdin.isatty():
            return 0

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            return 0

        hook_input = json.loads(input_text)
        file_path = get_file_path_from_input(hook_input)

        if not should_lint_file(file_path):
            return 0

        project_dir = get_project_directory(hook_input)
        run_lint(file_path, project_dir)

    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"Warning: Markdown auto-lint: Failed to parse hook input JSON - {exc}",
            file=sys.stderr,
        )
    except (OSError, PermissionError) as exc:
        print(
            f"Warning: Markdown auto-lint: File system error - {exc}",
            file=sys.stderr,
        )
        print(
            "\n**Markdown Auto-Lint ERROR**: Cannot access file. Check permissions.\n"
        )
    except Exception as exc:
        print(
            f"Warning: Markdown auto-lint unexpected error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        print(
            "\n**Markdown Auto-Lint ERROR**: Unexpected error. Hook may need attention.\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
