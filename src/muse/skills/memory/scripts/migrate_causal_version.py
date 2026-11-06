#!/usr/bin/env python3
"""Stamp causal_order_version=2 on legacy episode files.

Issue #3598: existing episodes pre-date #3464, which introduced
causal_order_version=2 on newly written episodes. An absent marker means the
edges came from the pre-#3464 rule and must not be read as trusted v2 evidence.
This script closes that gap for the corpus already on disk.

Two classes of episode are written:

STAMP-ONLY: The v2 rebuild produces the same edge topology as the stored edges.
Only causal_order_version is added; no event content changes.

RELINK: The v2 rebuild improves the stored edges (typically: more edges, or
corrects an ordering error that does not require commit-restamp). Written only
when the rebuild does not reduce edge count and all edges reference valid ids.
Episodes with backwards commit chains require repair_commit_order first; those
are handled by extract_session_episode.py --validate --fix, not this script.

Episodes skipped:
- Already v2 (causal_order_version == 2).
- Already carries a different causal_order_version (cannot classify as legacy).
- No events or invalid event ids (cannot rebuild safely).
- Rebuild would drop edges (conservative guard).
- Any exception during rebuild.

Exit codes match ADR-035:
  0  All processable episodes are now v2; nothing was left unversioned.
  1  One or more episodes could not be stamped.
  2  No episode files found, or unrecoverable argument error.

Provenance: every written file carries a migration_note field at the top level
recording this script name and the stamp date. A reader can identify which
episodes were migrated versus always-correct.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))

import extract_session_episode as _ex  # noqa: E402  (path insert required before import)

_MIGRATION_SCRIPT = "migrate_causal_version.py"
_CAUSAL_ORDER_VERSION = _ex.CAUSAL_ORDER_VERSION
_FAILURE_OUTCOMES = frozenset({"existing_version", "invalid_ids", "no_events", "skipped"})


def _edge_set(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Return the set of (source_id, target_id) leads_to pairs."""
    result: set[tuple[str, str]] = set()
    for evt in events:
        if not isinstance(evt, dict):
            continue
        src = evt.get("id", "")
        for tgt in evt.get("leads_to") or []:
            if isinstance(tgt, str):
                result.add((src, tgt))
    return result


def _rebuild_edges(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, str]:
    """Return a deep-copied, renumbered, relinked event list and a reason string.

    Returns (None, reason) on any failure. Returns (rebuilt, "") on success.
    """
    rebuilt = copy.deepcopy(events)
    try:
        _ex._renumber_events(rebuilt)
        _ex._link_sequential_events(rebuilt)
    except Exception as exc:
        return None, f"rebuild failed: {exc}"
    return rebuilt, ""


def _edge_count(events: list[dict[str, Any]]) -> int:
    return sum(len(e.get("leads_to") or []) for e in events if isinstance(e, dict))


def _apply_migration(
    path: Path,
    data: dict[str, Any],
    events: list[dict[str, Any]],
    rebuilt: list[dict[str, Any]],
    orig_edges: set[tuple[str, str]],
    orig_count: int,
    rebuilt_count: int,
    stamp_date: str,
) -> tuple[str, str]:
    """Write stamp-only or relink migration; return (outcome, reason)."""
    if _edge_set(rebuilt) == orig_edges:
        data["causal_order_version"] = _CAUSAL_ORDER_VERSION
        data["migration_note"] = (
            f"stamp_only by {_MIGRATION_SCRIPT} on {stamp_date}: "
            f"v2 edge rebuild agrees with stored edges"
        )
        try:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            return "skipped", f"write failed: {exc}"
        return "stamp_only", f"edges_unchanged={orig_count}"

    if rebuilt_count < orig_count:
        return "skipped", (
            f"refused: v2 rebuild would drop {orig_count - rebuilt_count} of {orig_count} edges"
        )

    data["events"] = rebuilt
    data["causal_order_version"] = _CAUSAL_ORDER_VERSION
    data["migration_note"] = (
        f"relinked by {_MIGRATION_SCRIPT} on {stamp_date}: edges {orig_count} -> {rebuilt_count}"
    )
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return "skipped", f"write failed: {exc}"
    return "relinked", f"edges {orig_count} -> {rebuilt_count}"


