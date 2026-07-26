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

GRAPH_VERSION = "1.0"


def _empty_graph() -> dict[str, Any]:
    """The graph this module writes when there is nothing on disk to read.

    ``version`` and ``updated`` are part of the file's schema, so a fresh write
    has to carry them. Returning a bare ``nodes``/``edges``/``patterns`` dict
    here is how the committed graph came to hold a ``version`` and an
    ``updated`` stamp that no live writer had touched since 2026-02-10: the
    fields survived only because every write so far happened to load a file
    that already had them (issue #3351).
    """
    return {
        "version": GRAPH_VERSION,
        "updated": datetime.now(UTC).isoformat(),
        "nodes": [],
        "edges": [],
        "patterns": [],
    }


def load_causal_graph(graph_path: Path) -> dict[str, Any]:
    """Load causal graph from JSON file or return empty graph.

    Raises:
        ValueError: When the file cannot be decoded as UTF-8, contains invalid
            JSON, or contains valid JSON that is not a dict. This signals a
            corrupted file that must not be silently replaced, allowing the
            caller (e.g., a git hook) to restore the original.
    """
    if not graph_path.is_file():
        return _empty_graph()
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        msg = f"causal graph file is not valid UTF-8: {graph_path}"
        raise ValueError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"causal graph file contains invalid JSON: {graph_path}"
        raise ValueError(msg) from exc
    except OSError as exc:
        msg = f"causal graph file exists but could not be read: {graph_path}"
        raise ValueError(msg) from exc
    if not isinstance(data, dict):
        msg = f"causal graph file is valid JSON but not an object: {graph_path}"
        raise ValueError(msg)
    return data


