#!/usr/bin/env python3
"""Checkpoint work-in-progress state before context compaction.

Claude Code PreCompact hook that snapshots the current work state before
context is compacted, providing a resume context for the post-compaction
session.

Builds a resume-context string from the current session log (name, open
TODO items, git branch) and prints it to stdout for injection into the
post-compaction session. The stdout injection is the sole product; no
on-disk checkpoint artifact is written (ADR-082, issue #3217).

Hook Type: PreCompact (non-blocking, fail-open)
Exit Codes:
    0 = Always (never blocks compaction)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1691 (anti-drift protocol)
    - ADR-008 (protocol automation)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _fallback_get_recent_session_log(sessions_dir: str) -> Path | None:
    """Return the newest readable session log from today or yesterday.

    Runs only when ``hook_utilities`` cannot be imported. The repository
    canonical source is
    ``scripts/hook_utilities/utilities.py::recent_host_session_dates``::

        current = now()
        today = current.strftime(_ISO_DATE)
        yesterday = (current - timedelta(days=1)).strftime(_ISO_DATE)
        return today, yesterday

    The installed plugin mirrors that helper at
    ``lib/hook_utilities/utilities.py``. Unlike canonical, this fallback uses
    inline ``datetime.now()`` and skips a date after a glob error instead of
    warning and returning ``None``. Both use host-local dates (Issue #4779).
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return None

    now = datetime.now()  # host-local date authority (Issue #4779)
    for offset in (0, 1):
        date = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            candidates = list(sessions_path.glob(f"{date}-session-*.json"))
        except OSError:
            continue

        newest: Path | None = None
        newest_mtime = float("-inf")
        for candidate in candidates:
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime > newest_mtime:
                newest = candidate
                newest_mtime = mtime
        if newest is not None:
            return newest
    return None


# --- Standard hook boilerplate ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory, get_recent_session_log
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:
    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    get_recent_session_log = _fallback_get_recent_session_log

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "compact-checkpoint"


def _get_current_branch() -> str:
    """Get the current git branch name.

    Uses ``git -C`` to bind the call to the project directory rather
    than relying on the hook process CWD, and applies a short timeout
    so a stuck git index lock cannot hang the PreCompact gate.
    """
    project_dir = get_project_directory()
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else "(detached)"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "(unknown)"


def _extract_open_items(session_log: Path) -> list[str]:
    """Extract open/incomplete work items from a session log.

    Supports the legacy ``work: [{description, status}, ...]`` shape, the
    current ``workLog`` schema, and the observed ``work: { tasks: [...] }``
    shape (see ``.agents/sessions/2026-02-08-session-1194.json``).
    Items whose ``status`` is done/complete/completed are excluded.
    """
    items: list[str] = []

    def _append_open_items(entries: object) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if isinstance(entry, dict):
                status = str(entry.get("status", "")).lower()
                if status in ("done", "complete", "completed"):
                    continue
                # Prefer description, then task, then action, then step.
                # Skip entries whose values are missing or empty rather than
                # appending "None" / blank strings that pollute the resume context.
                desc = (
                    entry.get("description")
                    or entry.get("task")
                    or entry.get("action")
                    or entry.get("step")
                )
                if isinstance(desc, str):
                    stripped = desc.strip()
                    if stripped:
                        items.append(stripped)
            elif isinstance(entry, str):
                stripped = entry.strip()
                if stripped:
                    items.append(stripped)

    try:
        content = session_log.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError):
        return items

    if not isinstance(data, dict):
        return items

    work = data.get("work", [])
    if isinstance(work, list):
        _append_open_items(work)
    elif isinstance(work, dict):
        _append_open_items(work.get("tasks", []))

    _append_open_items(data.get("workLog", []))
    return items


def _drain_stdin() -> None:
    """Drain stdin to prevent pipe buffer blocking on the harness side.

    Even when this hook does not need input data, consuming stdin keeps
    the fail-open contract with the harness: an unconsumed pipe can leave
    the producer blocked or trigger EPIPE/SIGPIPE when the hook exits.
    """
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except OSError:
            pass


def main() -> None:
    """Snapshot state before context compaction."""
    _drain_stdin()

    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    project_dir = get_project_directory()
    project_path = Path(project_dir)

    # Get session log (supports cross-midnight sessions via yesterday fallback)
    sessions_dir = str(project_path / ".agents" / "sessions")
    session_log = get_recent_session_log(sessions_dir)

    session_log_name = session_log.name if session_log else "(none)"

    # Get open items
    open_items = _extract_open_items(session_log) if session_log else []

    # Get branch
    branch = _get_current_branch()

    # Build resume context
    timestamp = datetime.now(tz=UTC).isoformat()
    item_count = len(open_items)
    resume_context = (
        f"Compaction occurred at {timestamp}. "
        f"Resume from: {session_log_name}. "
        f"Branch: {branch}. "
        f"Open items: {item_count}."
    )

    if open_items:
        items_preview = "; ".join(open_items[:5])
        if len(open_items) > 5:
            items_preview += f" ... (+{len(open_items) - 5} more)"
        resume_context += f" Items: {items_preview}"

    # The resume context printed to stdout is the sole product of this
    # hook; it is injected into the post-compaction session. No on-disk
    # artifact is written (ADR-082, issue #3217): the former
    # pre-compact-*.json checkpoint had no reader and was removed.
    print(f"## ⚠️ Pre-Compaction Checkpoint\n\n{resume_context}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
