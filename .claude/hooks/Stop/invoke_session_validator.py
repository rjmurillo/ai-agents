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

import os
import sys

# Plugin mode: skip project-specific enforcement in consumer repos
if os.environ.get("CLAUDE_PLUGIN_ROOT"):
    sys.exit(0)

import json  # noqa: E402
import re  # noqa: E402  # Used by PLACEHOLDER_PATTERNS
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

REQUIRED_JSON_KEYS = (
    "session",
    "protocolCompliance",
    "work",
    "outcomes",
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
            sessions_path.glob(f"{today}-session-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return {"directory_missing": True}

    if not logs:
        return {"log_missing": True, "today": today}

    return logs[0]


def get_missing_keys(log_content: str) -> list[str]:
    """Check for missing or incomplete required JSON keys.

    Parses the session log as JSON and verifies required top-level keys exist
    and contain non-empty values.
    """
    try:
        data = json.loads(log_content)
    except (json.JSONDecodeError, ValueError):
        return ["Valid JSON structure (file is not valid JSON)"]

    if not isinstance(data, dict):
        return ["Valid JSON object (file is not a JSON object)"]

    missing: list[str] = []
    for key in REQUIRED_JSON_KEYS:
        if key not in data:
            missing.append(key)
        elif isinstance(data[key], dict) and not data[key]:
            missing.append(f"{key} (empty)")

    # Check if outcomes section has actual content
    outcomes = data.get("outcomes")
    if isinstance(outcomes, dict):
        has_placeholder = any(
            p.search(str(v)) for v in outcomes.values() for p in PLACEHOLDER_PATTERNS
        )
        if has_placeholder:
            missing.append("outcomes (contains placeholder text)")

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
                    f".agents/sessions/{today}-session-NN.json per SESSION-PROTOCOL.md"
                )
                return 0

        if not isinstance(result, Path):
            return 0
        log_path = result
        log_content = log_path.read_text(encoding="utf-8")
        missing_keys = get_missing_keys(log_content)

        if missing_keys:
            missing_list = ", ".join(missing_keys)
            write_continue_response(
                f"Session log incomplete in {log_path.name}. "
                f"Missing or incomplete keys: {missing_list}. "
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
