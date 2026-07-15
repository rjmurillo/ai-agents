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


# Reserved prefix for anonymous legacy evidence. Edges/patterns created before
# #3034 stored an aggregate ``count``/``evidence_count`` with no per-episode
# provenance. That evidence cannot be attributed to any episode id, so it is
# carried as synthetic contributions under this prefix: they keep the derived
# mean and evidence count correct, are never matched by an episode-id removal
# (so anonymous evidence survives a prune), and are filtered out of ``episodes``.
# NUL cannot appear in a real episode id, so collisions are impossible.
_LEGACY_PREFIX = "\x00legacy:"


def _is_episode_key(key: str) -> bool:
    return not key.startswith(_LEGACY_PREFIX)


def _legacy_backfill_contributions(
    item: dict[str, Any], value_key: str, count_key: str,
) -> dict[str, float]:
    """Return the ``contributions`` map for an edge or pattern, backfilling it
    once from legacy state when absent.

    - A post-#3039 item already has ``contributions``; return it verbatim.
    - A #3034-era item has an ``episodes`` list plus a running-average value but
      no per-episode values; seed each episode's contribution with the recorded
      average (the best available estimate, which preserves the mean).
    - A pre-#3034 item has a bare aggregate count with no ``episodes``; synthesize
      that many anonymous contributions under ``_LEGACY_PREFIX`` at the recorded
      average, so its evidence is preserved but immovable by episode id.
    """
    contributions = item.get("contributions")
    if isinstance(contributions, dict):
        return {str(k): float(v) for k, v in contributions.items()}
    average = float(item.get(value_key, 0.0))
    episodes = item.get("episodes") or []
    if episodes:
        return {str(ep): average for ep in episodes}
    count = int(item.get(count_key, item.get("count", 0)) or 0)
    return {f"{_LEGACY_PREFIX}{i}": average for i in range(count)}


def _recompute(
    item: dict[str, Any],
    contributions: dict[str, float],
    value_key: str,
    count_key: str,
) -> None:
    """Write the derived fields of an edge/pattern from its contributions.

    The value (``weight``/``success_rate``) is the mean over all contributions;
    the count (``evidence_count``/``occurrences``) is their number; ``episodes``
    lists only the real episode keys (anonymous legacy keys are excluded).
    """
    item["contributions"] = contributions
    item["episodes"] = sorted(k for k in contributions if _is_episode_key(k))
    item[count_key] = len(contributions)
    item[value_key] = round(sum(contributions.values()) / len(contributions), 2)
    item.pop("count", None)


def _recompute_edge(edge: dict[str, Any], contributions: dict[str, float]) -> None:
    _recompute(edge, contributions, "weight", "evidence_count")


def add_causal_edge(
    graph: dict[str, Any],
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float,
    episode_id: str,
) -> dict[str, Any] | None:
    """Add an edge to the causal graph.

    Returns the edge when this episode contributes new or changed evidence, or
    None when the episode's contribution is unchanged (idempotent no-op).

    Each episode contributes at most one value per edge, stored in the
    ``contributions`` map (episode_id -> weight). The edge ``weight`` is the mean
    of that map, so reprocessing a byte-stable episode is a no-op and removing an
    episode (see :func:`remove_episode_contributions`) recomputes the mean
    exactly. This replaced the earlier running-average form, which could not be
    un-merged when an episode was edited to drop a chain or deleted outright
    (#3039); the ``episodes`` guard alone froze the stale edge in place.
    """
    for existing in graph["edges"]:
        if existing["source"] == source_id and existing["target"] == target_id:
            contributions = _legacy_backfill_contributions(existing, "weight", "evidence_count")
            if contributions.get(episode_id) == weight:
                # Same episode, same value: reprocess is a no-op.
                return None
            contributions[episode_id] = weight
            _recompute_edge(existing, contributions)
            edge_result: dict[str, Any] = existing
            return edge_result

    edge = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "weight": round(weight, 2),
        "evidence_count": 1,
        "episodes": [episode_id],
        "contributions": {episode_id: weight},
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
            contributions = _legacy_backfill_contributions(existing, "success_rate", "occurrences")
            if contributions.get(episode_id) == success_rate:
                # Same episode, same value: reprocess is a no-op.
                return None
            contributions[episode_id] = success_rate
            _recompute_pattern(existing, contributions)
            pattern_result: dict[str, Any] = existing
            return pattern_result

    pattern = {
        "name": name,
        "description": description,
        "trigger": trigger,
        "action": action,
        "success_rate": round(success_rate, 2),
        "occurrences": 1,
        "episodes": [episode_id],
        "contributions": {episode_id: success_rate},
        "created": datetime.now(UTC).isoformat(),
    }
    graph["patterns"].append(pattern)
    return pattern


