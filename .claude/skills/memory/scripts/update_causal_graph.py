#!/usr/bin/env python3
"""Update the causal graph from episode data.

Processes episode files and updates the causal graph with decision nodes,
event nodes, causal chains, outcome tracking, and pattern extraction
from repeated sequences. Per ADR-038 Reflexion Memory Schema.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (update failed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load_causal_graph(graph_path: Path) -> dict[str, Any]:
    """Load causal graph from JSON file or return empty graph."""
    if not graph_path.is_file():
        return {"nodes": [], "edges": [], "patterns": []}
    try:
        data: dict[str, Any] = json.loads(graph_path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return {"nodes": [], "edges": [], "patterns": []}


def save_causal_graph(graph_path: Path, graph: dict[str, Any]) -> None:
    """Save causal graph to JSON file."""
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(graph, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_node_id(node_type: str, label: str) -> str:
    """Generate a deterministic node ID from type and label."""
    content = f"{node_type}:{label}"
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def add_causal_node(
    graph: dict[str, Any],
    node_type: str,
    label: str,
    episode_id: str,
) -> dict[str, Any] | None:
    """Add a node to the causal graph. Returns the node or None if duplicate."""
    node_id = generate_node_id(node_type, label)

    # Check for existing node
    for existing in graph["nodes"]:
        if existing["id"] == node_id:
            # Update episode list
            if episode_id not in existing.get("episodes", []):
                existing.setdefault("episodes", []).append(episode_id)
            result: dict[str, Any] = existing
            return result

    node = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "episodes": [episode_id],
        "created": datetime.now(UTC).isoformat(),
    }
    graph["nodes"].append(node)
    return node


def add_causal_edge(
    graph: dict[str, Any],
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float,
    episode_id: str,
) -> dict[str, Any] | None:
    """Add an edge to the causal graph.

    Returns the edge when this episode contributes new evidence, or None when
    the episode already contributed to this edge (idempotent no-op).

    An episode contributes to a given edge at most once. Reprocessing the same
    episode (a re-commit, an edit, or the pre-commit hook re-running) must not
    manufacture evidence: without the ``episodes`` guard, ``evidence_count`` and
    the running-average ``weight`` drift on every reprocess, so a byte-stable
    input produced a churning graph (#3034 follow-up).

    Legacy note: edges and patterns created before this guard carry no
    ``episodes`` provenance, so the code cannot tell whether a reprocessed
    episode already contributed. The first reprocess of such a legacy edge
    therefore bumps it once (a heuristic that may overcount if that episode had
    in fact contributed before) and records the episode id; every later
    reprocess of the same episode is then a correct no-op. A full rebuild is not
    used: it would only guess the missing provenance and would reset every
    ``created`` timestamp. The one-time bump is bounded and proportional to the
    staged episode, not a whole-graph churn.
    """
    # Check for existing edge
    for existing in graph["edges"]:
        if existing["source"] == source_id and existing["target"] == target_id:
            if episode_id in existing.get("episodes", []):
                # This episode already contributed; reprocess is a no-op.
                return None
            previous_evidence_count = int(
                existing.get("evidence_count", existing.get("count", 1)),
            )
            existing["weight"] = round(
                (existing["weight"] * previous_evidence_count + weight)
                / (previous_evidence_count + 1),
                2,
            )
            existing["evidence_count"] = previous_evidence_count + 1
            existing.setdefault("episodes", []).append(episode_id)
            existing.pop("count", None)
            edge_result: dict[str, Any] = existing
            return edge_result

    edge = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "weight": weight,
        "evidence_count": 1,
        "episodes": [episode_id],
        "created": datetime.now(UTC).isoformat(),
    }
    graph["edges"].append(edge)
    return edge


def add_pattern(
    graph: dict[str, Any],
    name: str,
    description: str,
    trigger: str,
    action: str,
    success_rate: float,
    episode_id: str,
) -> dict[str, Any] | None:
    """Add a pattern to the causal graph.

    Returns the pattern when this episode contributes a new occurrence, or None
    when the episode already contributed (idempotent no-op). Reprocessing the
    same episode must not inflate ``occurrences`` or drift ``success_rate``
    (#3034 follow-up); the ``episodes`` guard enforces at-most-once contribution
    for patterns created with provenance. Legacy patterns created before this
    guard carry no ``episodes`` list, so the same heuristic as add_causal_edge
    applies: the first reprocess bumps ``occurrences`` and ``success_rate`` once
    (and may overcount if that episode had already contributed) before recording
    the episode id; every later reprocess of the same episode is then a no-op.
    """
    # Check for existing pattern with same name
    for existing in graph["patterns"]:
        if existing["name"] == name:
            if episode_id in existing.get("episodes", []):
                # This episode already contributed; reprocess is a no-op.
                return None
            # Occurrence-weighted running average, consistent with
            # add_causal_edge. A plain (old + new) / 2 over-weights the most
            # recent episode: contributions 1.0, 1.0, 0.0 must average to 0.67,
            # not the 0.50 the two-point form produced (#3034 review).
            previous_occurrences = int(existing.get("occurrences", 1))
            existing["success_rate"] = round(
                (existing["success_rate"] * previous_occurrences + success_rate)
                / (previous_occurrences + 1),
                2,
            )
            existing["occurrences"] = previous_occurrences + 1
            existing.setdefault("episodes", []).append(episode_id)
            pattern_result: dict[str, Any] = existing
            return pattern_result

    pattern = {
        "name": name,
        "description": description,
        "trigger": trigger,
        "action": action,
        "success_rate": success_rate,
        "occurrences": 1,
        "episodes": [episode_id],
        "created": datetime.now(UTC).isoformat(),
    }
    graph["patterns"].append(pattern)
    return pattern


def get_episode_files(
    path: Path, since: str | None = None,
) -> list[Path]:
    """Get episode files to process."""
    if path.is_file():
        return [path]

    if not path.is_dir():
        return []

    files = sorted(path.glob("episode-*.json"))

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            return list(files)

        filtered = []
        for f in files:
            try:
                content = json.loads(f.read_text(encoding="utf-8"))
                episode_date = datetime.fromisoformat(content["timestamp"])
                if episode_date >= since_dt:
                    filtered.append(f)
            except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
                print(
                    f"WARNING: Skipping malformed episode file: {f} - {e}",
                    file=sys.stderr,
                )
        return filtered

    return list(files)


def get_decision_patterns(episode: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract decision patterns from an episode."""
    patterns = []
    decisions = episode.get("decisions", [])

    for decision in decisions:
        is_success = decision.get("outcome") == "success"
        trigger = (
            decision.get("context")
            or f"When {decision.get('type', 'unknown')} decision needed"
        )
        chosen = decision.get("chosen", "")

        if is_success:
            patterns.append({
                "name": f"{decision.get('type', 'unknown')} pattern",
                "description": f"Pattern from {episode.get('id', 'unknown')}",
                "trigger": trigger,
                "action": chosen,
                "success": True,
            })
        else:
            patterns.append({
                "name": f"{decision.get('type', 'unknown')} anti-pattern",
                "description": f"Anti-pattern from {episode.get('id', 'unknown')}",
                "trigger": trigger,
                "action": f"AVOID: {chosen}",
                "success": False,
            })

    return patterns


def build_causal_chains(episode: dict[str, Any]) -> list[dict[str, Any]]:
    """Build causal chains from episode events."""
    chains = []
    events = episode.get("events", [])
    decisions = episode.get("decisions", [])

    # Error -> recovery chains
    for idx, event in enumerate(events):
        if event.get("type") != "error":
            continue

        following = events[idx + 1:idx + 6]
        recovery = None
        for f_event in following:
            if (
                f_event.get("type") == "milestone"
                and re.search(r'fix|recover|resolve', f_event.get("content", ""), re.IGNORECASE)
            ):
                recovery = f_event
                break

        if recovery:
            chains.append({
                "from_type": "error",
                "from_label": event.get("content", ""),
                "to_type": "outcome",
                "to_label": recovery.get("content", ""),
                "edge_type": "causes",
                "weight": 0.8,
            })

    # Decision -> outcome chains
    for decision in decisions:
        chosen = decision.get("chosen", "")
        if not chosen:
            continue

        keywords = chosen.split()[:3]
        if not keywords:
            continue

        pattern = "|".join(re.escape(kw) for kw in keywords)
        for event in events:
            content = event.get("content", "")
            if re.search(pattern, content, re.IGNORECASE):
                chains.append({
                    "from_type": "decision",
                    "from_label": chosen,
                    "to_type": event.get("type", "unknown"),
                    "to_label": content,
                    "edge_type": "causes",
                    "weight": 0.6,
                })

    return chains


def collect_contributions(
    episode: dict[str, Any],
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, str, str, str, str, float]],
    list[tuple[str, str, str, str, float]],
]:
    """Derive the nodes, edges, and patterns an episode currently produces.

    Single source of truth for an episode's contribution set. ``process_episode``
    feeds both the add path and the stale-prune keep-set from this one
    derivation so the two cannot drift. A keep-set built from a separate mirror
    of this logic would miss a label form (the decision loop and the chain
    endpoints label the same decision differently) and strip ``episode_id`` from
    a node the episode still supports.

    Node tuple is ``(type, label)``; edge tuple is
    ``(from_type, from_label, to_type, to_label, edge_type, weight)``; pattern
    tuple is ``(name, description, trigger, action, success_rate)``.
    """
    nodes: list[tuple[str, str]] = []
    for decision in episode.get("decisions", []):
        node_label = f"{decision.get('type', 'unknown')}: {decision.get('chosen', '')}"
        nodes.append(("decision", node_label))
    for event in episode.get("events", []):
        event_type = event.get("type", "unknown")
        nodes.append((event_type, f"{event_type}: {event.get('content', '')}"))
    outcome_label = f"Outcome: {episode.get('outcome', 'unknown')} - {episode.get('task', '')}"
    nodes.append(("outcome", outcome_label))

    edges: list[tuple[str, str, str, str, str, float]] = []
    for chain in build_causal_chains(episode):
        edges.append((
            chain["from_type"], chain["from_label"],
            chain["to_type"], chain["to_label"],
            chain["edge_type"], chain["weight"],
        ))

    patterns: list[tuple[str, str, str, str, float]] = []
    for pat in get_decision_patterns(episode):
        success_rate = 1.0 if pat["success"] else 0.0
        patterns.append((
            pat["name"], pat["description"], pat["trigger"],
            pat["action"], success_rate,
        ))
    return nodes, edges, patterns


