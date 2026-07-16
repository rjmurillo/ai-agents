#!/usr/bin/env python3
"""Backfill episodes[] provenance on legacy causal-graph edges and patterns.

Edges and patterns created before the episodes[] provenance field (issue #3034)
carry no episodes[] entry. The per-episode prune path (issue #3039) cannot tell
"no provenance was ever recorded" apart from "no surviving episode supports
this", so it cannot retract these legacy contributions. This one-time,
idempotent backfill re-derives each legacy item's originating episode ids from
the surviving episode corpus and records them in episodes[], making the items
attributable so the prune path can reach them.

Recoverability. Attribution is recovered by replaying the deterministic
derivation in update_causal_graph.py over every episode file. Edge
(source, target) keys and pattern names are byte-stable functions of episode
content (node ids are sha256 hashes of type+label), so an edge or pattern in the
graph maps back to exactly the episodes whose content reproduces it. Items that
no surviving episode reproduces (test seed rows such as the p001 "Good pattern"
fixture, which carry id/last_used fields the generator never writes) have no
recoverable provenance and are left untouched; they remain the genuinely
unattributable case the #3039 path treats as permanent.

Scope. Only the episodes[] field is written, and only when re-derivation adds an
id that was not already recorded. weight, evidence_count, success_rate,
occurrences, created, and every node are left untouched, so this is a provenance
backfill, not a regeneration; it does not drag the whole-graph churn that #3034
rejected. episodes[] is written as the sorted union of existing and derived ids,
so a second run rewrites a byte-identical file (idempotent, no double-append).

Contract source: this script reuses update_causal_graph.py's public derivation
functions (generate_node_id, build_causal_chains, get_decision_patterns) rather
than re-deriving labels, so attribution stays byte-identical to what the
generator produced. See .claude/rules/canonical-source-mirror.md.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (save failed)
    2 - Configuration error (path traversal)
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

import update_causal_graph as ucg  # noqa: E402  (path set above)

EdgeKey = tuple[str, str]


def derive_attribution(
    episode_files: list[Path],
) -> tuple[dict[EdgeKey, set[str]], dict[str, set[str]]]:
    """Map edge keys and pattern names to the episode ids that reproduce them.

    Replays update_causal_graph's derivation over each episode. Malformed
    episode files are skipped (they contribute no attribution), matching the
    generator's own tolerance.
    """
    edge_attr: dict[EdgeKey, set[str]] = {}
    pattern_attr: dict[str, set[str]] = {}

    for file_path in episode_files:
        try:
            episode = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        episode_id = episode.get("id") or file_path.stem

        for chain in ucg.build_causal_chains(episode):
            source_id = ucg.generate_node_id(chain["from_type"], chain["from_label"])
            target_id = ucg.generate_node_id(chain["to_type"], chain["to_label"])
            edge_attr.setdefault((source_id, target_id), set()).add(episode_id)

        for pattern in ucg.get_decision_patterns(episode):
            pattern_attr.setdefault(pattern["name"], set()).add(episode_id)

    return edge_attr, pattern_attr


def _merge_episodes(item: dict[str, Any], derived_ids: set[str]) -> bool:
    """Union derived_ids into item['episodes'] (sorted). Return True if changed."""
    existing = item.get("episodes") or []
    merged = sorted(set(existing) | derived_ids)
    if merged == existing:
        return False
    item["episodes"] = merged
    return True


def backfill_graph(
    graph: dict[str, Any],
    edge_attr: dict[EdgeKey, set[str]],
    pattern_attr: dict[str, set[str]],
) -> dict[str, int]:
    """Populate episodes[] on edges and patterns from re-derived attribution.

    Mutates graph in place. Returns counts of items whose provenance changed.
    """
    stats = {"edges_backfilled": 0, "patterns_backfilled": 0}

    for edge in graph.get("edges", []):
        derived = edge_attr.get((edge.get("source"), edge.get("target")))
        if derived and _merge_episodes(edge, derived):
            stats["edges_backfilled"] += 1

    for pattern in graph.get("patterns", []):
        derived = pattern_attr.get(pattern.get("name"))
        if derived and _merge_episodes(pattern, derived):
            stats["patterns_backfilled"] += 1

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill episodes[] provenance on legacy causal-graph items.",
    )
    parser.add_argument(
        "--graph-path", type=Path, required=True,
        help="Path to the causal graph JSON file to backfill",
    )
    parser.add_argument(
        "--episode-path", type=Path, required=True,
        help="Path to the episode file or directory to attribute from",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be backfilled without writing the graph",
    )
    return parser


def _resolve_path(candidate: Path) -> Path | None:
    """Resolve a CLI path, rejecting traversal. Returns None on traversal."""
    if ".." in candidate.parts:
        return None
    return candidate.resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    graph_path = _resolve_path(args.graph_path)
    episode_path = _resolve_path(args.episode_path)
    if graph_path is None or episode_path is None:
        print("Security: path must not contain traversal sequences.", file=sys.stderr)
        return 2

    episode_files = ucg.get_episode_files(episode_path)
    if not episode_files:
        print("No episode files found; nothing to attribute.", file=sys.stderr)

    graph = ucg.load_causal_graph(graph_path)
    edge_attr, pattern_attr = derive_attribution(episode_files)
    stats = backfill_graph(graph, edge_attr, pattern_attr)

    changed = stats["edges_backfilled"] + stats["patterns_backfilled"]
    if args.dry_run:
        print(f"[DRY RUN] Would backfill {changed} item(s).", file=sys.stderr)
    elif changed:
        try:
            ucg.save_causal_graph(graph_path, graph)
        except OSError as exc:
            print(f"ERROR: failed to save causal graph: {exc}", file=sys.stderr)
            return 1

    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
