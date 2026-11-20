#!/usr/bin/env python3
"""Remind the session about unfilled retrospective skeletons.

Claude Code SessionStart hook. When an unfilled retrospective skeleton dated
in the last ``PENDING_RETRO_MAX_AGE_DAYS`` days exists, it prints a short
reminder with the ``/retrospective fill <date>`` command. Otherwise it prints
nothing, so a session with no pending work pays no context cost. The Stop
hook that wrote skeletons was retired by #3349, so in this repository the
reminder fires only if someone adds a skeleton by hand.

Does NOT inject retrospective content. The latest-retrospective injection was
dropped; the ADR-008 amendment dated 2026-11-20 records the evidence.
Retrospectives stay reachable on demand through the ``retrospective`` skill
and ``.project-toolkit/retrospective/INDEX.md``.

Does NOT load .agents/HANDOFF.md either (Issue #5168; superseded by
per-issue handoffs and Serena memory per ADR-014).

Hook Type: SessionStart (non-blocking, fail-open)
Exit Codes:
    0 = Success (always, fail-open)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1672 (session-start gate)
    - Issue #2079 (pending-skeleton reminder)
    - Issue #5168 (removed the HANDOFF.md auto-load)
    - Issues #7471 and #7472 (influence telemetry and curation cadence)
    - ADR-008 (protocol automation via lifecycle hooks)
    - ADR-014 (distributed handoff architecture; supersedes HANDOFF.md)
"""

from __future__ import annotations

import io
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


# Characters read from the head of each candidate when searching for the
# skeleton marker. The marker sits near the top of a skeleton, so the full
# file is never read. Nothing read here is injected into session context.
SKELETON_MARKER_SCAN_CHARS = 4000

HOOK_NAME = "context-loader"

# Marker carried by unfilled skeletons (Issue #2079). Its writer, the Stop
# hook ``invoke_auto_retrospective.py``, was retired by #3349; the marker is
# documented in the retrospective skill's ``references/skeleton-fill.md``.
# A skeleton carries this exact string until a reviewer fills it and removes
# the marker; this hook counts the unfilled ones to remind the user.
RETRO_STATE_MARKER = "<!-- RETRO-STATE: skeleton-pending-fill -->"

# Skeletons older than this many days stop nagging (Issue #2079 acceptance:
# "Cap by date so stale skeletons do not nag forever").
PENDING_RETRO_MAX_AGE_DAYS = 7


def _has_symlink_component(root: Path, target: Path) -> bool:
    """Return whether any path component from ``root`` down to ``target`` is a symlink.

    If ``retro_dir`` itself (or an ancestor such as ``.project-toolkit``) is
    a symlink to an external directory, globbing it would scan that external
    directory and leak its Markdown filenames into SessionStart context.
    Walking each unresolved component between ``root`` (the project
    directory, trusted) and ``target`` (``retro_dir``) catches that
    redirection before anything is stat'd or globbed.
    """
    try:
        relative_parts = target.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _count_pending_skeletons(
    retro_dir: Path, root: Path, max_age_days: int = PENDING_RETRO_MAX_AGE_DAYS
) -> tuple[int, list[str]]:
    """Count unfilled retro skeletons within ``max_age_days`` (Issue #2079).

    A skeleton is "pending" when it still carries the RETRO_STATE_MARKER and
    its filename date is within the window. Filenames without a leading date
    fall back to mtime. Returns ``(count, sorted_filenames)``.

    ``root`` is the trusted project directory; every component from ``root``
    down to ``retro_dir`` is rejected if it is a symlink (see
    :func:`_has_symlink_component`) before ``retro_dir`` is globbed, so a
    symlinked ``.project-toolkit`` or ``retrospective`` ancestor cannot
    redirect the scan to an external directory and leak its filenames.

    Fail-open: a missing directory or a symlinked ancestor yields ``(0, [])``;
    a per-file stat or read error skips that file rather than aborting the
    scan.
    """
    if not retro_dir.is_dir():
        return 0, []

    if _has_symlink_component(root, retro_dir):
        return 0, []

    try:
        # Exclude the co-located INDEX.md: it lives alongside the retro files
        # but is a meta-index, not a retrospective.
        retro_paths = [p for p in retro_dir.glob("*.md") if p.name != "INDEX.md"]
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
                head = handle.read(SKELETON_MARKER_SCAN_CHARS)
        except OSError:
            continue
        if RETRO_STATE_MARKER in head:
            pending.append(path.name)

    pending.sort()
    return len(pending), pending


_RETRO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _is_pending_skeleton_recent(path: Path, cutoff_date: date, cutoff_mtime: float) -> bool:
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
    reminder needs the date argument for ``/retrospective fill <date>``. Filenames
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
        audit_dir = Path(project_dir) / ".project-toolkit" / ".hook-state"
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


def _emit_utf8(text: str) -> None:
    """Prefer UTF-8 protocol output, with an ambient-encoding text fallback."""
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")
        except (
            AttributeError,
            TypeError,
            ValueError,
            io.UnsupportedOperation,
            OSError,
        ):
            pass
        else:
            stream.write(text + "\n")
            stream.flush()
            return

    payload = bytes(f"{text}\n", encoding="utf-8")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(payload)
        buffer.flush()
        return

    stream.write(text + "\n")
    stream.flush()


def _pending_reminder(pending_count: int, pending_names: list[str]) -> str:
    """Render the unfilled-skeleton reminder with one fill command (Issue #2079)."""
    listed = _pending_skeleton_summary(pending_names)
    dates = _skeleton_dates(pending_names)
    fill_hint = dates[0] if dates else "<date>"
    other_dates = f"\n\nOther available dates: {', '.join(dates[1:])}." if len(dates) > 1 else ""
    return (
        f"## ⏳ {pending_count} retro(s) need completion\n\n"
        f"Unfilled skeletons (last {PENDING_RETRO_MAX_AGE_DAYS} days): {listed}\n\n"
        f"Run `/retrospective fill {fill_hint}` to populate one skeleton and clear it."
        f"{other_dates}"
    )


def main() -> None:
    """Remind about unfilled retrospective skeletons; inject nothing otherwise."""
    _drain_stdin()

    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    project_dir = get_project_directory()
    project_path = Path(project_dir)
    retro_dir = project_path / ".project-toolkit" / "retrospective"

    pending_count, pending_names = _count_pending_skeletons(retro_dir, project_path)
    if pending_count:
        _emit_utf8(_pending_reminder(pending_count, pending_names))
        _write_audit_log(project_dir, [f"pending-retros:{pending_count}"])
    else:
        _write_audit_log(project_dir, ["(none)"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open: never block session start
        print(f"[WARNING] context-loader error: {exc}", file=sys.stderr)
        sys.exit(0)
