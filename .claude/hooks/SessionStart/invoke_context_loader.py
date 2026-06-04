#!/usr/bin/env python3
"""Auto-load HANDOFF.md and latest retrospective at session start.

Claude Code SessionStart hook that injects critical context files into
the session to eliminate the 95.8% context reading failure rate documented
in retrospective analysis.

Loads:
1. .agents/HANDOFF.md (read-only dashboard of project state)
2. Latest retrospective from .agents/retrospective/ (learnings from prior sessions)

Both are truncated to prevent context bloat. Output is printed to stdout
so Claude Code injects it into the session context.

Hook Type: SessionStart (non-blocking, fail-open)
Exit Codes:
    0 = Success (always, fail-open)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1672 (session-start gate)
    - ADR-008 (protocol automation via lifecycle hooks)
"""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# --- Standard hook boilerplate: resolve lib directory ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


# Maximum characters to inject per file to prevent context bloat
MAX_HANDOFF_CHARS = 4000
MAX_RETRO_CHARS = 4000

HOOK_NAME = "context-loader"

# Mirror of the marker stamped into unfilled skeletons by the Stop hook
# (Issue #2079). Canonical source:
# .claude/hooks/Stop/invoke_auto_retrospective.py, constant
# ``RETRO_STATE_MARKER``. Quoted verbatim per the canonical-source-mirror
# rule. A skeleton carries this exact string until a reviewer fills it and
# removes the marker; this hook counts the unfilled ones to remind the user.
RETRO_STATE_MARKER = "<!-- RETRO-STATE: skeleton-pending-fill -->"

# Skeletons older than this many days stop nagging (Issue #2079 acceptance:
# "Cap by date so stale skeletons do not nag forever").
PENDING_RETRO_MAX_AGE_DAYS = 7


