#!/usr/bin/env python3
"""Canonical emitter for REQ-008-09 kill-criteria (K1-K4) telemetry.

This is the one place that knows the on-disk shape of a kill-criteria
event. Every K1-K4 emission point (the drift-guard hook, the drift-check
CI job, the vendored-install check, the local-vs-CI verdict comparison)
calls :func:`emit_event` or the CLI here so the JSONL schema lives in a
single module. Duplicating the json-append logic at each site would let
the four writers drift apart (one of the exact failure modes REQ-008
tracks).

Kill criteria (see
``.agents/specs/requirements/REQ-008-review-axes-convergence.md`` Kill
Criteria section, REQ-008-09):

    K1: drift hook false positive (axis edit the maintainer intended that
        the hook blocked). 3+ in 30 days rolls back the convergence design.
    K2: generator-induced regression in CI prompts. 3+ instances.
    K3: vendored install breakage. 1+ downstream installer reports /review
        fails after a project-toolkit plugin update. Hard fail.
    K4: drift between local /review verdict and CI verdict on the same
        commit. 3+ in 30 days.

Event shape (one JSON object per line, append-only)::

    {"schemaVersion": 1, "ts": "<ISO-8601 UTC>", "kind": "K1",
     "detail": "<free text the emission point controls>"}

``schemaVersion`` is included so a future shape change is diagnosable
(see ``.claude/rules/data-intensive-applications.md`` schema evolution).
``ts`` is wall-clock UTC, used only for the 30-day rollover window, not
for causal ordering.

System of record: ``.agents/metrics/drift-events.jsonl`` is the SoR for
kill-criteria counts. The file is append-only; readers tally by ``kind``
within the trailing 30 days. Real telemetry is git-ignored; only an empty
seed (``.gitkeep``) is tracked so the directory exists on a fresh clone.

Detail field: callers pass structured, self-generated strings (drift
paths, counts, commit SHAs), never untrusted external pastes, so the
secret-redaction backstop (``.claude/rules/secret-redaction.md``) does not
run on this hot path. Do not feed user-pasted text into ``detail``.

Idempotency: each call appends exactly one line. The append is guarded by
``hook_utilities.lock_file`` when that lib is importable (the hook
context), and falls back to a plain append otherwise. A single retried
caller will append twice by design; dedupe, if needed, happens at read
time on ``(ts, kind, detail)``.

Weekly rollup: the ``report`` subcommand reads the same SoR file and tallies
events per kind within the trailing ``WINDOW_DAYS`` window, then prints a
markdown table with each criterion's count, its REQ-008-09 threshold, and a
status (ok / approaching / fired). A scheduled workflow runs the report so a
maintainer sees when a kill criterion nears its rollback limit before it fires.
The report is read-only; it never appends to the metrics file.

Exit Codes (ADR-035), CLI only:
    0 = event written, or report produced with no criterion fired
    1 = report produced and at least one kill criterion has fired (logic /
        threshold breach; the caller surfaces it)
    2 = usage / configuration error (bad arguments, unknown kind, unsafe path)
    3 = external failure (could not write or read the metrics file)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal, TextIO

KillCriterion = Literal["K1", "K2", "K3", "K4"]

VALID_KINDS: Final[frozenset[str]] = frozenset({"K1", "K2", "K3", "K4"})

# Order kinds present in the rollup so the report is stable across runs.
ORDERED_KINDS: Final[tuple[KillCriterion, ...]] = ("K1", "K2", "K3", "K4")

SCHEMA_VERSION: Final[int] = 1

# Path of the events file relative to the repository root.
EVENTS_RELPATH: Final[str] = ".agents/metrics/drift-events.jsonl"

# Rollover window for the kill-criteria counts, in days. REQ-008-09 phrases
# every limit as "within 30 days post-merge"; events older than this fall out
# of the tally.
WINDOW_DAYS: Final[int] = 30

# Per-criterion rollback thresholds, copied verbatim from REQ-008-09 in
# .agents/specs/requirements/REQ-008-review-axes-convergence.md (Kill Criteria):
#   K1: drift hook 3+ false positives in 30 days.
#   K2: generator-induced CI regressions, 3+ instances.
#   K3: vendored install breakage, 1+ report (hard fail).
#   K4: local-vs-CI verdict drift, 3+ times in 30 days.
# A criterion fires when its trailing-window count reaches the threshold.
KILL_THRESHOLDS: Final[dict[KillCriterion, int]] = {
    "K1": 3,
    "K2": 3,
    "K3": 1,
    "K4": 3,
}


def _try_lock_helpers() -> tuple[
    Callable[[TextIO], None] | None,
    Callable[[TextIO], None] | None,
]:
    """Return (lock_file, unlock_file) from hook_utilities, or (None, None).

    The drift-guard hook runs with ``hook_utilities`` already on
    ``sys.path`` (the plugin bootstrap put it there). Standalone CLI and
    script callers usually do not. When the helpers are unavailable, the
    caller falls back to a plain append; a missing advisory lock only
    matters when two writers race, which is rare for these low-frequency
    events.
    """
    try:
        from hook_utilities import lock_file, unlock_file  # noqa: PLC0415
    except ImportError:
        return None, None
    return lock_file, unlock_file


def _repo_root() -> Path:
    """Resolve the repository root anchored to this module's location."""
    return Path(__file__).resolve().parents[2]


