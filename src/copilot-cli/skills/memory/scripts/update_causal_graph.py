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


def add_causal_edge(
    graph: dict[str, Any],
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float,
) -> dict[str, Any] | None:
    """Add an edge to the causal graph. Returns the edge or None if duplicate."""
    # Check for existing edge
    for existing in graph["edges"]:
        if existing["source"] == source_id and existing["target"] == target_id:
            # Update weight (running average)
            existing["weight"] = round(
                (existing["weight"] + weight) / 2, 2,
            )
            existing["count"] = existing.get("count", 1) + 1
            edge_result: dict[str, Any] = existing
            return edge_result

    edge = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "weight": weight,
        "count": 1,
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
) -> dict[str, Any] | None:
    """Add a pattern to the causal graph."""
    # Check for existing pattern with same name
    for existing in graph["patterns"]:
        if existing["name"] == name:
            # Update success rate (running average)
            existing["success_rate"] = round(
                (existing["success_rate"] + success_rate) / 2, 2,
            )
            existing["occurrences"] = existing.get("occurrences", 1) + 1
            pattern_result: dict[str, Any] = existing
            return pattern_result

    pattern = {
        "name": name,
        "description": description,
        "trigger": trigger,
        "action": action,
        "success_rate": success_rate,
        "occurrences": 1,
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


def get_decision_patterns(episode: dict) -> list[dict]:
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


def build_causal_chains(episode: dict) -> list[dict]:
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

    if not episode_files:
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
    }

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
                        chain["edge_type"], chain["weight"],
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
                    pat["trigger"], pat["action"], success_rate,
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

    if args.dry_run:
        print("\n[DRY RUN] No actual changes were made", file=sys.stderr)

    # Output stats as JSON to stdout
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