def _read_file_truncated(path: Path, max_chars: int) -> str | None:
    """Read a file, truncating to max_chars if necessary.

    Streams only the bytes needed instead of loading the whole file, so
    large files do not balloon hook memory.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            content = handle.read(max_chars + 1)
    except OSError:
        return None

    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n[... truncated at {max_chars} chars ...]"
    return content


def _find_latest_retrospective(retro_dir: Path) -> Path | None:
    """Find the most recent retrospective file by modification time.

    Per-file stat failures (race with deletion, permission issue) skip that
    file rather than aborting the whole scan, so a single unreadable retro
    does not hide every other retro from the SessionStart hook.
    """
    if not retro_dir.is_dir():
        return None

    candidates: list[tuple[float, Path]] = []
    try:
        retro_paths = list(retro_dir.glob("*.md"))
    except OSError:
        return None

    for path in retro_paths:
        try:
            candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda entry: entry[0], reverse=True)
    return candidates[0][1]


def _count_pending_skeletons(
    retro_dir: Path, max_age_days: int = PENDING_RETRO_MAX_AGE_DAYS
) -> tuple[int, list[str]]:
    """Count unfilled retro skeletons within ``max_age_days`` (Issue #2079).

    A skeleton is "pending" when it still carries the RETRO_STATE_MARKER and
    its filename date is within the window. Filenames without a leading date
    fall back to mtime. Returns ``(count, sorted_filenames)``.

    Fail-open: a missing directory yields ``(0, [])``; a per-file stat or read
    error skips that file rather than aborting the scan, mirroring
    :func:`_find_latest_retrospective`.
    """
    if not retro_dir.is_dir():
        return 0, []

    try:
        retro_paths = list(retro_dir.glob("*.md"))
    except OSError:
        return 0, []

    cutoff_date = datetime.now(tz=UTC).date() - timedelta(days=max_age_days)
    cutoff_mtime = datetime.now(tz=UTC).timestamp() - max_age_days * 86400
    pending: list[str] = []
    for path in retro_paths:
        try:
            if not _is_pending_skeleton_recent(path, cutoff_date, cutoff_mtime):
                continue
            with path.open(encoding="utf-8", errors="replace") as handle:
                head = handle.read(MAX_RETRO_CHARS)
        except OSError:
            continue
        if RETRO_STATE_MARKER in head:
            pending.append(path.name)

    pending.sort()
    return len(pending), pending


_RETRO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _is_pending_skeleton_recent(
    path: Path, cutoff_date: date, cutoff_mtime: float
) -> bool:
    filename_date = _filename_date(path.name)
    if filename_date is not None:
        return filename_date >= cutoff_date
    return path.stat().st_mtime >= cutoff_mtime


def _filename_date(filename: str) -> date | None:
    match = _RETRO_DATE_RE.match(filename)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _skeleton_dates(filenames: list[str]) -> list[str]:
    """Extract leading ``YYYY-MM-DD`` dates from skeleton filenames (Issue #2079).

    Auto-retro skeletons are named ``YYYY-MM-DD-auto-retro.md``. The fill
    reminder needs the date argument for ``/retro fill <date>``. Filenames
    without a leading date are skipped. Order is preserved; duplicates removed.
    """
    seen: set[str] = set()
    dates: list[str] = []
    for name in filenames:
        filename_date = _filename_date(name)
        if filename_date is None:
            continue
        date_text = filename_date.isoformat()
        if date_text not in seen:
            seen.add(date_text)
            dates.append(date_text)
    return dates


def _pending_skeleton_summary(filenames: list[str]) -> str:
    dates = _skeleton_dates(filenames)
    undated_count = sum(1 for name in filenames if _filename_date(name) is None)
    parts = [f"{date_text}-auto-retro.md" for date_text in dates]
    if undated_count:
        parts.append(f"{undated_count} undated skeleton file(s)")
    return ", ".join(parts) if parts else f"{len(filenames)} skeleton file(s)"


def _write_audit_log(project_dir: str, loaded_files: list[str]) -> None:
    """Write a brief audit entry for session start context loading."""
    try:
        audit_dir = Path(project_dir) / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        timestamp = datetime.now(tz=UTC).isoformat()
        audit_file = audit_dir / f"context-loader-{today}.log"

        with audit_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Loaded: {', '.join(loaded_files)}\n")
    except OSError:
        pass  # Fail-open: audit is best-effort


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
    """Load HANDOFF.md and latest retrospective into session context."""
    _drain_stdin()

    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    project_dir = get_project_directory()
    project_path = Path(project_dir)
    loaded_files: list[str] = []
    output_parts: list[str] = []

    # 1. Load HANDOFF.md
    handoff_path = project_path / ".agents" / "HANDOFF.md"
    handoff_content = _read_file_truncated(handoff_path, MAX_HANDOFF_CHARS)
    if handoff_content:
        output_parts.append(
            "## 📋 Auto-loaded: HANDOFF.md (read-only dashboard)\n\n"
            f"{handoff_content}"
        )
        loaded_files.append("HANDOFF.md")

    # 2. Load latest retrospective
    retro_dir = project_path / ".agents" / "retrospective"
    latest_retro = _find_latest_retrospective(retro_dir)
    if latest_retro:
        retro_content = _read_file_truncated(latest_retro, MAX_RETRO_CHARS)
        if retro_content:
            output_parts.append(
                f"## 📝 Auto-loaded: Latest Retrospective ({latest_retro.name})\n\n"
                f"{retro_content}"
            )
            loaded_files.append(f"retrospective/{latest_retro.name}")

    # 3. Remind about unfilled retro skeletons (Issue #2079). Surface a count
    # and the fill command so the next interactive session can complete them.
    pending_count, pending_names = _count_pending_skeletons(retro_dir)
    if pending_count:
        listed = _pending_skeleton_summary(pending_names)
        dates = _skeleton_dates(pending_names)
        fill_hint = dates[0] if dates else "<date>"
        other_dates = (
            f"\n\nOther available dates: {', '.join(dates[1:])}."
            if len(dates) > 1
            else ""
        )
        output_parts.append(
            f"## ⏳ {pending_count} retro(s) need completion\n\n"
            f"Unfilled skeletons (last {PENDING_RETRO_MAX_AGE_DAYS} days): {listed}\n\n"
            f"Run `/retro fill {fill_hint}` to populate one skeleton and clear it."
            f"{other_dates}"
        )
        loaded_files.append(f"pending-retros:{pending_count}")

    # Output to stdout (injected into Claude's context)
    if output_parts:
        header = "## 🔄 Context Loader: Session Start Auto-Injection\n\n"
        summary = f"**Loaded {len(loaded_files)} file(s)**: {', '.join(loaded_files)}\n\n---\n\n"
        print(header + summary + "\n\n---\n\n".join(output_parts))
    else:
        print("## 🔄 Context Loader: No context files found to auto-load")

    # Audit trail (best-effort)
    _write_audit_log(project_dir, loaded_files if loaded_files else ["(none)"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open: never block session start
        print(f"[WARNING] context-loader error: {exc}", file=sys.stderr)
        sys.exit(0)
