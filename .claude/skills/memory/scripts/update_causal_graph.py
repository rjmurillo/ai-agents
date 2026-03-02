#!/usr/bin/env python3
"""Update the causal graph from episode data.

Processes episode files and updates the causal graph with:
  - Decision nodes and their relationships
  - Event nodes and causal chains
  - Outcome tracking and success rates
  - Pattern extraction from repeated sequences

Exit codes (ADR-035):
    0 - Success: Graph updated successfully
    1 - Error: Episode path not found or update failed
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_EPISODE_PATH = (
    _SCRIPT_DIR / ".." / ".." / ".." / ".." / ".agents" / "memory" / "episodes"
)
_DEFAULT_CAUSALITY_PATH = (
    _SCRIPT_DIR / ".." / ".." / ".." / ".." / ".agents" / "memory" / "causality"
)
_CAUSAL_GRAPH_FILE = _DEFAULT_CAUSALITY_PATH / "causal-graph.json"


# ---------------------------------------------------------------------------
# Graph I/O
# ---------------------------------------------------------------------------

def _empty_graph() -> dict:
    return {
        "version": "1.0",
        "updated": datetime.now(timezone.utc).isoformat(),
        "nodes": [],
        "edges": [],
        "patterns": [],
    }


def load_graph() -> dict:
    """Load causal graph from disk, returning empty graph if missing."""
    if not _CAUSAL_GRAPH_FILE.exists():
        return _empty_graph()
    try:
        text = _CAUSAL_GRAPH_FILE.read_text(encoding="utf-8")
        if not text.strip():
            return _empty_graph()
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARNING: Causal graph corrupted ({exc}), starting fresh.", file=sys.stderr)
        return _empty_graph()


def save_graph(graph: dict) -> None:
    """Persist causal graph to disk."""
    graph["updated"] = datetime.now(timezone.utc).isoformat()
    _CAUSAL_GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CAUSAL_GRAPH_FILE.write_text(json.dumps(graph, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Node / Edge / Pattern helpers
# ---------------------------------------------------------------------------

def _next_node_id(graph: dict) -> str:
    """Return next available node ID like n001, n002, ..."""
    ids = []
    for node in graph["nodes"]:
        m = re.match(r"^n(\d+)$", node.get("id", ""))
        if m:
            ids.append(int(m.group(1)))
    return f"n{(max(ids) + 1) if ids else 1:03d}"


def _next_pattern_id(graph: dict) -> str:
    """Return next available pattern ID like p001, p002, ..."""
    ids = []
    for p in graph["patterns"]:
        m = re.match(r"^p(\d+)$", p.get("id", ""))
        if m:
            ids.append(int(m.group(1)))
    return f"p{(max(ids) + 1) if ids else 1:03d}"


def add_causal_node(graph: dict, node_type: str, label: str, episode_id: str) -> dict:
    """Add or update a node in the graph. Returns the node dict."""
    for node in graph["nodes"]:
        if node.get("label") == label:
            node["frequency"] = node.get("frequency", 0) + 1
            if episode_id and episode_id not in node.get("episodes", []):
                node.setdefault("episodes", []).append(episode_id)
            return node

    node = {
        "id": _next_node_id(graph),
        "type": node_type,
        "label": label,
        "episodes": [episode_id] if episode_id else [],
        "frequency": 1,
        "success_rate": 1.0,
    }
    graph["nodes"].append(node)
    return node


def add_causal_edge(
    graph: dict,
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float,
) -> dict:
    """Add or update an edge in the graph. Returns the edge dict."""
    for edge in graph["edges"]:
        if (
            edge.get("source") == source_id
            and edge.get("target") == target_id
            and edge.get("type") == edge_type
        ):
            count = edge.get("evidence_count", 1) + 1
            edge["evidence_count"] = count
            edge["weight"] = (edge.get("weight", 0.5) * (count - 1) + weight) / count
            return edge

    edge = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "weight": weight,
        "evidence_count": 1,
    }
    graph["edges"].append(edge)
    return edge


def add_pattern(
    graph: dict,
    name: str,
    description: str,
    trigger: str,
    action: str,
    success_rate: float,
) -> dict:
    """Add or update a pattern in the graph. Returns the pattern dict."""
    for pattern in graph["patterns"]:
        if pattern.get("name") == name:
            count = pattern.get("occurrences", 1) + 1
            pattern["occurrences"] = count
            pattern["last_used"] = datetime.now(timezone.utc).isoformat()
            pattern["success_rate"] = (
                pattern.get("success_rate", 1.0) * (count - 1) + success_rate
            ) / count
            return pattern

    pattern = {
        "id": _next_pattern_id(graph),
        "name": name,
        "description": description,
        "trigger": trigger,
        "action": action,
        "success_rate": success_rate,
        "occurrences": 1,
        "last_used": datetime.now(timezone.utc).isoformat(),
    }
    graph["patterns"].append(pattern)
    return pattern


# ---------------------------------------------------------------------------
# Episode processing helpers
# ---------------------------------------------------------------------------

def get_decision_patterns(episode: dict) -> list:
    """Extract decision patterns from an episode."""
    patterns = []
    for decision in episode.get("decisions", []):
        outcome = decision.get("outcome", "")
        trigger = decision.get("context") or f"When {decision.get('type', 'unknown')} decision needed"
        action = decision.get("chosen", "")
        success = outcome == "success"
        dtype = decision.get("type", "implementation")

        patterns.append(
            {
                "name": f"{dtype} pattern" if success else f"{dtype} anti-pattern",
                "description": f"Pattern from {episode.get('id', '')}",
                "trigger": trigger,
                "action": action if success else f"AVOID: {action}",
                "success": success,
            }
        )
    return patterns


def build_causal_chains(episode: dict) -> list:
    """Build causal chains from episode events."""
    chains = []
    events = episode.get("events", [])

    # Error -> recovery chains
    for i, event in enumerate(events):
        if event.get("type") != "error":
            continue
        following = events[i + 1 : i + 6]
        for follow in following:
            if follow.get("type") == "milestone" and re.search(
                r"fix|recover|resolve", follow.get("content", ""), re.IGNORECASE
            ):
                chains.append(
                    {
                        "from_type": "error",
                        "from_label": event.get("content", ""),
                        "to_type": "outcome",
                        "to_label": follow.get("content", ""),
                        "edge_type": "causes",
                        "weight": 0.8,
                    }
                )
                break  # one recovery per error

    # Decision -> event chains
    for decision in episode.get("decisions", []):
        chosen_words = decision.get("chosen", "").split()[:3]
        if not chosen_words:
            continue
        keyword_pattern = "|".join(re.escape(w) for w in chosen_words)
        for event in events:
            if re.search(keyword_pattern, event.get("content", ""), re.IGNORECASE):
                chains.append(
                    {
                        "from_type": "decision",
                        "from_label": decision.get("chosen", ""),
                        "to_type": event.get("type", "event"),
                        "to_label": event.get("content", ""),
                        "edge_type": "causes",
                        "weight": 0.6,
                    }
                )

    return chains


# ---------------------------------------------------------------------------
# Episode file loading
# ---------------------------------------------------------------------------

def get_episode_files(path: Path, since: datetime | None) -> list:
    """Return episode JSON files to process."""
    if path.is_file():
        return [path]

    if not path.exists():
        return []

    try:
        files = list(path.glob("episode-*.json"))
    except OSError as exc:
        print(f"WARNING: Failed to read episode files from '{path}': {exc}", file=sys.stderr)
        return []

    if since is None:
        return files

    filtered = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ep_date = datetime.fromisoformat(data.get("timestamp", ""))
            if ep_date >= since:
                filtered.append(f)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"WARNING: Skipping malformed episode file {f}: {exc}", file=sys.stderr)
    return filtered


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Update the causal graph from episode data."
    )
    parser.add_argument(
        "--episode-path",
        default=str(_DEFAULT_EPISODE_PATH),
        help="Path to a specific episode file or a directory of episodes.",
    )
    parser.add_argument(
        "--since",
        help="Only process episodes since this date (ISO 8601, e.g. 2026-01-01).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes.",
    )
    args = parser.parse_args()

    since_dt: datetime | None = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
        except ValueError as exc:
            print(f"ERROR: Invalid --since date '{args.since}': {exc}", file=sys.stderr)
            sys.exit(1)

    print("Updating causal graph...")
    if args.dry_run:
        print("[DRY RUN] No changes will be made")

    episode_files = get_episode_files(Path(args.episode_path), since_dt)
    if not episode_files:
        print("No episode files found to process.")
        sys.exit(0)

    print(f"Found {len(episode_files)} episode(s) to process")

    stats = {
        "episodes_processed": 0,
        "nodes_added": 0,
        "edges_added": 0,
        "patterns_added": 0,
    }

    for ep_file in episode_files:
        print(f"\nProcessing: {ep_file.name}")
        try:
            episode = json.loads(ep_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: Failed to process '{ep_file}': {exc}", file=sys.stderr)
            continue

        graph = load_graph()
        episode_id = episode.get("id", ep_file.stem)

        # Add decision nodes
        for decision in episode.get("decisions", []):
            label = f"{decision.get('type', 'unknown')}: {decision.get('chosen', '')}"
            if not args.dry_run:
                try:
                    add_causal_node(graph, "decision", label, episode_id)
                    save_graph(graph)
                    stats["nodes_added"] += 1
                except OSError as exc:
                    print(f"WARNING: Failed to add decision node '{label}': {exc}", file=sys.stderr)
            else:
                print(f"  [DRY] Would add node: {label}")

        # Add event nodes
        for event in episode.get("events", []):
            label = f"{event.get('type', 'event')}: {event.get('content', '')}"
            if not args.dry_run:
                try:
                    add_causal_node(graph, event.get("type", "event"), label, episode_id)
                    save_graph(graph)
                    stats["nodes_added"] += 1
                except OSError as exc:
                    print(f"WARNING: Failed to add event node '{label}': {exc}", file=sys.stderr)
            else:
                print(f"  [DRY] Would add node: {label}")

        # Add outcome node
        outcome_label = f"Outcome: {episode.get('outcome', 'unknown')} - {episode.get('task', '')}"
        if not args.dry_run:
            try:
                add_causal_node(graph, "outcome", outcome_label, episode_id)
                save_graph(graph)
                stats["nodes_added"] += 1
            except OSError as exc:
                print(f"WARNING: Failed to add outcome node: {exc}", file=sys.stderr)

        # Build and add causal chains
        chains = build_causal_chains(episode)
        for chain in chains:
            if not args.dry_run:
                try:
                    graph = load_graph()
                    from_node = add_causal_node(graph, chain["from_type"], chain["from_label"], episode_id)
                    to_node = add_causal_node(graph, chain["to_type"], chain["to_label"], episode_id)
                    add_causal_edge(
                        graph,
                        from_node["id"],
                        to_node["id"],
                        chain["edge_type"],
                        chain["weight"],
                    )
                    save_graph(graph)
                    stats["edges_added"] += 1
                except OSError as exc:
                    print(
                        f"WARNING: Failed to add chain '{chain['from_label']}' -> "
                        f"'{chain['to_label']}': {exc}",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"  [DRY] Would add edge: {chain['from_label']} "
                    f"--[{chain['edge_type']}]--> {chain['to_label']}"
                )

        # Extract and add patterns
        patterns = get_decision_patterns(episode)
        for p in patterns:
            if not args.dry_run:
                try:
                    graph = load_graph()
                    add_pattern(
                        graph,
                        p["name"],
                        p["description"],
                        p["trigger"],
                        p["action"],
                        1.0 if p["success"] else 0.0,
                    )
                    save_graph(graph)
                    stats["patterns_added"] += 1
                except OSError as exc:
                    print(f"WARNING: Failed to add pattern '{p['name']}': {exc}", file=sys.stderr)
            else:
                print(f"  [DRY] Would add pattern: {p['name']}")

        stats["episodes_processed"] += 1

    print()
    print("=" * 50)
    print("Causal Graph Update Complete")
    print("=" * 50)
    print(f"  Episodes processed: {stats['episodes_processed']}")
    print(f"  Nodes added:        {stats['nodes_added']}")
    print(f"  Edges added:        {stats['edges_added']}")
    print(f"  Patterns added:     {stats['patterns_added']}")

    if args.dry_run:
        print("\n[DRY RUN] No actual changes were made")


if __name__ == "__main__":
    main()
