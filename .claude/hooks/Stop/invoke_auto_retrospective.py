#!/usr/bin/env python3
"""
Stop hook: Auto-generates retrospective on session end.

Creates a structured retrospective template in .agents/retrospective/ and
updates docs/retros/INDEX.md with a new entry.

Hook Type: Stop (non-blocking, always exits 0)
Exit Codes: Always 0 (fail-open — never blocks session stop)

Bypass: SKIP_AUTO_RETRO=true environment variable

Related:
- Issue #1703 (lifecycle hook infrastructure)
- ADR-008 (protocol automation lifecycle hooks)
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import coerce_to_list as _coerce_to_list
    from hook_utilities import get_project_directory as _get_project_directory
    from hook_utilities import get_recent_session_log as _get_recent_session_log
    from hook_utilities import lock_file as _lock_file
    from hook_utilities import unlock_file as _unlock_file
    from hook_utilities.guards import skip_if_consumer_repo

    def get_project_directory() -> Path | None:
        """Wrap shared utility returning Path for backward compat."""
        result = _get_project_directory()
        return Path(result) if result else None

except ImportError:
    # Fallback if hook_utilities not available
    def get_project_directory() -> Path | None:
        """Resolve project root from env or git."""
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if env_dir:
            return Path(env_dir)
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return None

    def skip_if_consumer_repo(hook_name: str) -> bool:  # type: ignore[misc]
        """Fallback guard when hook_utilities is unavailable."""
        project_dir = get_project_directory()
        if not project_dir or not (project_dir / ".agents").is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False

    _get_recent_session_log = None  # type: ignore[assignment]
    _coerce_to_list = None  # type: ignore[assignment]
    _lock_file = None  # type: ignore[assignment]
    _unlock_file = None  # type: ignore[assignment]


def has_retro_today(retro_dir: Path, today: str) -> bool:
    """Check if a retrospective already exists for today."""
    if not retro_dir.is_dir():
        return False
    return any(retro_dir.glob(f"{today}*.md"))


def _find_recent_session_fallback(sessions_dir: Path, today_only: bool = False) -> Path | None:
    """Fallback session lookup when hook_utilities is unavailable.

    Args:
        sessions_dir: Directory containing session logs.
        today_only: If True, only return today's sessions (no yesterday fallback).
    """
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")

    # First, check for today's sessions
    today_candidates = list(sessions_dir.glob(f"{today}-session-*.json"))
    if today_candidates:
        try:
            return max(today_candidates, key=lambda f: f.stat().st_mtime)
        except OSError:
            return None

    if today_only:
        return None

    # Only fall back to yesterday if no today session exists (cross-midnight continuation)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_candidates = list(sessions_dir.glob(f"{yesterday}-session-*.json"))
    if yesterday_candidates:
        try:
            return max(yesterday_candidates, key=lambda f: f.stat().st_mtime)
        except OSError:
            return None

    return None


def find_recent_session_file(sessions_dir: Path, today_only: bool = False) -> Path | None:
    """Find the most recent session file for the current session.

    Only falls back to yesterday's session if NO today-prefixed session exists,
    preventing stale data from yesterday being attributed to today.

    Args:
        sessions_dir: Directory containing session logs.
        today_only: If True, only return today's sessions (no yesterday fallback).
    """
    # The shared utility doesn't support today_only, so use fallback for that case
    if today_only or _get_recent_session_log is None:
        return _find_recent_session_fallback(sessions_dir, today_only=today_only)

    # For non-today_only case, we still need to implement the "prefer today" logic
    # since the shared utility doesn't do this
    return _find_recent_session_fallback(sessions_dir, today_only=False)


def _coerce_to_list_fallback(value) -> list:
    """Fallback normalizer when hook_utilities is unavailable."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("tasks", "items", "log", "entries"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
        for v in value.values():
            if isinstance(v, list):
                return v
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def coerce_to_list(value) -> list:
    """Normalize work/outcomes to a list, regardless of session schema shape.

    Session logs in this repo have used several shapes over time:
    - ``work: [...]`` (legacy flat list)
    - ``work: {tasks: [...]}`` / ``{items: [...]}`` (dict wrapper)
    - ``workLog: [...]`` (current schema)
    - bare strings (rare)
    """
    if _coerce_to_list is not None:
        return _coerce_to_list(value)
    return _coerce_to_list_fallback(value)


def _format_work_item(item: dict) -> str:
    """Format a work item dict into a human-readable string.

    Supports multiple session schemas:
    - Current: {'step': N, 'action': '...', 'outcome': '...'}
    - Legacy: {'description': '...'} or {'task': '...'}
    """
    # Try current schema (step/action/outcome)
    if "action" in item:
        parts = []
        if "step" in item:
            parts.append(f"Step {item['step']}:")
        parts.append(item["action"])
        if "outcome" in item:
            parts.append(f"→ {item['outcome']}")
        return " ".join(parts)
    # Try legacy schemas
    if "description" in item:
        return item["description"]
    if "task" in item:
        return item["task"]
    # Fallback to repr
    return str(item)


