#!/usr/bin/env python3
"""Block false completion claims without verification evidence.

Claude Code PreToolUse hook that detects when agents claim "done", "fixed",
etc. in commit messages or PR operations without prior verification evidence
(test/build runs) in the session log.

Addresses 44 false completion mentions across 80+ retrospectives.

Gate triggers on:
- git commit messages containing completion signals
- gh pr create commands with completion language

Evidence requirements (any one satisfies):
1. Test run in session log (pytest, npm test, etc.)
2. Build verification in session log (tsc --noEmit, etc.)
3. PR checks verified (gh pr checks)

Bypass conditions:
- SKIP_COMPLETION_GATE=true environment variable
- Documentation-only changes (*.md files only)
- No session log present (fail-open)
- Non-commit/non-PR commands

Hook Type: PreToolUse (blocking on match)
Exit Codes (Claude Hook Semantics):
    0 = Allow (evidence exists or not a completion claim)
    2 = Block (completion claim without verification)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1673 (false completion)
    - ADR-008 (protocol automation)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# --- Standard hook boilerplate ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory, get_today_session_log
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
        if date is None:
            date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_path = Path(sessions_dir)
        if not sessions_path.is_dir():
            return None
        try:
            logs = sorted(
                sessions_path.glob(f"{date}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        return logs[0] if logs else None

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "false-completion-gate"

# Completion signal patterns in commit messages / PR titles
COMPLETION_SIGNALS = re.compile(
    r"\b(done|fixed|complete[ds]?|finished|resolved|merged|shipped|closes?\s+#\d+)\b",
    re.IGNORECASE,
)

# Verification evidence patterns in session logs
VERIFICATION_PATTERNS = [
    re.compile(r"pytest", re.IGNORECASE),
    re.compile(r"npm\s+test", re.IGNORECASE),
    re.compile(r"npm\s+run\s+test", re.IGNORECASE),
    re.compile(r"pnpm\s+test", re.IGNORECASE),
    re.compile(r"yarn\s+test", re.IGNORECASE),
    re.compile(r"tsc\s+--noEmit", re.IGNORECASE),
    re.compile(r"dotnet\s+test", re.IGNORECASE),
    re.compile(r"go\s+test", re.IGNORECASE),
    re.compile(r"gh\s+pr\s+checks", re.IGNORECASE),
    re.compile(r"Invoke-Pester", re.IGNORECASE),
    re.compile(r"uv\s+run\s+pytest", re.IGNORECASE),
    re.compile(r"make\s+test", re.IGNORECASE),
]


def _read_stdin_json() -> dict | None:
    """Read and parse JSON from stdin (Claude hook input)."""
    if sys.stdin.isatty():
        return None
    try:
        data = sys.stdin.read().strip()
        if not data:
            return None
        return json.loads(data)
    except (json.JSONDecodeError, OSError):
        return None


def _extract_command(hook_input: dict) -> str:
    """Extract the command string from hook input."""
    tool_input = hook_input.get("tool_input", {})
    return tool_input.get("command", "")


def _is_completion_claim(command: str) -> bool:
    """Check if a command contains completion signals."""
    return COMPLETION_SIGNALS.search(command) is not None


def _is_documentation_only(is_pr_create: bool) -> bool:
    """Check if changes are documentation-only.

    Args:
        is_pr_create: True if this is a `gh pr create` command, False for `git commit`.
                      For commits, checks staged changes (git diff --cached).
                      For PRs, checks branch diff against the merge base.
    """
    try:
        if is_pr_create:
            # For PR create, get the branch diff against the merge base
            # First, find the merge base with the default branch
            base_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if base_result.returncode != 0:
                return False

            # Try to find merge-base with common default branches
            for default_branch in ["main", "master", "develop"]:
                merge_base_result = subprocess.run(
                    ["git", "merge-base", default_branch, "HEAD"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if merge_base_result.returncode == 0:
                    merge_base = merge_base_result.stdout.strip()
                    result = subprocess.run(
                        ["git", "diff", "--name-only", merge_base, "HEAD"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    break
            else:
                # No default branch found, fall back to staged changes
                result = subprocess.run(
                    ["git", "diff", "--cached", "--name-only"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
        else:
            # For commits, check staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode != 0:
            return False
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        if not files:
            return False
        return all(f.endswith(".md") for f in files)
    except OSError:
        return False


def _has_verification_evidence(session_log: Path) -> bool:
    """Check session log for test/build verification evidence.

    Args:
        session_log: Path to the session log file. Caller must ensure this is not None.
    """
    try:
        content = session_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    for pattern in VERIFICATION_PATTERNS:
        if pattern.search(content):
            return True
    return False


def _write_audit_log(project_dir: str, command: str, decision: str, reason: str) -> None:
    """Write audit entry for false completion gate decisions."""
    try:
        audit_dir = Path(project_dir) / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        timestamp = datetime.now(tz=UTC).isoformat()
        audit_file = audit_dir / f"false-completion-gate-{today}.log"

        # Truncate command for audit (avoid huge log entries)
        cmd_preview = command[:200] + "..." if len(command) > 200 else command

        with audit_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {decision}: {reason} | cmd: {cmd_preview}\n")
    except OSError:
        pass


def main() -> None:
    """Check for false completion claims without verification."""
    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    # Bypass via environment variable
    if os.environ.get("SKIP_COMPLETION_GATE", "").lower() == "true":
        sys.exit(0)

    hook_input = _read_stdin_json()
    if hook_input is None:
        sys.exit(0)

    command = _extract_command(hook_input)
    if not command:
        sys.exit(0)

    # Only gate on git commit and gh pr create commands
    is_commit = re.search(r"(?:^|\s)git\s+(commit|ci)", command)
    is_pr_create = re.search(r"gh\s+pr\s+create", command)
    if not is_commit and not is_pr_create:
        sys.exit(0)

    # Check if the command/message contains completion signals
    if not _is_completion_claim(command):
        sys.exit(0)

    project_dir = get_project_directory()

    # Bypass for documentation-only changes
    if _is_documentation_only(is_pr_create=bool(is_pr_create)):
        _write_audit_log(project_dir, command, "ALLOW", "documentation-only changes")
        sys.exit(0)

    # Check for verification evidence in session log
    sessions_dir = str(Path(project_dir) / ".agents" / "sessions")
    session_log = get_today_session_log(sessions_dir)

    # Fail-open when no session log exists
    if session_log is None:
        _write_audit_log(project_dir, command, "ALLOW", "no session log (fail-open)")
        sys.exit(0)

    if _has_verification_evidence(session_log):
        _write_audit_log(project_dir, command, "ALLOW", "verification evidence found")
        sys.exit(0)

    # Block: completion claim without verification
    _write_audit_log(project_dir, command, "BLOCK", "completion claim without verification")

    block_response = json.dumps({
        "decision": "block",
        "reason": (
            "⛔ FALSE COMPLETION GATE: You claimed completion "
            "(done/fixed/complete/etc.) but no verification evidence "
            "(test run, build check, PR checks) was found in the session log. "
            "Run tests or build verification before claiming completion."
        ),
    })
    print(block_response)
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open on unexpected errors
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