def build_event(kind: KillCriterion, detail: str) -> dict[str, object]:
    """Build a kill-criteria event dict.

    Args:
        kind: One of ``K1``-``K4``.
        detail: Free-text describing the trigger. Caller-controlled,
            not untrusted input.

    Returns:
        The event as a plain dict, ready to serialize.

    Raises:
        ValueError: ``kind`` is not a recognized kill criterion.
    """
    if kind not in VALID_KINDS:
        msg = f"unknown kill criterion {kind!r}; expected one of {sorted(VALID_KINDS)}"
        raise ValueError(msg)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ts": datetime.now(tz=UTC).isoformat(),
        "kind": kind,
        "detail": detail,
    }


def _append_line(path: Path, line: str) -> None:
    """Append a single line to ``path``, creating parents as needed.

    Uses the ``hook_utilities`` advisory lock when available so two
    concurrent writers do not interleave. The lock is best-effort; the
    write proceeds without it when the helpers are absent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file, unlock_file = _try_lock_helpers()
    with path.open("a", encoding="utf-8") as handle:
        if lock_file is not None and unlock_file is not None:
            lock_file(handle)
            try:
                handle.write(line)
                handle.flush()
            finally:
                unlock_file(handle)
        else:
            handle.write(line)


def emit_event(
    kind: KillCriterion,
    detail: str,
    events_path: Path | None = None,
) -> dict[str, object]:
    """Append one kill-criteria event to the metrics file.

    Args:
        kind: One of ``K1``-``K4``.
        detail: Free-text describing the trigger (caller-controlled).
        events_path: Override for the events file. Defaults to
            ``<repo-root>/.agents/metrics/drift-events.jsonl``. Tests
            pass a temp path here to mock the write boundary.

    Returns:
        The event dict that was written.

    Raises:
        ValueError: ``kind`` is invalid.
        OSError: The metrics file could not be written.
    """
    event = build_event(kind, detail)
    target = events_path if events_path is not None else _repo_root() / EVENTS_RELPATH
    line = json.dumps(event, separators=(",", ":")) + "\n"
    _append_line(target, line)
    return event


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser with an emit (default) and a report subcommand.

    The emit form keeps its flat flags (``--kind``/``--detail``) so existing
    callers, including the drift-detection workflow step, do not change. The
    report subcommand is opt-in via the ``report`` keyword.
    """
    parser = argparse.ArgumentParser(
        prog="kill_criteria",
        description=(
            "Emit or summarize REQ-008-09 kill-criteria (K1-K4) telemetry. "
            "With no subcommand, emit one event from --kind/--detail. "
            "Use 'report' for the weekly rollup."
        ),
    )
    parser.add_argument(
        "--kind",
        choices=sorted(VALID_KINDS),
        help="Kill criterion to record (K1, K2, K3, or K4).",
    )
    parser.add_argument(
        "--detail",
        help="Free-text description of the trigger (caller-controlled).",
    )
    parser.add_argument(
        "--events-path",
        default=None,
        help="Override for the events JSONL file (default: repo metrics file).",
    )

    subparsers = parser.add_subparsers(dest="command")
    report = subparsers.add_parser(
        "report",
        help="Print a weekly markdown rollup of trailing-window kill-criteria counts.",
    )
    report.add_argument(
        "--events-path",
        default=None,
        help="Override for the events JSONL file (default: repo metrics file).",
    )
    return parser


