#!/usr/bin/env python3
"""Restore causal edges in episodes whose timestamps were flattened.

``merge_preserving`` used to normalize every event timestamp to session
midnight. With a commit and a milestone sharing one timestamp,
``_event_order_relation`` returns None per the #3464 incomparability rule and
every milestone-to-commit edge is dropped, so the episode is left flat
(issue #4071). The extractor no longer flattens a commit event, but that only
protects episodes regenerated from a session log that still exists.

This repairs an episode in place from the file alone: it restamps each commit
event with its real committer date and rebuilds the chain. An episode whose
commit SHA no longer resolves in the local object database carries no ordering
evidence, so it is reported as unrepairable rather than given a fabricated
order.

EXIT CODES:
  0 - success (repaired, or already sound, or --check found nothing)
  1 - logic error (an episode is unreadable or its causal graph is invalid)
  2 - configuration error (episodes directory missing)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from extract_session_episode import (  # noqa: E402
    EpisodeValidationError,
    _as_dict,
    _as_list,
    _commit_sha,
    _event_order_relation,
    _git_commit_timestamp,
    _link_sequential_events,
    _norm,
    default_episodes_dir,
    validate_episode_causal_graph,
)


def _commit_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [evt for evt in events if _norm(evt.get("type")) == "commit"]


def restamp_commit_events(events: list[dict[str, Any]]) -> int:
    """Give each commit event its real committer date. Returns changes made."""
    changed = 0
    for event in _commit_events(events):
        sha = _commit_sha(event)
        real = _git_commit_timestamp(sha) if sha else None
        if real and real != event.get("timestamp"):
            event["timestamp"] = real
            changed += 1
    return changed


def _is_flat(events: list[dict[str, Any]], edges: int) -> bool:
    """An episode with commit events and no causal chain lost its ordering."""
    return edges == 0 and bool(_commit_events(events)) and len(events) > 1


def count_edges(events: list[dict[str, Any]]) -> int:
    """Total ``leads_to`` entries. Each edge is written into both endpoints."""
    return sum(len(_as_list(_as_dict(evt).get("leads_to"))) for evt in events)


def _edge_set(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Every ``leads_to`` edge as a (source id, target id) pair."""
    edges: set[tuple[str, str]] = set()
    for evt in events:
        source = str(_as_dict(evt).get("id"))
        for target in _as_list(_as_dict(evt).get("leads_to")):
            edges.add((source, str(target)))
    return edges


def _all_removed_now_incomparable(
    events: list[dict[str, Any]], removed: set[tuple[str, str]]
) -> bool:
    """True when every removed edge joins events that are now incomparable.

    Uses the post-restamp timestamps, so an edge the old flattened stamps
    fabricated between a synthetic-midnight milestone and a commit reads as
    incomparable here and may be dropped. An edge between events the order
    relation still ranks is evidence, and dropping it is refused. A dangling
    endpoint counts as removable: the rebuild validates ids, so the old edge
    referenced an event that no longer exists.
    """
    by_id = {str(_as_dict(evt).get("id")): evt for evt in events}
    timestamps = validate_episode_causal_graph(events, validate_order=False)
    for source, target in removed:
        left = by_id.get(source)
        right = by_id.get(target)
        if left is None or right is None:
            continue
        if _event_order_relation(left, right, timestamps) is not None:
            return False
    return True


def repair_episode(path: Path) -> dict[str, Any]:
    """Repair one episode file in place. Returns a per-file report.

    ``status`` is one of ``repaired``, ``unchanged``, or ``unrepairable``.
    ``unrepairable`` means the episode is flat and no commit SHA in it
    resolves, so nothing separates the commit from a same-day milestone.
    """
    episode = json.loads(path.read_text(encoding="utf-8"))
    events = [_as_dict(evt) for evt in _as_list(episode.get("events"))]
    if not events:
        return {"path": str(path), "status": "unchanged", "edges": 0}

    before_edges = count_edges(events)
    before_set = _edge_set(events)
    restamped = restamp_commit_events(events)
    _link_sequential_events(events)
    after_edges = count_edges(events)
    after_set = _edge_set(events)

    # A rebuild may remove an edge only when the pair it joined is now
    # classified incomparable (the false milestone-to-commit edges of issue
    # #4847). A removed edge between still-comparable events means the file
    # carries evidence this pass cannot see, so leave it alone. A raw count
    # comparison cannot make that distinction: it preserved the exact #4847
    # edge this tool exists to remove (PR #5058 review).
    removed = before_set - after_set
    evidence_removed = removed and not _all_removed_now_incomparable(events, removed)
    if evidence_removed or after_set == before_set:
        status = "unrepairable" if _is_flat(events, before_edges) else "unchanged"
        report = {"path": str(path), "status": status, "edges": before_edges}
        if status == "unrepairable":
            if restamped > 0:
                report["reason"] = (
                    "commits restamped but non-commit events at synthetic midnight "
                    "are incomparable (issue #4847)"
                )
            else:
                report["reason"] = "no commit sha resolves in the local object database"
        return report

    episode["events"] = events
    path.write_text(json.dumps(episode, indent=2) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "status": "repaired",
        "edges": after_edges,
        "edges_before": before_edges,
        "removed_incomparable_edges": len(removed),
    }


def _episode_paths(args: argparse.Namespace) -> list[Path]:
    if args.paths:
        return [Path(candidate) for candidate in args.paths]
    return sorted(Path(args.episodes_dir).glob("*.json"))


def _summarize(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "Scanned": len(reports),
        "Repaired": sum(1 for r in reports if r["status"] == "repaired"),
        "Unchanged": sum(1 for r in reports if r["status"] == "unchanged"),
        "Unrepairable": [r["path"] for r in reports if r["status"] == "unrepairable"],
        "Invalid": [
            {"path": r["path"], "reason": r["reason"]}
            for r in reports
            if r["status"] == "invalid"
        ],
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="Episode files. Default: the whole corpus.")
    parser.add_argument(
        "--episodes-dir",
        default=str(default_episodes_dir()),
        help="Directory scanned when no paths are given.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report what would change without writing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Repair every named episode, or the whole corpus."""
    args = _parse_args(argv)
    if not args.paths and not Path(args.episodes_dir).is_dir():
        print(json.dumps({"Error": f"no such directory: {args.episodes_dir}"}), file=sys.stderr)
        return 2

    reports = [_inspect_or_repair(path, check=args.check) for path in _episode_paths(args)]
    summary = _summarize(reports)
    print(json.dumps(summary, indent=2))
    # One malformed episode must not stop the corpus pass, but it is still a
    # defect the caller has to see, so it lands in the summary and the exit code.
    return 1 if summary["Invalid"] else 0


def _inspect_or_repair(path: Path, *, check: bool) -> dict[str, Any]:
    """Repair the episode, restoring the original bytes when check is set."""
    original = path.read_bytes() if check else b""
    try:
        return repair_episode(path)
    except (OSError, ValueError, EpisodeValidationError) as exc:
        return {"path": str(path), "status": "invalid", "edges": 0, "reason": str(exc)}
    finally:
        if check:
            path.write_bytes(original)


if __name__ == "__main__":
    sys.exit(main())