def _remove_from_elements(
    elements: list[dict[str, Any]],
    episode_id: str,
    keep_keys: frozenset[Any],
    key_of: Callable[[dict[str, Any]], Any],
    count_field: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Strip ``episode_id`` from elements whose key is not in ``keep_keys``.

    An element supported only by this episode is dropped. One with other
    supporting episodes keeps its averaged ``weight``/``success_rate`` and
    decrements ``count_field``. Leaving the average is exact under the generator
    invariant that every episode contributes an identical value to a given key:
    chain type fixes an edge's node-type prefixes and weight (0.8 for
    error->recovery, 0.6 for decision->outcome), and a pattern name encodes its
    success_rate (1.0 for ``pattern``, 0.0 for ``anti-pattern``). Returns
    ``(survivors, removed_count)``.
    """
    survivors: list[dict[str, Any]] = []
    removed = 0
    for element in elements:
        episodes = element.get("episodes", [])
        if episode_id not in episodes or key_of(element) in keep_keys:
            survivors.append(element)
            continue
        remaining = [e for e in episodes if e != episode_id]
        if not remaining:
            removed += 1
            continue
        element["episodes"] = remaining
        if count_field is not None:
            current = int(element.get(count_field, element.get("count", len(episodes))))
            element[count_field] = max(len(remaining), current - 1)
            element.pop("count", None)
        survivors.append(element)
    return survivors, removed


def remove_episode_contributions(
    graph: dict[str, Any],
    episode_id: str,
    *,
    keep_node_ids: frozenset[str] = frozenset(),
    keep_edge_keys: frozenset[tuple[str, str]] = frozenset(),
    keep_pattern_names: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Remove an episode's stale contributions from the graph.

    Elements whose key is in a keep-set are left intact (the episode still
    produces them). Empty keep-sets remove every trace of the episode, the
    prune path for a deleted episode (issue #3039). Returns per-kind removed
    counts.
    """
    nodes, nodes_removed = _remove_from_elements(
        graph["nodes"], episode_id, keep_node_ids, lambda n: n["id"], None,
    )
    edges, edges_removed = _remove_from_elements(
        graph["edges"], episode_id, keep_edge_keys,
        lambda e: (e["source"], e["target"]), "evidence_count",
    )
    patterns, patterns_removed = _remove_from_elements(
        graph["patterns"], episode_id, keep_pattern_names,
        lambda p: p["name"], "occurrences",
    )
    graph["nodes"] = nodes
    graph["edges"] = edges
    graph["patterns"] = patterns
    return {
        "nodes": nodes_removed,
        "edges": edges_removed,
        "patterns": patterns_removed,
    }


