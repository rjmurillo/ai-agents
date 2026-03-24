#!/usr/bin/env python3
"""Auto-runs CodeQL quick scan after Python/workflow file writes.

Claude Code PostToolUse hook that automatically triggers targeted CodeQL security
scans after Write operations on Python files (*.py) or GitHub Actions workflows
(*.yml in .github/workflows/).

Uses a quick scan configuration with only 5-10 critical CWEs (command injection,
SQL injection, XSS, path traversal, hardcoded credentials) to meet a 30-second
performance budget. Gracefully degrades if CodeQL CLI is not installed.

Part of the CodeQL multi-tier security strategy (Tier 3: PostToolUse Hook).

Hook Type: PostToolUse
Matcher: Write
Filter: *.py files, *.yml in .github/workflows/
Performance Budget: 30 seconds
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)
"""

import json
import os
import shutil
import subprocess
import sys


def _get_file_path_from_input(hook_input: dict) -> str | None:
    """Extract file_path from hook input."""
    tool_input = hook_input.get("tool_input", {})
    if isinstance(tool_input, dict):
        return tool_input.get("file_path")
    return None


def _get_project_directory(hook_input: dict) -> str:
    """Resolve project directory from env or hook input."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir
    cwd = hook_input.get("cwd", os.getcwd())
    return str(cwd) if cwd else os.getcwd()


def _should_scan_file(file_path: str) -> bool:
    """Determine if file should trigger CodeQL quick scan."""
    if not file_path or not file_path.strip():
        return False

    if not os.path.exists(file_path):
        return False

    # Check for Python files
    if file_path.lower().endswith(".py"):
        return True

    # Check for GitHub Actions workflows
    if file_path.lower().endswith((".yml", ".yaml")):
        normalized = file_path.replace("\\", "/")
        if ".github/workflows/" in normalized:
            return True

    return False


def _is_codeql_installed(project_dir: str) -> bool:
    """Check if CodeQL CLI is installed and accessible."""
    if shutil.which("codeql"):
        return True

    default_path = os.path.join(project_dir, ".codeql", "cli", "codeql")
    if sys.platform == "win32":
        default_path += ".exe"

    return os.path.exists(default_path)


def _get_language_from_file(file_path: str) -> str | None:
    """Determine CodeQL language from file extension."""
    lower = file_path.lower()
    if lower.endswith(".py"):
        return "python"
    if lower.endswith((".yml", ".yaml")):
        return "actions"
    return None


def main() -> int:
    """Main hook entry point. Always returns 0 (non-blocking)."""
    try:
        if not sys.stdin.readable():
            return 0

        input_json = sys.stdin.read()
        if not input_json or not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
        file_path = _get_file_path_from_input(hook_input)

        if file_path is None or not _should_scan_file(file_path):
            return 0

        project_dir = _get_project_directory(hook_input)

        if not _is_codeql_installed(project_dir):
            return 0

        language = _get_language_from_file(file_path)
        if not language:
            return 0

        scan_script_path = os.path.join(
            project_dir, ".codeql", "scripts", "Invoke-CodeQLScan.ps1"
        )
        if not os.path.exists(scan_script_path):
            return 0

        # Invoke quick scan with 30-second timeout
        try:
            result = subprocess.run(
                [
                    "pwsh", "-NoProfile", "-NonInteractive",
                    "-File", scan_script_path,
                    "-Languages", language,
                    "-QuickScan",
                    "-UseCache",
                    "-RepoPath", project_dir,
                    "-Format", "json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_dir,
            )
        except subprocess.TimeoutExpired:
            print(
                f"\n**CodeQL Quick Scan WARNING**: Scan timed out after 30s "
                f"for `{file_path}`. Run full scan manually.\n"
            )
            return 0

        if result.returncode != 0:
            print(
                "\n**CodeQL Quick Scan ERROR**: Scan failed. "
                "Check .codeql/logs/ or run manual scan for details.\n"
            )
            return 0

        # Parse JSON output for findings count
        findings_count = 0
        try:
            lines = result.stdout.strip().splitlines()
            json_lines = [line for line in lines if line.strip().startswith("{")]
            if json_lines:
                json_output = "\n".join(json_lines)
                scan_result = json.loads(json_output)
                findings_count = scan_result.get("TotalFindings", 0)
        except (json.JSONDecodeError, KeyError, TypeError):
            print(
                "\n**CodeQL Quick Scan ERROR**: Scan output invalid. "
                "Run manual scan to see actual errors: "
                "`pwsh .codeql/scripts/Invoke-CodeQLScan.ps1`\n"
            )
            return 0

        if findings_count > 0:
            print(
                f"\n**CodeQL Quick Scan**: Analyzed `{file_path}` "
                f"- **{findings_count} finding(s) detected**\n"
            )
        else:
            print(
                f"\n**CodeQL Quick Scan**: Analyzed `{file_path}` "
                f"- No findings\n"
            )

    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    except (OSError, PermissionError):
        pass
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