def _extract_work_outcomes(data) -> tuple[list, list]:
    """Pull work and outcomes from session data, supporting workLog and work shapes."""
    if not isinstance(data, dict):
        return [], []
    work_raw = data.get("workLog")
    if not work_raw:
        work_raw = data.get("work", [])
    outcomes_raw = data.get("outcomes", [])
    return coerce_to_list(work_raw), coerce_to_list(outcomes_raw)


def is_trivial_session(project_dir: Path, today: str) -> bool:
    """Check if session is trivial (no meaningful work done today).

    Only considers today's session to avoid attributing yesterday's work to today.
    """
    sessions_dir = project_dir / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return True

    # Only look at today's sessions to avoid misattributing yesterday's work
    session_file = find_recent_session_file(sessions_dir, today_only=True)
    if not session_file:
        return True

    try:
        content = session_file.read_text(encoding="utf-8")
        data = json.loads(content)
        work, outcomes = _extract_work_outcomes(data)
        return len(work) == 0 and len(outcomes) == 0
    except Exception as e:
        # Fail-open on any parse/IO error; surface to stderr for diagnosability.
        print(
            f"[hook-error] invoke_auto_retrospective is_trivial_session: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return True


def generate_retrospective(project_dir: Path, today: str) -> Path | None:
    """Generate a structured retrospective file."""
    retro_dir = project_dir / ".agents" / "retrospective"
    retro_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{today}-auto-retro.md"
    retro_path = retro_dir / filename

    # Only pull context from today's session log to avoid misattributing yesterday's work
    session_context = ""
    sessions_dir = project_dir / ".agents" / "sessions"
    if sessions_dir.is_dir():
        session_file = find_recent_session_file(sessions_dir, today_only=True)
        if session_file:
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                work_items, outcomes = _extract_work_outcomes(data)
                if work_items:
                    session_context += "### Work Items\n"
                    for item in work_items[:10]:
                        if isinstance(item, str):
                            session_context += f"- {item}\n"
                        elif isinstance(item, dict):
                            session_context += f"- {_format_work_item(item)}\n"
                if outcomes:
                    session_context += "\n### Outcomes\n"
                    for outcome in outcomes[:10]:
                        if isinstance(outcome, str):
                            session_context += f"- {outcome}\n"
                        elif isinstance(outcome, dict):
                            session_context += f"- {outcome.get('result', str(outcome))}\n"
            except Exception as e:
                print(
                    f"[hook-error] invoke_auto_retrospective generate_retrospective: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )

    content = f"""# Retrospective: {today}

> Auto-generated by invoke_auto_retrospective.py (Stop hook)

## Session Context

{session_context if session_context else "_No session log data available._"}

## What Went Well

- _[To be filled by reviewing agent or human]_

## What Could Improve

- _[To be filled by reviewing agent or human]_

## Key Learnings

- _[To be filled by reviewing agent or human]_

## Failure Patterns

- _[To be filled: check against known patterns in .agents/failure-modes/]_
"""

    retro_path.write_text(content, encoding="utf-8")
    return retro_path


def update_retro_index(project_dir: Path, today: str, filename: str) -> None:
    """Append entry to docs/retros/INDEX.md, creating if needed."""
    index_dir = project_dir / "docs" / "retros"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "INDEX.md"

    header = "# Retrospective Index\n\n| Date | File | Summary |\n|------|------|---------|"

    # Append new row (advisory lock to prevent interleaved writes from parallel sessions)
    # Open with "a+b" to atomically create if missing, then lock before any read/write
    row = f"| {today} | {filename} | Auto-generated session retro |"
    with open(index_path, "a+b") as f:
        if _lock_file is not None:
            _lock_file(f)
        try:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0:
                # File was just created, write header
                f.write((header + "\n").encode("utf-8"))
            else:
                f.seek(-1, os.SEEK_END)
                last_byte = f.read(1)
                if last_byte != b"\n":
                    f.write(b"\n")
            f.write((row + "\n").encode("utf-8"))
        finally:
            if _unlock_file is not None:
                _unlock_file(f)


def main() -> int:
    """Generate retrospective on session stop."""
    # Skip for consumer repos (avoid creating directories outside .agents/)
    if skip_if_consumer_repo("auto-retrospective"):
        return 0

    # Bypass
    if os.environ.get("SKIP_AUTO_RETRO", "").lower() == "true":
        return 0

    # Skip if stdin is TTY
    if sys.stdin.isatty():
        return 0

    # Read stdin (consume it)
    try:
        sys.stdin.read()
    except Exception as e:
        print(f"[hook-error] invoke_auto_retrospective stdin: {type(e).__name__}: {e}", file=sys.stderr)

    project_dir = get_project_directory()
    if not project_dir:
        return 0

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    retro_dir = project_dir / ".agents" / "retrospective"

    # Idempotent: skip if retro already exists today
    if has_retro_today(retro_dir, today):
        return 0

    # Skip trivial sessions (only considers today's work to avoid misattribution)
    if is_trivial_session(project_dir, today):
        return 0

    try:
        retro_path = generate_retrospective(project_dir, today)
        if retro_path:
            update_retro_index(project_dir, today, retro_path.name)
    except Exception as e:
        # Broad catch preserves fail-open contract; surface to stderr.
        print(
            f"[hook-error] invoke_auto_retrospective main: {type(e).__name__}: {e}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
