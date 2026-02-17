#!/usr/bin/env python3
"""Routing-level enforcement gates for Claude Code per ADR-033.

Blocks high-stakes actions until validation prerequisites are met.
Implements Gate 2: QA Validation Gate that blocks PR creation without QA evidence.

QA Evidence is satisfied by:
1. QA report exists in .agents/qa/ from the last 24 hours
2. QA section in today's session log

Bypass conditions:
- Documentation-only PRs (no code changes)
- SKIP_QA_GATE environment variable set

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (uses JSON decision payload for deny/allow semantics)
"""

from __future__ import annotations

import os
import sys

# Plugin mode: skip project-specific enforcement in consumer repos
if os.environ.get("CLAUDE_PLUGIN_ROOT"):
    sys.exit(0)

import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

_QA_EVIDENCE_PATTERN = re.compile(r"(?i)## QA|qa agent|Test Results|QA Validation|Test Strategy")

# Documentation-only file patterns (anchored to prevent substring matches)
_DOC_PATTERNS = [
    re.compile(r"\.md$"),
    re.compile(r"\.txt$"),
    re.compile(r"(^|/)README$"),
    re.compile(r"(^|/)LICENSE$"),
    re.compile(r"(^|/)CHANGELOG$"),
    re.compile(r"\.gitignore$"),
]


def write_audit_log(hook_name: str, message: str) -> None:
    """Write hook failure events to persistent audit log."""
    try:
        script_dir = Path(__file__).resolve().parent
        audit_log_path = script_dir / "audit.log"
        timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{hook_name}] {message}\n"
        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as exc:
        print(f"[{hook_name}] Audit log write failed: {exc}", file=sys.stderr)
        try:
            import tempfile

            temp_path = Path(tempfile.gettempdir()) / "claude-hook-audit.log"
            timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
            entry = f"[{timestamp}] [{hook_name}] {message}\n"
            with open(temp_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError:
            print(
                f"[{hook_name}] CRITICAL: All audit log paths failed. Original message: {message}",
                file=sys.stderr,
            )


def get_today_session_log_local() -> Path | None:
    """Find today's most recent session log.

    Uses local logic instead of the shared utility because this hook
    operates from CWD rather than the project root discovered by the utility.
    """
    session_dir = Path(".agents/sessions")
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    if not session_dir.is_dir():
        print(f"routing_gates: Session directory not found: {session_dir}", file=sys.stderr)
        return None

    try:
        logs = sorted(
            session_dir.glob(f"{today}-session-*.json"),
            key=lambda p: p.name,
            reverse=True,
        )
        return logs[0] if logs else None
    except OSError as exc:
        msg = f"Failed to read session logs from {session_dir}: {exc}"
        print(f"routing_gates: {msg}", file=sys.stderr)
        write_audit_log("RoutingGates", f"Session log read error: {exc}")
        return None


def check_qa_evidence() -> bool:
    """Check for QA evidence in reports or session log."""
    # Option 1: QA report in .agents/qa/ from last 24 hours
    qa_dir = Path(".agents/qa")
    if qa_dir.is_dir():
        cutoff_time = time.time() - (24 * 3600)
        for report in qa_dir.glob("*.md"):
            if report.stat().st_mtime > cutoff_time:
                return True

    # Option 2: QA section in session log
    session_log = get_today_session_log_local()
    if session_log is not None:
        try:
            content = session_log.read_text(encoding="utf-8")
        except OSError as exc:
            msg = f"Session log exists but cannot be read: {exc}"
            print(f"routing_gates: {msg}", file=sys.stderr)
            write_audit_log("RoutingGates", f"Session log read failed: {exc}")
            return False

        if content and _QA_EVIDENCE_PATTERN.search(content):
            return True

    return False


def check_documentation_only() -> bool:
    """Check if all changed files are documentation-only.

    Security: checks committed changes (not working tree) to prevent bypass.
    Fail-closed on git errors to prevent QA bypass.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "diff", "--name-only", "origin/main"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                error_msg = f"git diff failed (exit {result.returncode}): {result.stderr.strip()}"
                print(
                    f"routing_gates: {error_msg}. Failing closed (git errors block).",
                    file=sys.stderr,
                )
                write_audit_log("RoutingGates", error_msg)
                return False

        changed_files = result.stdout.strip()
        if not changed_files:
            return True  # No changes, allow (fail-open)

        for file_path in changed_files.splitlines():
            is_doc = any(pat.search(file_path) for pat in _DOC_PATTERNS)
            if not is_doc:
                return False  # Code file found

        return True  # All files are documentation

    except PermissionError as exc:
        error_msg = f"Permission denied checking git diff: {exc}"
        print(f"routing_gates: {error_msg}. Failing closed (QA required).", file=sys.stderr)
        write_audit_log("RoutingGates", error_msg)
        return False
    except OSError as exc:
        error_msg = f"I/O error checking git diff: {exc}"
        print(f"routing_gates: {error_msg}. Failing closed (QA required).", file=sys.stderr)
        write_audit_log("RoutingGates", error_msg)
        return False
    except Exception as exc:
        error_msg = f"Unexpected error checking changed files: {type(exc).__name__} - {exc}"
        print(f"routing_gates: {error_msg}. Failing closed (QA required).", file=sys.stderr)
        write_audit_log("RoutingGates", error_msg)
        return False


def is_valid_project_root() -> bool:
    """Validate that CWD is a project root directory."""
    indicators = [".claude/settings.json", ".git"]
    cwd = Path.cwd()
    return any((cwd / indicator).exists() for indicator in indicators)


def main() -> int:
    """Main hook entry point. Returns exit code."""
    if not is_valid_project_root():
        cwd = Path.cwd()
        print(
            f"routing_gates: CWD '{cwd}' does not appear to be a project root "
            "(missing .claude/settings.json or .git). Failing open.",
            file=sys.stderr,
        )
        return 0

    command = ""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        input_data = json.loads(input_json)
        tool_input = input_data.get("tool_input")
        if isinstance(tool_input, dict):
            cmd = tool_input.get("command")
            if isinstance(cmd, str):
                command = cmd
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"routing_gates: Failed to parse input JSON. Error: {exc}. "
            "Assuming empty command and allowing action.",
            file=sys.stderr,
        )
        command = ""

    # Gate 2: QA Validation (for PR creation)
    if "gh pr create" in command:
        # Bypass 1: Environment variable override
        if os.environ.get("SKIP_QA_GATE") == "true":
            write_audit_log(
                "RoutingGates",
                "QA gate bypassed via SKIP_QA_GATE environment variable",
            )
            return 0

        # Bypass 2: Documentation-only changes
        if check_documentation_only():
            return 0

        # Main check: QA evidence required
        if not check_qa_evidence():
            output = {
                "decision": "deny",
                "reason": (
                    "QA VALIDATION GATE: QA evidence required before PR creation.\n\n"
                    "Invoke the QA agent to verify changes:\n"
                    "  #runSubagent with subagentType=qa prompt='Verify changes for PR'\n\n"
                    "Or create a QA report file in .agents/qa/\n\n"
                    "Bypass conditions:\n"
                    "- Documentation-only PRs (auto-detected based on file extensions)\n"
                    "- Set SKIP_QA_GATE=true environment variable (requires justification)"
                ),
            }
            print(json.dumps(output, separators=(",", ":")))
            return 0  # JSON output with deny decision

    return 0


if __name__ == "__main__":
    sys.exit(main())