def save_causal_graph(graph_path: Path, graph: dict[str, Any]) -> None:
    """Save causal graph to JSON file.

    Supplies ``version`` when the loaded graph lacks one and restamps
    ``updated`` when the content actually changed (issue #3351).

    The stamp is conditional on purpose. This runs from the
    ``update-causal-graph`` job on every commit, so an unconditional stamp
    would rewrite the file on every commit even when no episode added
    anything, dirtying the tree and manufacturing merge conflicts in a file
    that is already the repo's worst conflict source. When the rendered
    content matches what is on disk, the write is skipped entirely and the
    file stays byte-identical.

    The comparison read is an optimization, not a load, so every way it can
    fail means "I could not prove the bytes already match" and the write
    proceeds. ``UnicodeDecodeError`` is listed alongside ``OSError`` because it
    is a ``ValueError`` subclass rather than an ``OSError`` one, so an
    undecodable file on disk would otherwise abort the save instead of
    replacing it. ``load_causal_graph`` treats the same bytes as fatal, and the
    asymmetry is deliberate: the load asks what the current state is, the save
    only asks whether its own output is already there.
    """
    graph.setdefault("version", GRAPH_VERSION)
    graph.setdefault("updated", datetime.now(UTC).isoformat())
    unchanged = json.dumps(graph, indent=2) + "\n"
    try:
        if graph_path.read_text(encoding="utf-8") == unchanged:
            return
    except (OSError, UnicodeDecodeError):
        pass
    graph["updated"] = datetime.now(UTC).isoformat()
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(graph, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_node_id(node_type: str, label: str) -> str:
    """Generate a deterministic node ID from type and label."""
    content = f"{node_type}:{label}"
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def generate_pattern_id(name: str) -> str:
    """Generate a deterministic pattern ID from its name.

    ``name`` is already the identity ``add_pattern`` dedupes on, so deriving the
    id from it keeps the two in agreement. Content-derived rather than
    sequential (``p001``, ``p002``) because this file is merged by the
    content-aware driver in ``scripts/validation/merge_causal_graph.py``: two
    branches that each allocate the next number both produce ``p005`` for
    different patterns, and no merge can tell them apart. Distinct names can
    collide in principle: this is a 48-bit prefix whose birthday bound reaches
    even odds near 2**24 names. The graph holds tens, so the risk is negligible
    at its expected scale. Identical names always produce the same id. Refs #3353.
    """
    return hashlib.sha256(f"pattern:{name}".encode()).hexdigest()[:12]


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
            # Patterns written before #3353 carry no id. Derive it now so a
            # graph that predates this fix converges as its patterns are
            # touched, rather than only on records created from here on.
            existing.setdefault("id", generate_pattern_id(name))
            contributions = _legacy_backfill_contributions(existing, "success_rate", "occurrences")
            if contributions.get(episode_id) == success_rate:
                # Same episode, same value: reprocess is a no-op.
                return None
            contributions[episode_id] = success_rate
            _recompute_pattern(existing, contributions)
            pattern_result: dict[str, Any] = existing
            return pattern_result

    pattern = {
        "id": generate_pattern_id(name),
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
    weight of any it shared. A node is dropped only when removing this episode
    empties its provenance; a node this episode never referenced is left
    untouched. An edge or pattern is dropped when its last contribution is
    removed, else its mean is recomputed from the survivors. Returns a count of
    what was removed.

    Legacy edges/patterns (no ``contributions`` map) are backfilled from their
    ``episodes`` list first, so removal is exact for them too from this point on.
    """
    removed = {"nodes": 0, "edges": 0, "patterns": 0}

    kept_nodes = []
    for node in graph.get("nodes", []):
        if episode_id in node.get("episodes", []):
            remaining = [ep for ep in node["episodes"] if ep != episode_id]
            if not remaining:
                removed["nodes"] += 1
                continue
            node["episodes"] = remaining
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


def _episode_membership(
    graph: dict[str, Any], episode_id: str,
) -> dict[str, set[Any]]:
    """Return the nodes/edges/patterns ``episode_id`` currently contributes to.

    Membership is read from each item's ``episodes`` provenance (kept in sync by
    ``_recompute``). Used by the reconcile path to find contributions the episode
    dropped between reprocesses (#3039).
    """
    return {
        "nodes": {
            n["id"] for n in graph.get("nodes", [])
            if episode_id in n.get("episodes", [])
        },
        "edges": {
            (e["source"], e["target"]) for e in graph.get("edges", [])
            if episode_id in e.get("episodes", [])
        },
        "patterns": {
            p["name"] for p in graph.get("patterns", [])
            if episode_id in p.get("episodes", [])
        },
    }


def _retract_stale(
    graph: dict[str, Any],
    episode_id: str,
    old: dict[str, set[Any]],
    touched: dict[str, set[Any]],
) -> dict[str, int]:
    """Remove ``episode_id`` from items it supported before but not this pass.

    ``old`` is the pre-add membership; ``touched`` is what the current content
    re-added. The difference is the episode's dropped contributions, retracted
    the same way :func:`remove_episode_contributions` retracts a whole episode
    (drop the item on its last supporter, else recompute the mean). Items the
    episode still supports are left untouched, so their ``created`` timestamps
    and the byte-idempotency of an unchanged reprocess are preserved.
    """
    removed = {"nodes": 0, "edges": 0, "patterns": 0}

    stale_nodes = old["nodes"] - touched["nodes"]
    if stale_nodes:
        kept = []
        for node in graph.get("nodes", []):
            if node["id"] in stale_nodes:
                episodes = [ep for ep in node.get("episodes", []) if ep != episode_id]
                if not episodes:
                    removed["nodes"] += 1
                    continue
                node["episodes"] = episodes
            kept.append(node)
        graph["nodes"] = kept

    stale_edges = old["edges"] - touched["edges"]
    if stale_edges:
        kept = []
        for edge in graph.get("edges", []):
            if (edge["source"], edge["target"]) in stale_edges:
                contributions = _legacy_backfill_contributions(
                    edge, "weight", "evidence_count",
                )
                if episode_id in contributions:
                    del contributions[episode_id]
                    if not contributions:
                        removed["edges"] += 1
                        continue
                    _recompute_edge(edge, contributions)
            kept.append(edge)
        graph["edges"] = kept

    stale_patterns = old["patterns"] - touched["patterns"]
    if stale_patterns:
        kept = []
        for pattern in graph.get("patterns", []):
            if pattern["name"] in stale_patterns:
                contributions = _legacy_backfill_contributions(
                    pattern, "success_rate", "occurrences",
                )
                if episode_id in contributions:
                    del contributions[episode_id]
                    if not contributions:
                        removed["patterns"] += 1
                        continue
                    _recompute_pattern(pattern, contributions)
            kept.append(pattern)
        graph["patterns"] = kept

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
        "--reset-graph", action="store_true",
        help=(
            "Discard the existing graph and rebuild from the episodes on disk. "
            "The repair path for a corrupted graph file: the graph is derived "
            "data, so a full run reconstructs it (issue #3370)."
        ),
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

    if not episode_files and not prune_ids and not args.reset_graph:
        print("No episode files found to process.", file=sys.stderr)
        return 0

    print(f"Found {len(episode_files)} episode(s) to process", file=sys.stderr)

    # Load existing graph. A corrupt file is preserved rather than replaced,
    # so the failure has to carry its own repair instruction: without one the
    # hook warns on every commit forever with nothing the user can act on.
    if args.reset_graph:
        print("Discarding the existing graph and rebuilding from episodes.", file=sys.stderr)
        graph = _empty_graph()
    else:
        try:
            graph = load_causal_graph(graph_path)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            print(
                "The graph is derived from the episodes on disk, so it can be "
                "rebuilt. Repair with:\n"
                "  python3 .claude/skills/memory/scripts/update_causal_graph.py "
                "--reset-graph",
                file=sys.stderr,
            )
            return 2

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

        # Reconcile semantics (#3039). Snapshot which nodes/edges/patterns this
        # episode currently supports, re-add from current content (adding is a
        # no-op when unchanged, so a byte-stable reprocess leaves the graph and
        # its `created` timestamps untouched, preserving #3034 idempotency), then
        # retract only the items the episode used to support but no longer does.
        # An episode edited to drop a chain thus loses exactly that chain; an
        # unchanged episode changes nothing.
        #
        # Handle id renames: if the JSON `id` field differs from the filename
        # stem, the graph may still have contributions under the stem. Merge
        # that membership into `old` so those entries are retracted (#3039 fix).
        old = _episode_membership(graph, episode_id)
        stem_id = file_path.stem
        if stem_id != episode_id:
            stem_old = _episode_membership(graph, stem_id)
            old = {
                "nodes": old["nodes"] | stem_old["nodes"],
                "edges": old["edges"] | stem_old["edges"],
                "patterns": old["patterns"] | stem_old["patterns"],
            }
            # Retract contributions under the old (stem) id immediately since
            # they will be re-added under the new id below.
            if not args.dry_run:
                removed = remove_episode_contributions(graph, stem_id)
                stats["nodes_removed"] += removed["nodes"]
                stats["edges_removed"] += removed["edges"]
                stats["patterns_removed"] += removed["patterns"]
        touched_nodes: set[str] = set()
        touched_edges: set[tuple[str, str]] = set()
        touched_patterns: set[str] = set()

        # Add decision nodes
        for decision in episode.get("decisions", []):
            node_label = f"{decision.get('type', 'unknown')}: {decision.get('chosen', '')}"
            node_id = generate_node_id("decision", node_label)
            touched_nodes.add(node_id)
            if not args.dry_run:
                node = add_causal_node(graph, "decision", node_label, episode_id)
                if node:
                    stats["nodes_added"] += 1
            else:
                print(f"  [DRY] Would add node: {node_label}", file=sys.stderr)

        # Add event nodes
        for event in episode.get("events", []):
            node_type = event.get("type", "unknown")
            node_label = f"{node_type}: {event.get('content', '')}"
            node_id = generate_node_id(node_type, node_label)
            touched_nodes.add(node_id)
            if not args.dry_run:
                node = add_causal_node(graph, node_type, node_label, episode_id)
                if node:
                    stats["nodes_added"] += 1
            else:
                print(f"  [DRY] Would add node: {node_label}", file=sys.stderr)

        # Add outcome node
        outcome_label = f"Outcome: {episode.get('outcome', 'unknown')} - {episode.get('task', '')}"
        outcome_id = generate_node_id("outcome", outcome_label)
        touched_nodes.add(outcome_id)
        if not args.dry_run:
            outcome_node = add_causal_node(graph, "outcome", outcome_label, episode_id)
            if outcome_node:
                stats["nodes_added"] += 1

        # Build and add causal chains
        chains = build_causal_chains(episode)
        for chain in chains:
            from_id = generate_node_id(chain["from_type"], chain["from_label"])
            to_id = generate_node_id(chain["to_type"], chain["to_label"])
            touched_nodes.add(from_id)
            touched_nodes.add(to_id)
            touched_edges.add((from_id, to_id))
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
            touched_patterns.add(pat["name"])
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

        # Retract contributions this episode no longer makes (edit-shrink).
        touched: dict[str, set[Any]] = {
            "nodes": touched_nodes,
            "edges": touched_edges,
            "patterns": touched_patterns,
        }
        if args.dry_run:
            # Preview removals: compute what would be retracted without mutating.
            stale_nodes = old["nodes"] - touched["nodes"]
            stale_edges = old["edges"] - touched["edges"]
            stale_patterns = old["patterns"] - touched["patterns"]
            for nid in stale_nodes:
                print(f"  [DRY] Would retract node: {nid}", file=sys.stderr)
            for src, tgt in stale_edges:
                print(f"  [DRY] Would retract edge: {src} -> {tgt}", file=sys.stderr)
            for pname in stale_patterns:
                print(f"  [DRY] Would retract pattern: {pname}", file=sys.stderr)
        else:
            removed = _retract_stale(graph, episode_id, old, touched)
            stats["nodes_removed"] += removed["nodes"]
            stats["edges_removed"] += removed["edges"]
            stats["patterns_removed"] += removed["patterns"]

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