def process_episode(
    graph: dict[str, Any],
    episode: dict[str, Any],
    episode_id: str,
    dry_run: bool,
) -> dict[str, int]:
    """Apply one episode with replace semantics: prune stale, then re-add.

    Reprocessing an edited episode drops the nodes, edges, and patterns it no
    longer produces (issue #3039 edit-shrinks case) while leaving unchanged
    elements byte-stable (issue #3034 idempotency: nothing is pruned and every
    add is a no-op). Returns stat deltas.
    """
    nodes, edges, patterns = collect_contributions(episode)

    zero = {
        "nodes_added": 0, "edges_added": 0, "patterns_added": 0,
        "nodes_removed": 0, "edges_removed": 0, "patterns_removed": 0,
    }
    if dry_run:
        for _node_type, label in nodes:
            print(f"  [DRY] Would add node: {label}", file=sys.stderr)
        for _ft, from_label, _tt, to_label, edge_type, _weight in edges:
            print(
                f"  [DRY] Would add edge: {from_label} "
                f"--[{edge_type}]--> {to_label}",
                file=sys.stderr,
            )
        for name, *_rest in patterns:
            print(f"  [DRY] Would add pattern: {name}", file=sys.stderr)
        return zero

    keep_node_ids = {generate_node_id(node_type, label) for node_type, label in nodes}
    for from_type, from_label, to_type, to_label, _et, _w in edges:
        keep_node_ids.add(generate_node_id(from_type, from_label))
        keep_node_ids.add(generate_node_id(to_type, to_label))
    keep_edge_keys = {
        (generate_node_id(ft, fl), generate_node_id(tt, tl))
        for ft, fl, tt, tl, _et, _w in edges
    }
    keep_pattern_names = {name for name, *_rest in patterns}

    removed = remove_episode_contributions(
        graph, episode_id,
        keep_node_ids=frozenset(keep_node_ids),
        keep_edge_keys=frozenset(keep_edge_keys),
        keep_pattern_names=frozenset(keep_pattern_names),
    )

    stats = {
        "nodes_added": 0, "edges_added": 0, "patterns_added": 0,
        "nodes_removed": removed["nodes"],
        "edges_removed": removed["edges"],
        "patterns_removed": removed["patterns"],
    }
    for node_type, label in nodes:
        if add_causal_node(graph, node_type, label, episode_id):
            stats["nodes_added"] += 1
    for from_type, from_label, to_type, to_label, edge_type, weight in edges:
        from_node = add_causal_node(graph, from_type, from_label, episode_id)
        to_node = add_causal_node(graph, to_type, to_label, episode_id)
        if from_node and to_node:
            edge = add_causal_edge(
                graph, from_node["id"], to_node["id"],
                edge_type, weight, episode_id,
            )
            if edge:
                stats["edges_added"] += 1
    for name, description, trigger, action, success_rate in patterns:
        if add_pattern(
            graph, name, description, trigger, action, success_rate, episode_id,
        ):
            stats["patterns_added"] += 1
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update the causal graph from episode data.",
    )
    parser.add_argument(
        "--episode-path", type=Path, default=None,
        help="Path to episode file or directory (default: .agents/memory/episodes/)",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Only process episodes since this ISO date",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--graph-path", type=Path, default=None,
        help="Path to causal graph JSON file",
    )
    parser.add_argument(
        "--deleted-episode-id", action="append", default=None, metavar="ID",
        help="Episode id whose contributions to prune (repeatable). Use when "
             "an episode file was deleted so its stale nodes, edges, and "
             "patterns are removed from the graph.",
    )
    return parser


