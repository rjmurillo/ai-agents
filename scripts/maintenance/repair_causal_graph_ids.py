"""Restore content-derived node ids in the committed causal graph.

Issue #3367: 13 of the graph's nodes carry an id that
``update_causal_graph.generate_node_id`` does not reproduce from their own
``type`` and ``label``. The string that was hashed is not recoverable: an
exhaustive sweep on the simplest of them (12 candidate types by 8 label
variants by 8 separators by 8 hash algorithms, plus every truncation length,
over 3840 hypotheses) found nothing. So the ids are not decoded, they are
recomputed from the content that survived.

A node whose id is not derivable from its content is unreachable by the
generator: the next episode mentioning the same thing hashes to a different id
and adds a second node instead of extending the first. Evidence then splits
across two records that no query joins.

Two repairs, decided by whether the canonical id is already taken:

- taken: the duplicate pair is folded into the canonical node. Episodes union,
  the earliest ``created`` wins, and edges pointing at the stale id are moved.
- free: the node keeps everything and only its id changes.

Rerunning is a no-op, so this is safe to run again if ``generate_node_id`` ever
changes shape again (it has twice: #1146 and #3358).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _ROOT / ".claude" / "skills" / "memory" / "scripts"
if str(_GENERATOR) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_GENERATOR))

from update_causal_graph import (  # noqa: E402  (path set above)
    _legacy_backfill_contributions,
    _recompute_edge,
    generate_node_id,
)

DEFAULT_GRAPH = _ROOT / ".agents" / "memory" / "causality" / "causal-graph.json"


def canonical_id(node: dict[str, Any]) -> str:
    """The id the generator would derive from this node's own content."""
    # Annotated because the generator is imported off sys.path (it lives under
    # a skill directory, not an importable package), so mypy sees it untyped.
    derived: str = generate_node_id(str(node.get("type", "")), str(node.get("label", "")))
    return derived


def build_id_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    """Map every stale node id to the id its content derives."""
    return {
        node["id"]: canonical for node in nodes if (canonical := canonical_id(node)) != node["id"]
    }


def _fold(into: dict[str, Any], other: dict[str, Any]) -> None:
    """Merge a duplicate node into the one that keeps the canonical id."""
    episodes = set(into.get("episodes") or []) | set(other.get("episodes") or [])
    into["episodes"] = sorted(episodes)
    created = [value for value in (into.get("created"), other.get("created")) if value]
    if created:
        into["created"] = min(created)


def repair_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the node list with every id reproducible from its own content."""
    repaired: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        target = canonical_id(node)
        if (existing := by_id.get(target)) is not None:
            _fold(existing, node)
            continue
        node = dict(node, id=target)
        by_id[target] = node
        repaired.append(node)
    return repaired


def repair_edges(edges: list[dict[str, Any]], id_map: dict[str, str]) -> list[dict[str, Any]]:
    """Repoint edges onto the repaired ids, folding any pair that collapses.

    Two edges can land on the same pair once their endpoints are rewritten. The
    generator allows one edge per (source, target), so they are folded the way
    it folds them: union the per-episode ``contributions`` and re-derive the
    weight and evidence count from that map.
    """
    repaired: list[dict[str, Any]] = []
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in edges:
        source = id_map.get(edge.get("source", ""), edge.get("source", ""))
        target = id_map.get(edge.get("target", ""), edge.get("target", ""))
        moved = dict(edge, source=source, target=target)
        if (existing := by_pair.get((source, target))) is None:
            by_pair[(source, target)] = moved
            repaired.append(moved)
            continue
        contributions = _legacy_backfill_contributions(existing, "weight", "evidence_count")
        contributions.update(_legacy_backfill_contributions(moved, "weight", "evidence_count"))
        _recompute_edge(existing, contributions)
    return repaired


def repair(graph: dict[str, Any]) -> dict[str, Any]:
    """Return the graph with reproducible node ids and edges pointing at them."""
    nodes = list(graph.get("nodes") or [])
    id_map = build_id_map(nodes)
    repaired = dict(graph)
    repaired["nodes"] = repair_nodes(nodes)
    repaired["edges"] = repair_edges(list(graph.get("edges") or []), id_map)
    return repaired


def unreproducible(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Every node whose id its own content does not derive."""
    return [node for node in (graph.get("nodes") or []) if canonical_id(node) != node["id"]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("graph", type=Path, nargs="?", default=DEFAULT_GRAPH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report unreproducible ids and exit 1 without writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Return 0 when the graph is clean, 1 under --check when it is not."""
    args = parse_args(argv)
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    stale = unreproducible(graph)

    for node in stale:
        print(f"{node['id']} -> {canonical_id(node)}  {node.get('type')}: {node.get('label', '')}")

    if args.check:
        print(f"{len(stale)} node id(s) do not reproduce from their content")
        return 1 if stale else 0

    if not stale:
        print("every node id already reproduces from its content")
        return 0

    repaired = repair(graph)
    args.graph.write_text(json.dumps(repaired, indent=2) + "\n", encoding="utf-8")
    print(
        f"repaired {len(stale)} node id(s); "
        f"{len(graph['nodes']) - len(repaired['nodes'])} duplicate(s) folded, "
        f"{len(graph.get('edges') or []) - len(repaired['edges'])} edge(s) folded"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