def _parse_args(argv: list[str]) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def _safe_events_path(raw: str) -> Path:
    """Return a repo-confined metrics path from a CLI string."""
    if not raw or not raw.strip():
        msg = "events path must not be empty"
        raise ValueError(msg)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        msg = "events path contains control characters"
        raise ValueError(msg)

    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("~"):
        msg = "events path must be relative to the repository root"
        raise ValueError(msg)
    if len(normalized) >= 2 and normalized[1] == ":":
        msg = "events path must not use a drive-qualified path"
        raise ValueError(msg)
    if normalized.endswith("/") or "//" in normalized:
        msg = "events path must name a JSONL file without empty path parts"
        raise ValueError(msg)

    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts:
        msg = "events path must name a JSONL file"
        raise ValueError(msg)
    if any(part == ".." for part in parts):
        msg = "events path traversal is not allowed"
        raise ValueError(msg)
    if parts[-1] == ".." or not parts[-1].endswith(".jsonl"):
        msg = "events path must end in .jsonl"
        raise ValueError(msg)

    repo_root = _repo_root()
    candidate = (repo_root / Path(*parts)).resolve(strict=False)
    if not candidate.is_relative_to(repo_root):
        msg = "events path must stay within the repository root"
        raise ValueError(msg)
    return candidate


# --- report (read side) --------------------------------------------------

CriterionStatus = Literal["ok", "approaching", "fired"]


@dataclass(frozen=True, slots=True)
class CriterionRollup:
    """Trailing-window tally for one kill criterion.

    Args:
        kind: The kill criterion (``K1``-``K4``).
        count: Events observed for this kind inside the window.
        threshold: The REQ-008-09 limit at which the criterion fires.
        status: ``fired`` when ``count >= threshold``, ``approaching`` when
            one short of the threshold, ``ok`` otherwise.
    """

    kind: KillCriterion
    count: int
    threshold: int
    status: CriterionStatus


def _classify(count: int, threshold: int) -> CriterionStatus:
    """Map a count against its threshold to a status label.

    A criterion fires when ``count >= threshold``. It is ``approaching`` only
    when at least one event is recorded and the count is exactly one short of
    the threshold. A hard-fail criterion (threshold 1, such as K3) has no
    approaching band: zero events is ``ok`` and the first event is ``fired``.
    """
    if count >= threshold:
        return "fired"
    if count > 0 and count == threshold - 1:
        return "approaching"
    return "ok"


