#!/usr/bin/env python3
"""Block git commit with ADR changes unless adr-review skill was executed.

Claude Code PreToolUse hook that enforces ADR review before commit.
Detects ADR file modifications and blocks commit unless the adr-review
skill ran in the current session.

Checks:
1. Command is git commit
2. Staged changes include ADR files (ADR-*.md)
3. Session log contains adr-review evidence
4. Debate log artifact exists in .agents/analysis/

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not commit, no ADR changes, or review done)
    2 = Block (ADR changes without review)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path for imports
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.hook_utilities.utilities import (  # noqa: E402
    get_project_directory,
    get_today_session_log,
    is_git_commit_command,
)

_ADR_PATTERN = re.compile(r"ADR-\d+\.md$", re.IGNORECASE)

_REVIEW_PATTERNS = [
    re.compile(r"/adr-review"),
    re.compile(r"adr-review skill"),
    re.compile(r"ADR Review Protocol"),
    re.compile(r"multi-agent consensus.{0,200}\bADR\b", re.DOTALL),
    re.compile(r"\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b", re.DOTALL),
]

_AGENTS_DEBATE = ".agents/analysis/"

_NO_SESSION_LOG_TEMPLATE = """\

## BLOCKED: ADR Changes Without Review

**YOU MUST run /adr-review before committing ADR changes.**

### Changes Detected

{changes_list}

### Required Action

Invoke the adr-review skill for multi-agent consensus:

```
/adr-review [ADR-path]
```

This ensures 6-agent debate before ADR acceptance.

**Skill**: `.claude/skills/adr-review/SKILL.md`
"""

_NO_EVIDENCE_TEMPLATE = """\

## BLOCKED: ADR Changes Without Review

**YOU MUST run /adr-review before committing ADR changes.**

### Changes Detected

{changes_list}

### Problem

{reason}. Session log needs evidence of /adr-review execution.

### Required Action

Invoke the adr-review skill for multi-agent consensus:

```
/adr-review [ADR-path]
```

This ensures 6-agent debate before ADR acceptance.

**Skill**: `.claude/skills/adr-review/SKILL.md`
**Session Log**: {session_log_name}
"""


def write_audit_log(message: str) -> None:
    """Write to the hook audit log for infrastructure error visibility."""
    try:
        hook_dir = Path(__file__).resolve().parents[1]
        audit_log_path = hook_dir / "audit.log"
        timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [ADRReviewGuard] {message}\n"
        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        print(
            f"[ADRReviewGuard] CRITICAL: Audit log write failed. Original error: {message}",
            file=sys.stderr,
        )


def get_staged_adr_changes() -> list[str]:
    """Get staged files that match the ADR naming pattern.

    Raises on git errors to maintain fail-closed posture for security.
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        msg = f"git diff --cached failed with exit code {result.returncode}: {stderr}"
        raise RuntimeError(msg)

    if not result.stdout.strip():
        return []

    return [f for f in result.stdout.strip().splitlines() if _ADR_PATTERN.search(f)]


def check_adr_review_evidence(
    session_log_path: Path,
    project_dir: str,
) -> dict[str, object]:
    """Check session log and artifacts for ADR review evidence.

    Returns dict with 'complete' (bool) and 'reason' or 'evidence' key.
    """
    try:
        content = session_log_path.read_text(encoding="utf-8")

        matched_pattern = None
        for pattern in _REVIEW_PATTERNS:
            if pattern.search(content):
                matched_pattern = pattern.pattern
                break

        if matched_pattern is None:
            return {
                "complete": False,
                "reason": "No adr-review evidence in session log",
            }

        analysis_dir = Path(project_dir) / ".agents" / "analysis"
        if not analysis_dir.is_dir():
            return {
                "complete": False,
                "reason": (
                    "Session log mentions adr-review, but "
                    f"{_AGENTS_DEBATE} directory does not exist"
                ),
            }

        debate_logs = list(analysis_dir.glob("*debate*.md"))
        if not debate_logs:
            return {
                "complete": False,
                "reason": (
                    "Session log mentions adr-review, but no debate "
                    f"log artifact found in {_AGENTS_DEBATE}"
                ),
            }

        return {
            "complete": True,
            "evidence": (
                "ADR review evidence found: matched pattern "
                f"'{matched_pattern}' and debate log artifact exists"
            ),
        }

    except PermissionError:
        return {
            "complete": False,
            "reason": ("Session log is locked or you lack permissions. Close editors and retry."),
        }
    except FileNotFoundError:
        return {
            "complete": False,
            "reason": ("Session log was deleted after detection. Create a new session log."),
        }
    except (ValueError, OSError) as exc:
        return {
            "complete": False,
            "reason": (f"Error reading session log: {type(exc).__name__} - {exc}"),
        }


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not command:
            return 0

        if not is_git_commit_command(command):
            return 0

        # Fail-closed: git errors block to prevent bypass.
        try:
            adr_changes = get_staged_adr_changes()
        except RuntimeError as exc:
            error_msg = f"Staged ADR check failed (fail-closed): {exc}"
            print(error_msg, file=sys.stderr)
            write_audit_log(error_msg)
            return 2

        if not adr_changes:
            return 0

        # ADR changes detected, verify review was done
        project_dir = get_project_directory()
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")
        session_log = get_today_session_log(sessions_dir, date=today)

        changes_list = "\n".join(adr_changes)

        if session_log is None:
            print(_NO_SESSION_LOG_TEMPLATE.format(changes_list=changes_list))
            print(
                "Session blocked: ADR changes without review",
                file=sys.stderr,
            )
            return 2

        evidence = check_adr_review_evidence(session_log, project_dir)

        if not evidence["complete"]:
            print(
                _NO_EVIDENCE_TEMPLATE.format(
                    changes_list=changes_list,
                    reason=evidence["reason"],
                    session_log_name=session_log.name,
                )
            )
            print(
                "Session blocked: ADR review not completed in session",
                file=sys.stderr,
            )
            return 2

        return 0

    except Exception as exc:
        # Fail-open on infrastructure errors
        error_msg = f"ADR review guard error: {type(exc).__name__} - {exc}"
        print(error_msg, file=sys.stderr)
        write_audit_log(error_msg)
        return 0


if __name__ == "__main__":
    sys.exit(main())