def _dry_run_classify(path: Path) -> str:
    """Classify an episode for dry-run reporting without writing."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "skipped"
    if not isinstance(data, dict):
        return "skipped"
    if "causal_order_version" in data:
        if data.get("causal_order_version") == _CAUSAL_ORDER_VERSION:
            return "already_v2"
        return "existing_version"
    events = data.get("events")
    if not isinstance(events, list) or not events:
        return "no_events"
    if _ex.validate_event_ids(events):
        return "invalid_ids"
    rebuilt, _ = _rebuild_edges(events)
    if rebuilt is None:
        return "skipped"
    if _edge_set(events) == _edge_set(rebuilt):
        return "stamp_only"
    if _edge_count(rebuilt) >= _edge_count(events):
        return "relinked"
    return "skipped"


def migrate_episode_file(path: Path, *, stamp_date: str) -> tuple[str, str]:
    """Attempt to stamp causal_order_version=2 on the episode at path.

    Returns (outcome, reason) where outcome is one of:
      "already_v2"     Already carries causal_order_version == 2.
      "existing_version" Already carries a different causal_order_version.
      "no_events"      Episode has no events; skipped.
      "invalid_ids"    Event ids fail validation; skipped.
      "stamp_only"     Wrote: added causal_order_version, edges unchanged.
      "relinked"       Wrote: rebuilt edge topology and stamped version.
      "skipped"        Could not write; reason explains why.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return "skipped", f"unreadable: {exc}"

    if not isinstance(data, dict):
        return "skipped", "top level is not an object"

    if "causal_order_version" in data:
        if data.get("causal_order_version") == _CAUSAL_ORDER_VERSION:
            return "already_v2", ""
        return "existing_version", "existing causal_order_version is not legacy"

    events = data.get("events")
    if not isinstance(events, list) or not events:
        return "no_events", ""

    id_problems = _ex.validate_event_ids(events)
    if id_problems:
        return "invalid_ids", id_problems[0]

    rebuilt, reason = _rebuild_edges(events)
    if rebuilt is None:
        return "skipped", reason

    orig_edges = _edge_set(events)
    orig_count = _edge_count(events)
    rebuilt_count = _edge_count(rebuilt)

    return _apply_migration(
        path, data, events, rebuilt, orig_edges, orig_count, rebuilt_count, stamp_date
    )


def _episode_paths(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.glob("*.json"))
    return [target]


def run_migrate(target: Path, *, dry_run: bool = False) -> int:
    """Run the migration over target. Return an ADR-035 exit code.

    dry_run reports what would happen without writing any file.
    """
    paths = _episode_paths(target)
    if not paths:
        print(
            json.dumps({"Error": f"No episode files found under {target}"}),
            file=sys.stderr,
        )
        return 2

    stamp_date = datetime.now(tz=timezone.utc).date().isoformat()
    counts: dict[str, int] = {
        "already_v2": 0,
        "existing_version": 0,
        "stamp_only": 0,
        "relinked": 0,
        "no_events": 0,
        "invalid_ids": 0,
        "skipped": 0,
    }

    for path in paths:
        if dry_run:
            outcome = _dry_run_classify(path)
        else:
            outcome, _reason = migrate_episode_file(path, stamp_date=stamp_date)
        counts[outcome] = counts.get(outcome, 0) + 1

    summary = dict(counts)
    summary["total"] = len(paths)
    summary["dry_run"] = dry_run
    print(json.dumps(summary))

    return 1 if any(counts.get(outcome, 0) > 0 for outcome in _FAILURE_OUTCOMES) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stamp causal_order_version=2 on legacy episode files (issue #3598)."
    )
    p.add_argument(
        "target",
        type=Path,
        help="Episode JSON file or directory of episode files.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing any file.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if ".." in args.target.parts:
        print(
            json.dumps({"Error": "Security: path must not contain traversal sequences."}),
            file=sys.stderr,
        )
        return 2
    target = args.target.resolve()
    if not target.exists():
        print(json.dumps({"Error": f"Path not found: {target}"}), file=sys.stderr)
        return 2
    return run_migrate(target, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