def _resolve_path(candidate: Path | None, default: Path) -> Path | None:
    """Resolve a user-supplied path, rejecting traversal. None means unsafe."""
    if candidate is None:
        return default
    if ".." in candidate.parts:
        return None
    return candidate.resolve()


def _apply_episode_files(
    graph: dict[str, Any],
    episode_files: list[Path],
    dry_run: bool,
    stats: dict[str, int],
) -> None:
    """Process each episode file with replace semantics, folding in stats."""
    for file_path in episode_files:
        print(f"\nProcessing: {file_path.name}", file=sys.stderr)
        try:
            episode = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"WARNING: Failed to process episode file '{file_path}': {e}",
                file=sys.stderr,
            )
            continue
        episode_id = episode.get("id", file_path.stem)
        deltas = process_episode(graph, episode, episode_id, dry_run)
        for key, value in deltas.items():
            stats[key] += value
        stats["episodes_processed"] += 1


def _apply_deletions(
    graph: dict[str, Any],
    deleted_ids: list[str],
    dry_run: bool,
    stats: dict[str, int],
) -> None:
    """Prune every deleted episode's contributions, folding in stats."""
    for deleted_id in deleted_ids:
        print(f"\nPruning deleted episode: {deleted_id}", file=sys.stderr)
        if dry_run:
            print(
                f"  [DRY] Would prune contributions from {deleted_id}",
                file=sys.stderr,
            )
            continue
        removed = remove_episode_contributions(graph, deleted_id)
        stats["nodes_removed"] += removed["nodes"]
        stats["edges_removed"] += removed["edges"]
        stats["patterns_removed"] += removed["patterns"]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    base_path = script_dir.parent.parent.parent.parent
    episode_path = _resolve_path(
        args.episode_path, base_path / ".agents" / "memory" / "episodes",
    )
    graph_path = _resolve_path(
        args.graph_path,
        base_path / ".agents" / "memory" / "causality" / "causal-graph.json",
    )
    if episode_path is None or graph_path is None:
        print(
            "Security: path must not contain traversal sequences.",
            file=sys.stderr,
        )
        return 2

    print("Updating causal graph...", file=sys.stderr)

    if args.dry_run:
        print("[DRY RUN] No changes will be made", file=sys.stderr)

    episode_files = get_episode_files(episode_path, args.since)
    deleted_ids = args.deleted_episode_id or []

    if not episode_files and not deleted_ids:
        print("No episode files found to process.", file=sys.stderr)
        return 0

    print(
        f"Found {len(episode_files)} episode(s) to process, "
        f"{len(deleted_ids)} deletion(s)",
        file=sys.stderr,
    )

    graph = load_causal_graph(graph_path)

    stats = {
        "episodes_processed": 0,
        "nodes_added": 0,
        "edges_added": 0,
        "patterns_added": 0,
        "nodes_removed": 0,
        "edges_removed": 0,
        "patterns_removed": 0,
    }

    _apply_episode_files(graph, episode_files, args.dry_run, stats)
    _apply_deletions(graph, deleted_ids, args.dry_run, stats)

    # Save graph
    if not args.dry_run:
        try:
            save_causal_graph(graph_path, graph)
        except OSError as e:
            print(f"ERROR: Failed to save causal graph: {e}", file=sys.stderr)
            return 1

    # Summary
    print("", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print("Causal Graph Update Complete", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print(f"  Episodes processed: {stats['episodes_processed']}", file=sys.stderr)
    print(f"  Nodes added:        {stats['nodes_added']}", file=sys.stderr)
    print(f"  Edges added:        {stats['edges_added']}", file=sys.stderr)
    print(f"  Patterns added:     {stats['patterns_added']}", file=sys.stderr)
    print(f"  Nodes removed:      {stats['nodes_removed']}", file=sys.stderr)
    print(f"  Edges removed:      {stats['edges_removed']}", file=sys.stderr)
    print(f"  Patterns removed:   {stats['patterns_removed']}", file=sys.stderr)

    if args.dry_run:
        print("\n[DRY RUN] No actual changes were made", file=sys.stderr)

    # Output stats as JSON to stdout
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