def _recompute_pattern(
    pattern: dict[str, Any], contributions: dict[str, float],
) -> None:
    """Write the derived fields of a pattern from its per-episode contributions.

    ``success_rate`` is the mean over contributing episodes, so a 1.0, 1.0, 0.0
    sequence averages to 0.67 (occurrence-weighted), matching the pre-#3039
    intent while remaining exactly reversible when an episode is removed.
    """
    _recompute(pattern, contributions, "success_rate", "occurrences")


def remove_episode_contributions(
    graph: dict[str, Any], episode_id: str,
) -> dict[str, int]:
    """Remove every contribution attributable to ``episode_id`` from the graph.

    This is the missing inverse of the additive merge (#3039). Editing an
    episode to drop a chain, or deleting the episode file, must retract the
    nodes, edges, and patterns that episode alone supported and recompute the
    weight of any it shared. A node is dropped when no episode references it; an
    edge or pattern is dropped when its last contribution is removed, else its
    mean is recomputed from the survivors. Returns a count of what was removed.

    Legacy edges/patterns (no ``contributions`` map) are backfilled from their
    ``episodes`` list first, so removal is exact for them too from this point on.
    """
    removed = {"nodes": 0, "edges": 0, "patterns": 0}

    kept_nodes = []
    for node in graph.get("nodes", []):
        episodes = [ep for ep in node.get("episodes", []) if ep != episode_id]
        if not episodes:
            removed["nodes"] += 1
            continue
        node["episodes"] = episodes
        kept_nodes.append(node)
    graph["nodes"] = kept_nodes

    kept_edges = []
    for edge in graph.get("edges", []):
        contributions = _legacy_backfill_contributions(edge, "weight", "evidence_count")
        if episode_id in contributions:
            del contributions[episode_id]
            if not contributions:
                removed["edges"] += 1
                continue
            _recompute_edge(edge, contributions)
        kept_edges.append(edge)
    graph["edges"] = kept_edges

    kept_patterns = []
    for pattern in graph.get("patterns", []):
        contributions = _legacy_backfill_contributions(pattern, "success_rate", "occurrences")
        if episode_id in contributions:
            del contributions[episode_id]
            if not contributions:
                removed["patterns"] += 1
                continue
            _recompute_pattern(pattern, contributions)
        kept_patterns.append(pattern)
    graph["patterns"] = kept_patterns

    return removed


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
        "--prune-episode-ids", type=str, default=None,
        help=(
            "Comma-separated episode ids whose contributions to remove from the "
            "graph (for episodes deleted from disk; #3039). Pruned before any "
            "staged episodes are processed."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Determine paths
    script_dir = Path(__file__).resolve().parent
    base_path = script_dir.parent.parent.parent.parent

    if args.episode_path:
        if ".." in args.episode_path.parts:
            msg = "Security: path must not contain traversal sequences."
            print(msg, file=sys.stderr)
            return 2
        episode_path = args.episode_path.resolve()
    else:
        episode_path = base_path / ".agents" / "memory" / "episodes"

    if args.graph_path:
        if ".." in args.graph_path.parts:
            msg = "Security: path must not contain traversal sequences."
            print(msg, file=sys.stderr)
            return 2
        graph_path = args.graph_path.resolve()
    else:
        graph_path = base_path / ".agents" / "memory" / "causality" / "causal-graph.json"

    print("Updating causal graph...", file=sys.stderr)

    if args.dry_run:
        print("[DRY RUN] No changes will be made", file=sys.stderr)

    # Get episode files
    episode_files = get_episode_files(episode_path, args.since)

    prune_ids = [
        pid.strip()
        for pid in (args.prune_episode_ids or "").split(",")
        if pid.strip()
    ]

    if not episode_files and not prune_ids:
        print("No episode files found to process.", file=sys.stderr)
        return 0

    print(f"Found {len(episode_files)} episode(s) to process", file=sys.stderr)

    # Load existing graph
    graph = load_causal_graph(graph_path)

    stats = {
        "episodes_processed": 0,
        "nodes_added": 0,
        "edges_added": 0,
        "patterns_added": 0,
        "episodes_pruned": 0,
        "nodes_removed": 0,
        "edges_removed": 0,
        "patterns_removed": 0,
    }

    # Prune contributions of episodes deleted from disk (#3039). A deleted
    # episode never appears in episode_files, so its nodes/edges/patterns would
    # otherwise remain forever; the caller passes the deleted ids explicitly.
    for pruned_id in prune_ids:
        if args.dry_run:
            print(f"  [DRY] Would prune episode: {pruned_id}", file=sys.stderr)
            continue
        removed = remove_episode_contributions(graph, pruned_id)
        stats["episodes_pruned"] += 1
        stats["nodes_removed"] += removed["nodes"]
        stats["edges_removed"] += removed["edges"]
        stats["patterns_removed"] += removed["patterns"]

    for file_path in episode_files:
        print(f"\nProcessing: {file_path.name}", file=sys.stderr)

        try:
            content = file_path.read_text(encoding="utf-8")
            episode = json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"WARNING: Failed to process episode file '{file_path}': {e}",
                file=sys.stderr,
            )
            continue

        episode_id = episode.get("id", file_path.stem)

        # Replace semantics (#3039): retract this episode's prior contributions
        # before re-adding from current content. An episode edited to drop a
        # chain, decision, or event must not leave the old edge/pattern frozen in
        # place (the pre-#3039 episodes-guard made the re-add a no-op and kept the
        # stale contribution). Removing first, then re-adding the current content,
        # makes the graph reflect exactly what the episode says now.
        if not args.dry_run:
            remove_episode_contributions(graph, episode_id)

        # Add decision nodes
        for decision in episode.get("decisions", []):
            node_label = f"{decision.get('type', 'unknown')}: {decision.get('chosen', '')}"
            if not args.dry_run:
                node = add_causal_node(graph, "decision", node_label, episode_id)
                if node:
                    stats["nodes_added"] += 1
            else:
                print(f"  [DRY] Would add node: {node_label}", file=sys.stderr)

        # Add event nodes
        for event in episode.get("events", []):
            node_label = f"{event.get('type', 'unknown')}: {event.get('content', '')}"
            if not args.dry_run:
                node = add_causal_node(
                    graph, event.get("type", "unknown"), node_label, episode_id,
                )
                if node:
                    stats["nodes_added"] += 1
            else:
                print(f"  [DRY] Would add node: {node_label}", file=sys.stderr)

        # Add outcome node
        outcome_label = f"Outcome: {episode.get('outcome', 'unknown')} - {episode.get('task', '')}"
        if not args.dry_run:
            outcome_node = add_causal_node(graph, "outcome", outcome_label, episode_id)
            if outcome_node:
                stats["nodes_added"] += 1

        # Build and add causal chains
        chains = build_causal_chains(episode)
        for chain in chains:
            if not args.dry_run:
                from_node = add_causal_node(
                    graph, chain["from_type"], chain["from_label"], episode_id,
                )
                to_node = add_causal_node(
                    graph, chain["to_type"], chain["to_label"], episode_id,
                )
                if from_node and to_node:
                    edge = add_causal_edge(
                        graph, from_node["id"], to_node["id"],
                        chain["edge_type"], chain["weight"], episode_id,
                    )
                    if edge:
                        stats["edges_added"] += 1
            else:
                print(
                    f"  [DRY] Would add edge: {chain['from_label']} "
                    f"--[{chain['edge_type']}]--> {chain['to_label']}",
                    file=sys.stderr,
                )

        # Extract and add patterns
        patterns = get_decision_patterns(episode)
        for pat in patterns:
            success_rate = 1.0 if pat["success"] else 0.0
            if not args.dry_run:
                p = add_pattern(
                    graph, pat["name"], pat["description"],
                    pat["trigger"], pat["action"], success_rate, episode_id,
                )
                if p:
                    stats["patterns_added"] += 1
            else:
                print(
                    f"  [DRY] Would add pattern: {pat['name']}",
                    file=sys.stderr,
                )

        stats["episodes_processed"] += 1

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
    if stats["episodes_pruned"]:
        print(f"  Episodes pruned:    {stats['episodes_pruned']}", file=sys.stderr)
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
