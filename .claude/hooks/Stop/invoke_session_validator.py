#!/usr/bin/env python3
"""Validate session log completeness before Claude stops responding.

Claude Code Stop hook that verifies the session log exists and contains
required sections. If incomplete, forces Claude to continue working until
the session log is properly completed per SESSION-PROTOCOL requirements.

Part of the hooks expansion implementation (Issue #773, Phase 2).

Hook Type: Stop
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_SECTIONS = (
    "## Session Context",
    "## Implementation Plan",
    "## Work Log",
    "## Decisions",
    "## Outcomes",
    "## Files Changed",
    "## Follow-up Actions",
)

PLACEHOLDER_PATTERNS = (
    re.compile(r"(?i)to be filled"),
    re.compile(r"(?i)tbd"),
    re.compile(r"(?i)todo"),
    re.compile(r"(?i)coming soon"),
    re.compile(r"(?i)\(pending\)"),
    re.compile(r"(?i)\[pending\]"),
)


def write_continue_response(reason: str) -> None:
    """Write a JSON response that tells Claude to continue working."""
    response = json.dumps({"continue": True, "reason": reason})
    print(response)


def get_project_directory(hook_input: dict[str, object]) -> str:
    """Get project directory from environment or hook input."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir
    cwd = hook_input.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    return os.getcwd()


def get_today_session_logs(sessions_dir: str) -> dict[str, object] | Path:
    """Find today's session logs.

    Returns:
        dict with 'directory_missing' or 'log_missing' keys on failure,
        or a Path to the most recent log file on success.
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return {"directory_missing": True}

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    try:
        logs = sorted(
            sessions_path.glob(f"{today}-session-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return {"directory_missing": True}

    if not logs:
        return {"log_missing": True, "today": today}

    return logs[0]


def get_missing_sections(log_content: str) -> list[str]:
    """Check for missing or incomplete required sections."""
    missing: list[str] = []

    for section in REQUIRED_SECTIONS:
        if re.escape(section).replace(r"\ ", " ") not in log_content:
            # Direct string check
            if section not in log_content:
                missing.append(section)

    # Check if Outcomes section is incomplete
    outcomes_match = re.search(r"## Outcomes(.*?)(?=\n##|\Z)", log_content, re.DOTALL)
    if outcomes_match:
        outcomes_text = outcomes_match.group(1)

        has_placeholder = any(p.search(outcomes_text) for p in PLACEHOLDER_PATTERNS)
        is_too_short = len(outcomes_text.strip()) < 50

        if has_placeholder or is_too_short:
            missing.append("## Outcomes (section incomplete or contains placeholder text)")

    return missing


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
        project_dir = get_project_directory(hook_input)
        sessions_dir = str(Path(project_dir) / ".agents" / "sessions")

        result = get_today_session_logs(sessions_dir)

        if isinstance(result, dict):
            if result.get("directory_missing"):
                return 0
            if result.get("log_missing"):
                today = result.get("today", "unknown")
                write_continue_response(
                    f"Session log missing. MUST create session log at "
                    f".agents/sessions/{today}-session-NN.md per SESSION-PROTOCOL.md"
                )
                return 0

        # result is a Path at this point
        log_path: Path = result  # type: ignore[assignment]
        log_content = log_path.read_text(encoding="utf-8")
        missing_sections = get_missing_sections(log_content)

        if missing_sections:
            missing_list = ", ".join(missing_sections)
            write_continue_response(
                f"Session log incomplete in {log_path.name}. "
                f"Missing or incomplete sections: {missing_list}. "
                f"MUST complete per SESSION-PROTOCOL.md"
            )

        return 0

    except (OSError, PermissionError) as exc:
        print(f"Session validator file error: {exc}", file=sys.stderr)
        write_continue_response(
            f"Session validation failed: Cannot read session log. "
            f"MUST investigate file system issue. Error: {exc}"
        )
        return 0

    except Exception as exc:
        print(
            f"Session validator unexpected error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        write_continue_response(
            f"Session validation encountered unexpected error. "
            f"MUST investigate: {type(exc).__name__} - {exc}"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
