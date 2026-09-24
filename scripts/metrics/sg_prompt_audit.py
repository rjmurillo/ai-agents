"""Audit security-guidance child-review transcripts for repeated diff content.

REQ-3 of ``.project-toolkit/specs/SPEC-5856-security-guidance-diff-prompt-dedup.md``:
walk a Claude Code ``projects/`` directory, parse every child-review transcript
(``scripts/metrics/sg_prompt_audit_parse.py``), and report how much of the
inlined-diff prompt content is exact-duplicate across sessions. The report
is content-free: hashes, byte counts, paths, timestamps, and counters only,
never the diff or prompt text itself (see ``AuditReport`` in
``sg_prompt_audit_models.py``, and the no-leak test in
``tests/metrics/test_sg_prompt_audit.py``).

Usage::

    python -m scripts.metrics.sg_prompt_audit [--projects-dir DIR] \\
        [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--top N] [--output PATH]

Exit codes: ``0`` on success, ``2`` for a configuration error (a
``--projects-dir`` that is not a directory, or a malformed ``--since``/
``--until`` date). This mirrors the ``AGENTS.md`` exit-code contract
(``0``=ok, ``2``=config), which is the only pair this read-only auditor can
reach; it has no logic (``1``), external (``3``), or auth (``4``) failure
mode to report.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from scripts.metrics.sg_prompt_audit_models import (
    AuditReport,
    FailureEntry,
    Iter2CacheEntry,
    Locator,
    RepeatedBlockGroup,
    RepeatedDiffGroup,
    SessionRecord,
    Window,
)
from scripts.metrics.sg_prompt_audit_parse import parse_timestamp, process_transcript_file

_TOKEN_ESTIMATE_METHOD = "bytes_div_4"


def _in_window(started_at: str, since: date | None, until: date | None) -> bool:
    if since is None and until is None:
        return True
    if not started_at:
        return False
    day = parse_timestamp(started_at).date()
    if since is not None and day < since:
        return False
    if until is not None and day > until:
        return False
    return True


def build_report(
    projects_dir: Path, since: date | None, until: date | None, top: int
) -> AuditReport:
    """Walk ``projects_dir`` and summarize every in-window review session found."""
    records: list[SessionRecord] = []
    skipped_lines = 0
    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        for jsonl_path in sorted(project_dir.glob("*.jsonl")):
            record, skipped = process_transcript_file(jsonl_path, project_dir.name)
            skipped_lines += skipped
            if record is not None and _in_window(record.started_at, since, until):
                records.append(record)
    return summarize(str(projects_dir), records, since, until, top, skipped_lines)


def _diff_group_entry(diff_sha256: str, members: list[SessionRecord]) -> RepeatedDiffGroup:
    total_bytes = members[0].diff_bytes
    started = [m.started_at for m in members if m.started_at]
    span = 0.0
    if len(started) >= 2:
        span = (parse_timestamp(max(started)) - parse_timestamp(min(started))).total_seconds()
    return RepeatedDiffGroup(
        diff_sha256=diff_sha256,
        count=len(members),
        bytes=total_bytes,
        redundant_bytes=total_bytes * (len(members) - 1),
        kinds=sorted({m.kind for m in members}),
        locators=[m.locator for m in members],
        distinct_cwds=len({m.cwd for m in members}),
        time_span_seconds=span,
    )


def _repeated_diffs(records: Sequence[SessionRecord]) -> list[RepeatedDiffGroup]:
    groups: dict[str, list[SessionRecord]] = {}
    for record in records:
        groups.setdefault(record.diff_sha256, []).append(record)
    return [
        _diff_group_entry(sha256, members) for sha256, members in groups.items() if len(members) > 1
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class _BlockOccurrence:
    session_locator: Locator
    project: str
    bytes: int
    path: str


def _block_occurrences(records: Sequence[SessionRecord]) -> dict[str, list[_BlockOccurrence]]:
    occurrences: dict[str, list[_BlockOccurrence]] = {}
    for record in records:
        for block in record.blocks:
            occurrences.setdefault(block.sha256, []).append(
                _BlockOccurrence(
                    session_locator=record.locator,
                    project=record.locator.project,
                    bytes=block.bytes,
                    path=block.path,
                )
            )
    return occurrences


def _block_group_entry(sha256: str, occurrences: list[_BlockOccurrence]) -> RepeatedBlockGroup:
    sessions = {occ.session_locator for occ in occurrences}
    projects = {occ.project for occ in occurrences}
    block_bytes = occurrences[0].bytes
    return RepeatedBlockGroup(
        block_sha256=sha256,
        path=occurrences[0].path,
        bytes=block_bytes,
        sessions=len(sessions),
        distinct_projects=len(projects),
        redundant_bytes=block_bytes * (len(sessions) - 1),
    )


def _repeated_blocks(records: Sequence[SessionRecord]) -> list[RepeatedBlockGroup]:
    occurrences = _block_occurrences(records)
    groups = []
    for sha256, occs in occurrences.items():
        if len({occ.session_locator for occ in occs}) > 1:
            groups.append(_block_group_entry(sha256, occs))
    return groups


def _failures(records: Sequence[SessionRecord]) -> list[FailureEntry]:
    return [
        FailureEntry(locator=r.locator, reason=r.failure) for r in records if r.failure is not None
    ]


def _iter2_cache(records: Sequence[SessionRecord]) -> list[Iter2CacheEntry]:
    entries = []
    for r in records:
        if r.kind != "iter2" or r.first_turn_usage is None:
            continue
        entries.append(
            Iter2CacheEntry(
                locator=r.locator,
                cache_read_input_tokens=r.first_turn_usage.cache_read_input_tokens,
                cache_creation_input_tokens=r.first_turn_usage.cache_creation_input_tokens,
            )
        )
    return entries


def summarize(
    projects_dir: str,
    records: Sequence[SessionRecord],
    since: date | None,
    until: date | None,
    top: int,
    skipped_lines: int,
) -> AuditReport:
    """Aggregate parsed sessions into the content-free ``AuditReport``."""
    counts_by_kind: dict[str, int] = {}
    total_prompt_bytes = 0
    for record in records:
        counts_by_kind[record.kind] = counts_by_kind.get(record.kind, 0) + 1
        total_prompt_bytes += record.prompt_bytes
    diff_groups = _repeated_diffs(records)
    block_groups = _repeated_blocks(records)
    grand_diffs_bytes = sum(g.redundant_bytes for g in diff_groups)
    grand_blocks_bytes = sum(g.redundant_bytes for g in block_groups)
    window = Window(
        since=since.isoformat() if since else None,
        until=until.isoformat() if until else None,
    )
    return AuditReport(
        projects_dir=projects_dir,
        window=window,
        sessions_examined=len(records),
        skipped_lines=skipped_lines,
        counts_by_kind=counts_by_kind,
        total_prompt_bytes=total_prompt_bytes,
        estimated_tokens=total_prompt_bytes // 4,
        token_estimate_method=_TOKEN_ESTIMATE_METHOD,
        repeated_diffs=sorted(diff_groups, key=lambda g: g.redundant_bytes, reverse=True)[:top],
        repeated_blocks=sorted(block_groups, key=lambda g: g.redundant_bytes, reverse=True)[:top],
        grand_redundant_bytes_diffs=grand_diffs_bytes,
        grand_redundant_tokens_diffs=grand_diffs_bytes // 4,
        grand_redundant_bytes_blocks=grand_blocks_bytes,
        grand_redundant_tokens_blocks=grand_blocks_bytes // 4,
        iter2_cache=_iter2_cache(records),
        failures=_failures(records),
    )


def _parse_date_bound(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit security-guidance child-review transcripts for repeated diff "
            "and block content."
        )
    )
    parser.add_argument(
        "--projects-dir",
        default=str(Path.home() / ".claude" / "projects"),
        help=(
            "Directory holding per-project transcript subdirectories "
            "(default: ~/.claude/projects)."
        ),
    )
    parser.add_argument("--since", help="YYYY-MM-DD inclusive lower bound on session start.")
    parser.add_argument("--until", help="YYYY-MM-DD inclusive upper bound on session start.")
    parser.add_argument(
        "--top", type=int, default=20, help="Top-N groups by redundant bytes (default: 20)."
    )
    parser.add_argument("--output", help="Write the JSON report to this path; default is stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(args_list)
    projects_dir = Path(args.projects_dir)
    if not projects_dir.is_dir():
        print(f"error: not a directory: {projects_dir}", file=sys.stderr)
        return 2
    try:
        since = _parse_date_bound(args.since)
        until = _parse_date_bound(args.until)
    except ValueError as exc:
        print(f"error: invalid date: {exc}", file=sys.stderr)
        return 2
    report = build_report(projects_dir, since, until, args.top)
    text = json.dumps(dataclasses.asdict(report), indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover -- process entry point, not unit-testable
    sys.exit(main())
