#!/usr/bin/env python3
"""Gather Phase 0 evidence for a retrospective.

Collects the evidence sources this script currently supports: the recent
session log under ``.agents/sessions/`` and the ``git log`` over the
retrospective period. Each source degrades clearly: a missing or unreadable
source is marked absent in the returned ``Evidence`` rather than failing the
whole gather, per the SKILL.md Inputs contract ("When a source is unavailable,
degrade gracefully ... mark the missing sections, never substitute invented
data").

System of record: the session log is the SoR for what happened in a session;
git history is corroborating derived evidence (see
``.claude/rules/data-intensive-applications.md``). This module only reads; it
mutates no state.

Integration points: ``git`` is an external process. Every subprocess call sets
an explicit timeout and treats a non-zero exit or timeout as "source absent",
never as a crash (see ``.claude/rules/release-it.md``).

Exit codes (ADR-035):
  0: evidence gathered (some sources may be marked absent)
  2: usage or configuration error (bad project directory)
  3: unexpected external failure that prevented any gather
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Bound the git call so a wedged repo cannot hang the retrospective.
_GIT_TIMEOUT_SECONDS = 15
# Cap how many session-log work items we surface, matching the Stop hook.
_MAX_WORK_ITEMS = 25
# Cap commits pulled into the evidence to keep the artifact readable.
_DEFAULT_COMMIT_LIMIT = 50


@dataclass(frozen=True, slots=True)
class Evidence:
    """Phase 0 evidence bundle.

    Every source carries an explicit ``*_available`` flag so the artifact can
    mark missing sections instead of substituting invented data.

    Attributes:
        scope: The retrospective scope label.
        session_log_path: Path to the session log used, or empty when absent.
        session_log_available: Whether a session log was found and parsed.
        work_items: Work-item summaries from the session log.
        outcomes: Outcome summaries from the session log.
        git_available: Whether git history was readable.
        commits: One-line commit summaries over the period.
        notes: Human-readable notes about degraded sources.
    """

    scope: str
    session_log_path: str
    session_log_available: bool
    work_items: list[str]
    outcomes: list[str]
    git_available: bool
    commits: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SessionLogParseResult:
    """Parsed session-log fields plus an error when parsing failed."""

    work_items: list[str]
    outcomes: list[str]
    error: str | None = None

    def __iter__(self) -> Iterator[list[str]]:
        """Keep legacy tuple-unpacking callers source-compatible."""
        yield self.work_items
        yield self.outcomes


def _newest_session_log(candidates: list[Path]) -> Path:
    """Return the newest candidate by mtime, then name."""
    try:
        return max(candidates, key=lambda f: (f.stat().st_mtime, f.name))
    except OSError:
        return sorted(candidates, key=lambda p: p.name)[-1]


def find_recent_session_log(sessions_dir: Path, today: date | None = None) -> Path | None:
    """Return the current session log by date priority, or None when absent.

    Matches the Stop-hook lookup order: prefer today's logs, then yesterday's
    logs only when today has none, then fall back to the newest older log.
    """
    if not sessions_dir.is_dir():
        return None
    candidates = list(sessions_dir.glob("*-session-*.json"))
    if not candidates:
        return None
    today = today or datetime.now(tz=UTC).date()
    for target_day in (today, today - timedelta(days=1)):
        prefix = f"{target_day.isoformat()}-session-"
        dated = [path for path in candidates if path.name.startswith(prefix)]
        if dated:
            return _newest_session_log(dated)
    return _newest_session_log(candidates)


def _format_work_item(item: object) -> str:
    """Format a single work-log entry into one readable line.

    Supports the current ``{step, action, outcome}`` schema and the legacy
    ``{description}`` / ``{task}`` shapes, plus bare strings.
    """
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    if "action" in item:
        parts: list[str] = []
        if "step" in item:
            parts.append(f"Step {item['step']}:")
        parts.append(str(item["action"]))
        outcome = item.get("outcome")
        if outcome:
            parts.append(f"-> {outcome}")
        return " ".join(parts)
    for key in ("description", "task", "summary"):
        if key in item:
            return str(item[key])
    return json.dumps(item, sort_keys=True)


def _coerce_to_list(value: object) -> list[object]:
    """Normalize a work/outcomes field to a list across session schemas."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if not value:
            return []
        for key in ("tasks", "items", "log", "entries"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
        for inner in value.values():
            if isinstance(inner, list):
                return inner
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def parse_session_log(path: Path) -> SessionLogParseResult:
    """Read work items and outcomes from a session log.

    Returns formatted fields plus parse status. On parse or IO error, returns
    empty lists with an error so the caller can mark the source degraded
    without mislabeling it as an empty session.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return SessionLogParseResult([], [], f"{type(exc).__name__}: {exc}")
    if not isinstance(data, dict):
        return SessionLogParseResult([], [], "session log root is not an object")

    work_raw = data.get("workLog")
    if work_raw is None:
        work_raw = data.get("work", [])
    outcomes_raw = data.get("outcomes", [])

    work = [_format_work_item(i) for i in _coerce_to_list(work_raw)[:_MAX_WORK_ITEMS]]
    outcomes = [_format_work_item(o) for o in _coerce_to_list(outcomes_raw)[:_MAX_WORK_ITEMS]]
    return SessionLogParseResult(work, outcomes)


def gather_git_log(
    project_dir: Path,
    since: str | None,
    limit: int = _DEFAULT_COMMIT_LIMIT,
) -> tuple[bool, list[str]]:
    """Return git one-line commit summaries over the period.

    Returns ``(available, commits)``. ``available`` is False when git is not
    present, the directory is not a repo, or the call times out. The git call
    is bounded by an explicit timeout so a wedged repo cannot hang the gather.
    """
    cmd = ["git", "log", f"--max-count={limit}", "--pretty=format:%h %s"]
    if since:
        cmd.append(f"--since={since}")
    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, []
    if result.returncode != 0:
        return False, []
    commits = [line for line in result.stdout.splitlines() if line.strip()]
    return True, commits


def gather_evidence(
    project_dir: Path,
    scope: str,
    since: str | None = None,
) -> Evidence:
    """Gather all Phase 0 evidence, degrading gracefully on missing sources.

    Args:
        project_dir: Repository root containing ``.agents/`` and ``.git``.
        scope: The retrospective scope label.
        since: Optional ``git log --since`` value to bound the period.

    Returns:
        An :class:`Evidence` bundle with per-source availability flags.
    """
    notes: list[str] = []

    sessions_dir = project_dir / ".agents" / "sessions"
    session_log = find_recent_session_log(sessions_dir)
    if session_log is None:
        notes.append("No session log found under .agents/sessions/.")
        work_items: list[str] = []
        outcomes: list[str] = []
        session_log_available = False
        session_log_path = ""
    else:
        parsed_session = parse_session_log(session_log)
        work_items = parsed_session.work_items
        outcomes = parsed_session.outcomes
        session_log_path = str(session_log)
        if parsed_session.error is not None:
            session_log_available = False
            notes.append(
                f"Session log {session_log.name} could not be parsed: "
                f"{parsed_session.error}."
            )
        elif not work_items and not outcomes:
            session_log_available = False
            notes.append(f"Session log {session_log.name} had no work or outcomes.")
        else:
            session_log_available = True

    git_available, commits = gather_git_log(project_dir, since)
    if not git_available:
        notes.append("git history unavailable (not a repo, git missing, or timed out).")

    return Evidence(
        scope=scope,
        session_log_path=session_log_path,
        session_log_available=session_log_available,
        work_items=work_items,
        outcomes=outcomes,
        git_available=git_available,
        commits=commits,
        notes=notes,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Gather Phase 0 evidence for a retrospective.",
    )
    parser.add_argument(
        "--scope",
        default=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
        help="Retrospective scope label (default: today's date).",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="git log --since value bounding the period (e.g. '1 day ago').",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Emits the evidence bundle as JSON."""
    parser = build_parser()
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: project dir not found: {args.project_dir}", file=sys.stderr)
        return 2

    try:
        evidence = gather_evidence(project_dir, args.scope, args.since)
    except Exception as exc:  # noqa: BLE001 - boundary: report and exit cleanly
        print(f"ERROR: evidence gather failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
