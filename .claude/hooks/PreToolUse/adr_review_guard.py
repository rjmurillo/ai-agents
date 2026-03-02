#!/usr/bin/env python3
"""Blocks git commit with ADR changes unless adr-review skill was executed.

Claude Code PreToolUse hook that enforces ADR review before commit.
Detects ADR file modifications and blocks commit unless the adr-review
skill ran in the current session.

Checks:
1. Command is git commit
2. Changes include ADR files (ADR-*.md)
3. Session log contains adr-review evidence
4. adr-review output shows multi-agent consensus

Part of Tier 2 enforcement hooks (Issue #773, ADR review enforcement).

Hook Type: PreToolUse
Exit Codes:
    0 = Allow (not commit, or no ADR changes, or review done)
    2 = Block (ADR changes without review)
"""

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _write_audit_log(hook_name: str, message: str) -> None:
    """Write hook events to persistent audit log."""
    try:
        script_dir = Path(__file__).resolve().parent
        hook_dir = script_dir.parent
        audit_log_path = hook_dir / "audit.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{hook_name}] {message}\n"
        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except OSError:
        print(
            f"[{hook_name}] CRITICAL: Audit log write failed. "
            f"Original message: {message}",
            file=sys.stderr,
        )


def _get_project_directory() -> str:
    """Resolve project root directory."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir

    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent

    return str(Path.cwd())


def _is_git_commit_command(command: str) -> bool:
    """Test if a command string is a git commit command."""
    if not command or not command.strip():
        return False
    return bool(re.search(r"(?:^|\s)git\s+(commit|ci)", command))


def _get_staged_adr_changes() -> list[str]:
    """Get list of staged ADR file changes. Raises on git errors (fail-closed)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git diff --cached failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )

    if not result.stdout.strip():
        return []

    adr_pattern = re.compile(r"ADR-\d+\.md$", re.IGNORECASE)
    staged_files = result.stdout.strip().splitlines()
    return [f for f in staged_files if adr_pattern.search(f)]


def _get_today_session_log(sessions_dir: str, today: str) -> str | None:
    """Find the most recent session log for given date."""
    if not os.path.isdir(sessions_dir):
        return None

    try:
        pattern_prefix = f"{today}-session-"
        logs = []
        for entry in os.listdir(sessions_dir):
            if entry.startswith(pattern_prefix) and entry.endswith(".json"):
                full_path = os.path.join(sessions_dir, entry)
                if os.path.isfile(full_path):
                    logs.append(full_path)
        if not logs:
            return None
        logs.sort(reverse=True)
        return logs[0]
    except OSError:
        return None


def _test_adr_review_evidence(
    session_log_path: str, project_dir: str
) -> dict:
    """Check session log for ADR review evidence."""
    try:
        with open(session_log_path, "r", encoding="utf-8") as f:
            content = f.read()

        patterns = [
            r"/adr-review",
            r"adr-review skill",
            r"ADR Review Protocol",
            r"(?s)multi-agent consensus.{0,200}\bADR\b",
            r"(?s)\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b",
        ]

        found_pattern = False
        matched_pattern = ""

        for pattern in patterns:
            if re.search(pattern, content):
                found_pattern = True
                matched_pattern = pattern
                break

        if not found_pattern:
            return {
                "complete": False,
                "reason": "No adr-review evidence in session log",
            }

        # Verify debate log artifact exists
        analysis_dir = os.path.join(project_dir, ".agents", "analysis")
        if os.path.isdir(analysis_dir):
            debate_logs = [
                f
                for f in os.listdir(analysis_dir)
                if "debate" in f.lower() and f.endswith(".md")
            ]
            if not debate_logs:
                return {
                    "complete": False,
                    "reason": (
                        "Session log mentions adr-review, but no debate log "
                        "artifact found in .agents/analysis/"
                    ),
                }
        else:
            return {
                "complete": False,
                "reason": (
                    "Session log mentions adr-review, but "
                    ".agents/analysis/ directory does not exist"
                ),
            }

        return {
            "complete": True,
            "evidence": (
                f"ADR review evidence found: matched pattern "
                f"'{matched_pattern}' and debate log artifact exists"
            ),
        }

    except PermissionError:
        return {
            "complete": False,
            "reason": (
                "Session log is locked or you lack permissions. "
                "Close editors and retry."
            ),
        }
    except FileNotFoundError:
        return {
            "complete": False,
            "reason": (
                "Session log was deleted after detection. "
                "Create a new session log."
            ),
        }
    except (ValueError, KeyError):
        return {
            "complete": False,
            "reason": (
                "Session log contains invalid data. "
                "Check file format or recreate."
            ),
        }
    except OSError as exc:
        return {
            "complete": False,
            "reason": f"Error reading session log: {type(exc).__name__} - {exc}",
        }


