#!/usr/bin/env python3
"""Stop hook that validates session log completeness before Claude stops.

Verifies the session log exists and contains required sections. If incomplete,
outputs a continue response so Claude keeps working until the session log is
properly completed per SESSION-PROTOCOL requirements.

Part of the hooks expansion implementation (Issue #773, Phase 2).

Hook Type: Stop
Exit Codes:
    0 = Always (non-blocking hook, all errors are warnings)

See: .agents/SESSION-PROTOCOL.md
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# Required sections in a session log
REQUIRED_SECTIONS: list[str] = [
    "## Session Context",
    "## Implementation Plan",
    "## Work Log",
    "## Decisions",
    "## Outcomes",
    "## Files Changed",
    "## Follow-up Actions",
]

# Placeholder patterns that indicate incomplete outcomes
PLACEHOLDER_PATTERNS: list[str] = [
    r"(?i)to be filled",
    r"(?i)tbd",
    r"(?i)todo",
    r"(?i)coming soon",
    r"(?i)\(pending\)",
    r"(?i)\[pending\]",
]


def get_project_directory(hook_input: dict) -> str:
    """Get project directory from env var or hook input cwd."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return env_dir
    return hook_input.get("cwd", os.getcwd())


def write_continue_response(reason: str) -> None:
    """Write a continue response as JSON to stdout."""
    response = json.dumps({"continue": True, "reason": reason})
    print(response)


def find_today_session_log(sessions_dir: str) -> dict:
    """Find session logs for today.

    Returns:
        Dict with one of:
        - {"directory_missing": True} if sessions dir doesn't exist
        - {"log_missing": True, "today": "YYYY-MM-DD"} if no log for today
        - {"path": str, "name": str} for the most recent log
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return {"directory_missing": True}

    today = date.today().isoformat()
    # The PowerShell original searches for .md files
    logs = sorted(
        sessions_path.glob(f"{today}-session-*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not logs:
        return {"log_missing": True, "today": today}

    return {"path": str(logs[0]), "name": logs[0].name}


def get_missing_sections(log_content: str) -> list[str]:
    """Find required sections missing from the session log.

    Also detects placeholder text in the Outcomes section.
    """
    missing = []
    for section in REQUIRED_SECTIONS:
        escaped = re.escape(section)
        if not re.search(escaped, log_content):
            missing.append(section)

    # Check Outcomes section for placeholders or insufficient content
    outcomes_match = re.search(
        r"## Outcomes(.*?)(?=\n##|\Z)", log_content, re.DOTALL
    )
    if outcomes_match:
        outcomes_text = outcomes_match.group(1)

        has_placeholder = any(
            re.search(p, outcomes_text) for p in PLACEHOLDER_PATTERNS
        )
        is_too_short = len(outcomes_text.strip()) < 50

        if has_placeholder or is_too_short:
            missing.append(
                "## Outcomes (section incomplete or contains placeholder text)"
            )

    return missing


def main() -> int:
    """Main hook execution. Always returns 0."""
    try:
        if sys.stdin.isatty():
            return 0

        input_text = sys.stdin.read()
        if not input_text or not input_text.strip():
            return 0

        hook_input = json.loads(input_text)
        project_dir = get_project_directory(hook_input)
        sessions_dir = os.path.join(project_dir, ".agents", "sessions")

        result = find_today_session_log(sessions_dir)

        if result.get("directory_missing"):
            # Project may not use sessions, exit silently
            return 0

        if result.get("log_missing"):
            today = result["today"]
            write_continue_response(
                f"Session log missing. MUST create session log at"
                f" .agents/sessions/{today}-session-NN.md per SESSION-PROTOCOL.md"
            )
            return 0

        # Read and validate session log content
        log_path = result["path"]
        log_name = result["name"]

        with open(log_path, encoding="utf-8") as f:
            log_content = f.read()

        missing_sections = get_missing_sections(log_content)

        if missing_sections:
            missing_list = ", ".join(missing_sections)
            write_continue_response(
                f"Session log incomplete in {log_name}."
                f" Missing or incomplete sections: {missing_list}."
                f" MUST complete per SESSION-PROTOCOL.md"
            )

        return 0

    except (OSError, PermissionError) as exc:
        print(f"Session validator file error: {exc}", file=sys.stderr)
        write_continue_response(
            f"Session validation failed: Cannot read session log."
            f" MUST investigate file system issue. Error: {exc}"
        )
        return 0

    except Exception as exc:
        print(
            f"Session validator unexpected error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        write_continue_response(
            f"Session validation encountered unexpected error."
            f" MUST investigate: {type(exc).__name__} - {exc}"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
