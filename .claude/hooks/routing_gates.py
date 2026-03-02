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

EXIT CODES (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow action OR JSON decision (deny/allow)
    1 = Hook error (fail-open)
    2 = Block action immediately (hook-specific)

Per ADR-033, this uses JSON decision mode for structured error messages.
"""

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _write_audit_log(hook_name: str, message: str) -> None:
    """Write hook failure events to persistent audit log."""
    try:
        script_dir = Path(__file__).resolve().parent
        audit_log_path = script_dir / "audit.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{hook_name}] {message}\n"
        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except OSError:
        try:
            import tempfile
            temp_audit = Path(tempfile.gettempdir()) / "claude-hook-audit.log"
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] [{hook_name}] {message}\n"
            with open(temp_audit, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except OSError:
            print(
                f"[{hook_name}] CRITICAL: All audit log paths failed. "
                f"Original message: {message}",
                file=sys.stderr,
            )


def _is_valid_project_root(cwd: str) -> bool:
    """Check if cwd has .claude/settings.json or .git."""
    indicators = [".claude/settings.json", ".git"]
    for indicator in indicators:
        if os.path.exists(os.path.join(cwd, indicator)):
            return True
    return False


def _get_today_session_log(sessions_dir: str) -> str | None:
    """Find the most recent session log for today."""
    today = datetime.date.today().strftime("%Y-%m-%d")

    if not os.path.isdir(sessions_dir):
        return None

    try:
        pattern = f"{today}-session-"
        logs = []
        for entry in os.listdir(sessions_dir):
            if entry.startswith(pattern) and entry.endswith(".json"):
                full_path = os.path.join(sessions_dir, entry)
                if os.path.isfile(full_path):
                    logs.append(full_path)
        if not logs:
            return None
        logs.sort(reverse=True)
        return logs[0]
    except OSError as exc:
        print(
            f"Invoke-RoutingGates: Failed to read session logs: {exc}",
            file=sys.stderr,
        )
        _write_audit_log("RoutingGates", f"Session log read error: {exc}")
        return None


def _test_qa_evidence(cwd: str) -> bool:
    """Check for QA evidence in reports or session log."""
    qa_dir = os.path.join(cwd, ".agents", "qa")
    if os.path.isdir(qa_dir):
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        try:
            for entry in os.listdir(qa_dir):
                if entry.endswith(".md"):
                    full_path = os.path.join(qa_dir, entry)
                    if os.path.isfile(full_path):
                        mtime = datetime.datetime.fromtimestamp(
                            os.path.getmtime(full_path)
                        )
                        if mtime > cutoff:
                            return True
        except OSError:
            pass

    sessions_dir = os.path.join(cwd, ".agents", "sessions")
    session_log = _get_today_session_log(sessions_dir)
    if session_log:
        try:
            with open(session_log, "r", encoding="utf-8") as f:
                content = f.read()
            if content:
                qa_pattern = re.compile(
                    r"(?i)## QA|qa agent|Test Results|QA Validation|Test Strategy"
                )
                if qa_pattern.search(content):
                    return True
        except OSError as exc:
            print(
                f"Invoke-RoutingGates: Session log exists but cannot be read: {exc}",
                file=sys.stderr,
            )
            _write_audit_log("RoutingGates", f"Session log read failed: {exc}")

    return False


def _test_documentation_only(cwd: str) -> bool:
    """Check if all changed files are documentation-only."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "diff", "--name-only", "origin/main"],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=30,
            )
            if result.returncode != 0:
                error_msg = (
                    f"git diff failed (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )
                print(
                    f"Invoke-RoutingGates: {error_msg}. Failing closed.",
                    file=sys.stderr,
                )
                _write_audit_log("RoutingGates", error_msg)
                return False

        changed_files = [
            f for f in result.stdout.strip().splitlines() if f.strip()
        ]
        if not changed_files:
            return True

        doc_pattern = re.compile(
            r"\.md$|\.txt$|(^|/)README$|(^|/)LICENSE$|(^|/)CHANGELOG$|\.gitignore$"
        )
        code_files = [f for f in changed_files if not doc_pattern.search(f)]
        return len(code_files) == 0

    except PermissionError as exc:
        error_msg = f"Permission denied checking git diff: {exc}"
        print(
            f"Invoke-RoutingGates: {error_msg}. Failing closed.",
            file=sys.stderr,
        )
        _write_audit_log("RoutingGates", error_msg)
        return False
    except OSError as exc:
        error_msg = f"I/O error checking git diff: {exc}"
        print(
            f"Invoke-RoutingGates: {error_msg}. Failing closed.",
            file=sys.stderr,
        )
        _write_audit_log("RoutingGates", error_msg)
        return False
    except subprocess.TimeoutExpired:
        error_msg = "git diff timed out"
        print(
            f"Invoke-RoutingGates: {error_msg}. Failing closed.",
            file=sys.stderr,
        )
        _write_audit_log("RoutingGates", error_msg)
        return False


def main() -> int:
    """Main hook entry point. Returns exit code."""
    input_text = sys.stdin.read()
    command = ""

    # Determine cwd from input or fall back to os.getcwd()
    cwd = os.getcwd()

    try:
        input_data = json.loads(input_text)
        if input_data.get("cwd"):
            cwd = input_data["cwd"]
        tool_input = input_data.get("tool_input", {})
        if isinstance(tool_input, dict):
            command = tool_input.get("command", "")
    except (json.JSONDecodeError, TypeError, AttributeError):
        print(
            "Invoke-RoutingGates: Failed to parse input JSON. "
            "Assuming empty command and allowing action.",
            file=sys.stderr,
        )
        command = ""

    if not _is_valid_project_root(cwd):
        print(
            f"Invoke-RoutingGates: CWD '{cwd}' does not appear to be a "
            "project root. Failing open.",
            file=sys.stderr,
        )
        return 0

    # Gate 2: QA Validation (for PR creation)
    if "gh pr create" in command:
        # Bypass 1: Environment variable override
        if os.environ.get("SKIP_QA_GATE") == "true":
            _write_audit_log(
                "RoutingGates",
                "QA gate bypassed via SKIP_QA_GATE environment variable",
            )
            return 0

        # Bypass 2: Documentation-only changes
        if _test_documentation_only(cwd):
            return 0

        # Main check: QA evidence required
        if not _test_qa_evidence(cwd):
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
            print(json.dumps(output))
            return 0  # JSON output with deny decision

    return 0


if __name__ == "__main__":
    sys.exit(main())