def _format_block_message(adr_changes: list[str], problem: str = "",
                          session_log_name: str = "") -> str:
    """Format the blocking message for ADR changes without review."""
    changes_list = "\n".join(adr_changes)
    msg = (
        "\n## BLOCKED: ADR Changes Without Review\n\n"
        "**YOU MUST run /adr-review before committing ADR changes.**\n\n"
        "### Changes Detected\n\n"
        f"{changes_list}\n\n"
    )
    if problem:
        msg += f"### Problem\n\n{problem}\n\n"
    msg += (
        "### Required Action\n\n"
        "Invoke the adr-review skill for multi-agent consensus:\n\n"
        "```\n/adr-review [ADR-path]\n```\n\n"
        "This ensures 6-agent debate (architect, critic, independent-thinker, "
        "security, analyst, high-level-advisor) before ADR acceptance.\n\n"
        "**Why**: ADR changes impact system architecture. Multi-agent review "
        "prevents oversights and catches edge cases.\n\n"
        "**Skill**: `.claude/skills/adr-review/SKILL.md`\n"
    )
    if session_log_name:
        msg += f"**Session Log**: {session_log_name}\n"
    return msg


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")

        if not sys.stdin.readable():
            return 0

        input_json = sys.stdin.read()
        if not input_json or not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        tool_input = hook_input.get("tool_input", {})
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command", "")

        if not _is_git_commit_command(command):
            return 0

        # Check for ADR file changes (fail-closed on git errors)
        try:
            adr_changes = _get_staged_adr_changes()
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            error_msg = f"Staged ADR check failed (fail-closed): {exc}"
            print(error_msg, file=sys.stderr)
            _write_audit_log("ADRReviewGuard", error_msg)
            return 2

        if not adr_changes:
            return 0

        # ADR changes detected, verify review was done
        project_dir = _get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")
        session_log = _get_today_session_log(sessions_dir, today)

        if session_log is None:
            msg = _format_block_message(adr_changes)
            print(msg)
            print(
                "Session blocked: ADR changes without review",
                file=sys.stderr,
            )
            return 2

        evidence = _test_adr_review_evidence(session_log, project_dir)

        if not evidence.get("complete"):
            session_name = os.path.basename(session_log)
            problem = (
                f"{evidence.get('reason', 'Unknown')}. "
                "Session log needs evidence of /adr-review execution."
            )
            msg = _format_block_message(
                adr_changes,
                problem=problem,
                session_log_name=session_name,
            )
            print(msg)
            print(
                "Session blocked: ADR review not completed in session",
                file=sys.stderr,
            )
            return 2

        # Review evidence found, allow commit
        return 0

    except Exception as exc:
        # Fail-open on infrastructure errors
        error_msg = f"ADR review guard error: {type(exc).__name__} - {exc}"
        print(error_msg, file=sys.stderr)
        _write_audit_log("ADRReviewGuard", error_msg)
        return 0


if __name__ == "__main__":
    sys.exit(main())