def _parse_event_line(line: str) -> dict[str, object] | None:
    """Parse one JSONL line into an event dict, or None when unusable.

    A blank line yields None. A line that is not a JSON object, or whose
    ``kind`` is not a recognized criterion, is skipped so one malformed
    append cannot poison the whole rollup (the file is append-only and may
    accrete partial writes on a crashed runner).
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("kind") not in VALID_KINDS:
        return None
    return parsed


def _event_in_window(event: Mapping[str, object], cutoff: datetime) -> bool:
    """Return True when the event timestamp is at or after the cutoff.

    An event with a missing or unparseable ``ts`` is treated as out of
    window: the report counts only events it can place in time, and an
    undated event cannot be attributed to the trailing 30 days.
    """
    raw_ts = event.get("ts")
    if not isinstance(raw_ts, str):
        return False
    try:
        parsed = datetime.fromisoformat(raw_ts)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed >= cutoff


def count_events_in_window(
    lines: Iterable[str],
    now: datetime,
    window_days: int = WINDOW_DAYS,
) -> dict[KillCriterion, int]:
    """Tally events per kind within the trailing window.

    Args:
        lines: Raw JSONL lines from the events file.
        now: The reference instant the window ends at (UTC).
        window_days: Width of the trailing window in days.

    Returns:
        A count per criterion. Every kind in ``ORDERED_KINDS`` is present,
        defaulting to zero, so the rollup never hides a quiet criterion.
    """
    cutoff = now - timedelta(days=window_days)
    counts: dict[KillCriterion, int] = dict.fromkeys(ORDERED_KINDS, 0)
    for line in lines:
        event = _parse_event_line(line)
        if event is None or not _event_in_window(event, cutoff):
            continue
        kind = event["kind"]
        counts[kind] += 1  # type: ignore[index]  # kind validated in _parse_event_line
    return counts


def build_rollups(counts: dict[KillCriterion, int]) -> list[CriterionRollup]:
    """Turn per-kind counts into ordered rollups with status."""
    return [
        CriterionRollup(
            kind=kind,
            count=counts.get(kind, 0),
            threshold=KILL_THRESHOLDS[kind],
            status=_classify(counts.get(kind, 0), KILL_THRESHOLDS[kind]),
        )
        for kind in ORDERED_KINDS
    ]


_STATUS_LABEL: Final[dict[CriterionStatus, str]] = {
    "ok": "ok",
    "approaching": "approaching",
    "fired": "FIRED",
}

_CRITERION_DESCRIPTION: Final[dict[KillCriterion, str]] = {
    "K1": "drift hook false positives",
    "K2": "generator-induced CI regressions",
    "K3": "vendored install breakage",
    "K4": "local-vs-CI verdict drift",
}


def render_report(
    rollups: Sequence[CriterionRollup],
    now: datetime,
    window_days: int = WINDOW_DAYS,
) -> str:
    """Render the weekly rollup as a markdown summary.

    The summary leads with the window and a headline (all clear, an
    approaching warning, or a fired alert), then a table of every criterion.
    """
    fired = [r for r in rollups if r.status == "fired"]
    approaching = [r for r in rollups if r.status == "approaching"]
    window_end = now.date().isoformat()

    lines = [
        "## Kill-Criteria Drift Telemetry (REQ-008-09)",
        "",
        f"Trailing {window_days}-day window ending {window_end} (UTC).",
        "",
    ]
    if fired:
        names = ", ".join(r.kind for r in fired)
        lines.append(f"ALERT: kill criteria fired: {names}. Roll back per REQ-008-09.")
    elif approaching:
        names = ", ".join(r.kind for r in approaching)
        lines.append(f"WARNING: kill criteria approaching the limit: {names}.")
    else:
        lines.append("All clear: no kill criterion is within one event of its limit.")
    lines.extend(
        [
            "",
            "| Kind | Criterion | Count | Threshold | Status |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for rollup in rollups:
        description = _CRITERION_DESCRIPTION[rollup.kind]
        status = _STATUS_LABEL[rollup.status]
        lines.append(
            f"| {rollup.kind} | {description} | {rollup.count} | {rollup.threshold} | {status} |"
        )
    lines.append("")
    return "\n".join(lines)


def report_events(
    events_path: Path | None = None,
    now: datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> tuple[str, bool]:
    """Produce the weekly rollup from the events file.

    Args:
        events_path: Override for the events file. Defaults to the repo
            metrics file. Tests pass a temp path here to mock the read
            boundary.
        now: Reference instant the window ends at. Defaults to current UTC.
        window_days: Width of the trailing window in days.

    Returns:
        ``(markdown, any_fired)``. ``any_fired`` is True when at least one
        criterion has reached its threshold, so the caller can set a
        non-zero exit code.

    Raises:
        OSError: The metrics file exists but could not be read.
    """
    target = events_path if events_path is not None else _repo_root() / EVENTS_RELPATH
    reference = now if now is not None else datetime.now(tz=UTC)
    lines = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    counts = count_events_in_window(lines, reference, window_days)
    rollups = build_rollups(counts)
    markdown = render_report(rollups, reference, window_days)
    any_fired = any(r.status == "fired" for r in rollups)
    return markdown, any_fired


def _run_report(events_path: Path | None) -> int:
    """CLI handler for the ``report`` subcommand. See module exit codes."""
    try:
        markdown, any_fired = report_events(events_path=events_path)
    except OSError as exc:
        print(f"error: could not read metrics file: {exc}", file=sys.stderr)
        return 3
    print(markdown)
    return 1 if any_fired else 0


def _resolve_events_path(raw: str | None) -> Path | None:
    """Validate the CLI events-path override, or None for the default."""
    return _safe_events_path(raw) if raw else None


def _run_emit(args: argparse.Namespace, events_path: Path | None) -> int:
    """CLI handler for the default emit form. See module exit codes."""
    if not args.kind or not args.detail:
        print("error: emit requires --kind and --detail", file=sys.stderr)
        return 2
    try:
        event = emit_event(args.kind, args.detail, events_path=events_path)
    except OSError as exc:
        print(f"error: could not write metrics file: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(event, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for exit codes."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        events_path = _resolve_events_path(args.events_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "report":
        return _run_report(events_path)
    return _run_emit(args, events_path)


if __name__ == "__main__":
    sys.exit(main())
