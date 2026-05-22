#!/usr/bin/env python3
"""Reflexion Memory module for episodic replay and causal reasoning.

Implements ADR-038 Reflexion Memory Schema with:
- Episodic memory storage and retrieval
- Causal graph management
- Pattern extraction from decision sequences

Tier Architecture:
- Tier 0: Working memory (context window, managed by Claude)
- Tier 1: Semantic memory (Serena + Forgetful, ADR-037)
- Tier 2: Episodic memory (this module)
- Tier 3: Causal memory (this module)

Exit codes (ADR-035):
    0 - Success
    1 - Logic error (validation failure)
    2 - Config error (schema/path not found)
    3 - External error (I/O failure)
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MODULE_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _MODULE_DIR.parent
_AGENTS_ROOT = _SKILL_ROOT.parent.parent.parent / ".agents"

EPISODES_PATH = _AGENTS_ROOT / "memory" / "episodes"
CAUSALITY_PATH = _AGENTS_ROOT / "memory" / "causality"
CAUSAL_GRAPH_FILE = CAUSALITY_PATH / "causal-graph.json"

SCHEMAS_PATH = _SKILL_ROOT / "resources" / "schemas"
EPISODE_SCHEMA_FILE = SCHEMAS_PATH / "episode.schema.json"
CAUSAL_GRAPH_SCHEMA_FILE = SCHEMAS_PATH / "causal-graph.schema.json"


# ---------------------------------------------------------------------------
# Private functions
# ---------------------------------------------------------------------------


def _validate_schema(
    data: dict[str, Any],
    schema_file: Path,
    data_type: str,
) -> None:
    """Validate data against a JSON Schema.

    Performs basic structural validation: required fields, types, enums, patterns.

    Args:
        data: The data dict to validate.
        schema_file: Path to the JSON Schema file.
        data_type: Human-readable name for error messages.

    Raises:
        FileNotFoundError: If schema file is missing.
        ValueError: If data does not conform to the schema.
    """
    if not schema_file.is_file():
        msg = (
            f"Required schema file not found: {schema_file}. "
            f"Cannot validate {data_type}. "
            f"Ensure schema files exist at {SCHEMAS_PATH}"
        )
        raise FileNotFoundError(msg)

    try:
        json_str = json.dumps(data, default=str)
    except (TypeError, ValueError) as exc:
        msg = f"Failed to serialize {data_type} to JSON: {exc}"
        raise ValueError(msg) from exc

    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Failed to read schema file '{schema_file}': {exc}"
        raise ValueError(msg) from exc

    # Basic structural validation
    parsed = json.loads(json_str)
    errors: list[str] = []

    required = schema.get("required", [])
    for field_name in required:
        if field_name not in parsed:
            errors.append(f"Missing required field: '{field_name}'")

    properties = schema.get("properties", {})
    for field_name, field_schema in properties.items():
        if field_name not in parsed:
            continue
        val = parsed[field_name]
        expected = field_schema.get("type")
        if expected == "string" and val is not None and not isinstance(val, str):
            errors.append(
                f"Field '{field_name}' should be string, got {type(val).__name__}"
            )
        elif expected == "array" and not isinstance(val, list):
            errors.append(
                f"Field '{field_name}' should be array, got {type(val).__name__}"
            )
        elif expected == "object" and not isinstance(val, dict):
            errors.append(
                f"Field '{field_name}' should be object, got {type(val).__name__}"
            )
        elif expected == "number" and not isinstance(val, (int, float)):
            errors.append(
                f"Field '{field_name}' should be number, got {type(val).__name__}"
            )

    if errors:
        msg = (
            f"Invalid {data_type} - JSON Schema validation failed: "
            + "; ".join(errors)
        )
        raise ValueError(msg)


def _get_causal_graph(allow_empty: bool = False) -> dict[str, Any]:
    """Load the causal graph from disk.

    Args:
        allow_empty: If True, returns empty graph on corruption instead of raising.

    Returns:
        Causal graph dict with version, updated, nodes, edges, patterns.

    Raises:
        ValueError: If graph is corrupted and allow_empty is False.
    """
    empty_graph: dict[str, Any] = {
        "version": "1.0",
        "updated": datetime.now(tz=UTC).isoformat(),
        "nodes": [],
        "edges": [],
        "patterns": [],
    }

    if not CAUSAL_GRAPH_FILE.is_file():
        return empty_graph

    try:
        content = CAUSAL_GRAPH_FILE.read_text(encoding="utf-8")
        if not content.strip():
            return empty_graph
        data: dict[str, Any] = json.loads(content)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        error_message = f"Causal graph corrupted at '{CAUSAL_GRAPH_FILE}': {exc}"
        if allow_empty:
            logger.warning(error_message)
            return empty_graph
        raise ValueError(error_message) from exc


def _save_causal_graph(
    graph: dict[str, Any],
    skip_validation: bool = False,
) -> None:
    """Save the causal graph to disk.

    Args:
        graph: The causal graph dict to save.
        skip_validation: Skip JSON Schema validation (for tests only).

    Raises:
        FileNotFoundError: If schema file missing.
        ValueError: If validation fails.
        OSError: If I/O fails.
    """
    graph["updated"] = datetime.now(tz=UTC).isoformat()

    if not skip_validation:
        _validate_schema(graph, CAUSAL_GRAPH_SCHEMA_FILE, "causal graph")

    CAUSALITY_PATH.mkdir(parents=True, exist_ok=True)

    try:
        json_str = json.dumps(graph, indent=2, default=str)
        CAUSAL_GRAPH_FILE.write_text(json_str, encoding="utf-8")
    except OSError as exc:
        msg = f"Failed to save causal graph to '{CAUSAL_GRAPH_FILE}': {exc}"
        raise OSError(msg) from exc


def _get_next_node_id(graph: dict[str, Any]) -> str:
    """Get the next available node ID."""
    nodes = graph.get("nodes") or []
    if not nodes:
        return "n001"

    ids: list[int] = []
    for node in nodes:
        node_id = node.get("id", "") if isinstance(node, dict) else ""
        match = re.match(r"^n(\d+)$", str(node_id))
        if match:
            ids.append(int(match.group(1)))

    if not ids:
        return "n001"

    return f"n{max(ids) + 1:03d}"


def _get_next_pattern_id(graph: dict[str, Any]) -> str:
    """Get the next available pattern ID."""
    patterns = graph.get("patterns") or []
    if not patterns:
        return "p001"

    ids: list[int] = []
    for pattern in patterns:
        pattern_id = pattern.get("id", "") if isinstance(pattern, dict) else ""
        match = re.match(r"^p(\d+)$", str(pattern_id))
        if match:
            ids.append(int(match.group(1)))

    if not ids:
        return "p001"

    return f"p{max(ids) + 1:03d}"


# ---------------------------------------------------------------------------
# Episode functions
# ---------------------------------------------------------------------------


def get_episode(session_id: str) -> dict[str, Any] | None:
    """Retrieve an episode by session ID.

    Args:
        session_id: The session identifier (e.g., "2026-01-01-session-126").

    Returns:
        Episode dict or None if not found.

    Raises:
        ValueError: If episode file is corrupted.
    """
    episode_file = (EPISODES_PATH / f"episode-{session_id}.json").resolve()
    if not episode_file.is_relative_to(EPISODES_PATH.resolve()):
        raise ValueError("Path traversal attempt detected in session_id")

    if not episode_file.is_file():
        return None

    try:
        content = episode_file.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(content)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Episode file corrupted at '{episode_file}': {exc}"
        raise ValueError(msg) from exc


def get_episodes(
    outcome: str | None = None,
    task: str | None = None,
    since: datetime | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve episodes matching criteria.

    Args:
        outcome: Filter by outcome: success, partial, failure.
        task: Filter by task name (substring match, case-insensitive).
        since: Filter episodes since this datetime.
        max_results: Maximum number of episodes to return (1-100).

    Returns:
        List of episode dicts sorted by timestamp descending.
    """
    if outcome is not None and outcome not in ("success", "partial", "failure"):
        msg = f"Invalid outcome: {outcome}. Must be success, partial, or failure."
        raise ValueError(msg)
    if max_results < 1 or max_results > 100:
        msg = "max_results must be between 1 and 100"
        raise ValueError(msg)

    episodes: list[dict[str, Any]] = []
    skipped_count = 0

    if not EPISODES_PATH.is_dir():
        return episodes

    try:
        files = sorted(EPISODES_PATH.glob("episode-*.json"))
    except PermissionError as exc:
        logger.error(
            "Permission denied reading episodes from '%s': %s",
            EPISODES_PATH,
            exc,
        )
        return episodes
    except OSError as exc:
        logger.error("Failed to enumerate episodes: %s", exc)
        return episodes

    for episode_file in files:
        try:
            content = episode_file.read_text(encoding="utf-8")
            episode = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipping corrupted episode file '%s': %s", episode_file, exc
            )
            skipped_count += 1
            continue

        # Apply filters
        if outcome and episode.get("outcome") != outcome:
            continue

        if task and task.lower() not in (episode.get("task") or "").lower():
            continue

        if since:
            try:
                ep_timestamp = episode.get("timestamp", "")
                episode_date = datetime.fromisoformat(ep_timestamp)
                if episode_date < since:
                    continue
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Episode '%s' has invalid timestamp '%s': %s",
                    episode_file.name,
                    episode.get("timestamp"),
                    exc,
                )
                skipped_count += 1
                continue

        episodes.append(episode)

        if len(episodes) >= max_results:
            break

    if skipped_count > 0:
        logger.warning(
            "Skipped %d corrupted or invalid episode file(s)", skipped_count
        )

    # Sort by timestamp descending
    episodes.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return episodes


def new_episode(
    session_id: str,
    task: str,
    outcome: str,
    decisions: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    lessons: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    skip_validation: bool = False,
) -> dict[str, Any]:
    """Create a new episode from structured data.

    Args:
        session_id: The source session identifier.
        task: High-level task description.
        outcome: Episode outcome: success, partial, failure.
        decisions: Array of decision objects.
        events: Array of event objects.
        lessons: Array of lesson strings.
        metrics: Metrics dict.
        skip_validation: Skip JSON Schema validation (for tests only).

    Returns:
        Episode dict.

    Raises:
        ValueError: If outcome is invalid or validation fails.
        OSError: If file write fails.
    """
    if outcome not in ("success", "partial", "failure"):
        msg = f"Invalid outcome: {outcome}. Must be success, partial, or failure."
        raise ValueError(msg)

    episode: dict[str, Any] = {
        "id": f"episode-{session_id}",
        "session": session_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "outcome": outcome,
        "task": task,
        "decisions": decisions or [],
        "events": events or [],
        "metrics": metrics or {},
        "lessons": lessons or [],
    }

    if not skip_validation:
        _validate_schema(episode, EPISODE_SCHEMA_FILE, "episode")

    EPISODES_PATH.mkdir(parents=True, exist_ok=True)

    episode_file = (EPISODES_PATH / f"episode-{session_id}.json").resolve()
    if not episode_file.is_relative_to(EPISODES_PATH.resolve()):
        raise ValueError("Path traversal attempt detected in session_id")
    try:
        json_str = json.dumps(episode, indent=2, default=str)
        episode_file.write_text(json_str, encoding="utf-8")
    except OSError as exc:
        msg = f"Failed to save episode to '{episode_file}': {exc}"
        raise OSError(msg) from exc

    return episode


def get_decision_sequence(episode_id: str) -> list[dict[str, Any]]:
    """Retrieve the decision sequence from an episode.

    Args:
        episode_id: The episode identifier (e.g., "episode-2026-01-01-126").

    Returns:
        List of decision dicts sorted by timestamp. Empty list if not found.
    """
    session_id = episode_id.removeprefix("episode-")
    episode = get_episode(session_id)

    if not episode:
        return []

    decisions = episode.get("decisions") or []
    return sorted(decisions, key=lambda d: d.get("timestamp", ""))


# ---------------------------------------------------------------------------
# Causal graph functions
# ---------------------------------------------------------------------------


def add_causal_node(
    node_type: str,
    label: str,
    episode_id: str | None = None,
) -> dict[str, Any]:
    """Add a node to the causal graph.

    Args:
        node_type: Node type: decision, event, outcome, pattern, error.
        label: Human-readable label.
        episode_id: Source episode ID.

    Returns:
        Node dict with id, type, label, episodes, frequency, success_rate.

    Raises:
        ValueError: If node_type is invalid.
    """
    valid_types = ("decision", "event", "outcome", "pattern", "error")
    if node_type not in valid_types:
        msg = f"Invalid node type: {node_type}. Must be one of {valid_types}."
        raise ValueError(msg)

    graph = _get_causal_graph()

    # Check if node already exists (by label)
    for existing in graph.get("nodes", []):
        if existing.get("label") == label:
            existing["frequency"] = int(existing.get("frequency", 0)) + 1
            if episode_id:
                episodes = existing.get("episodes") or []
                if episode_id not in episodes:
                    episodes.append(episode_id)
                    existing["episodes"] = episodes
            _save_causal_graph(graph)
            result: dict[str, Any] = existing
            return result

    # Create new node
    node_episodes: list[str] = []
    if episode_id:
        node_episodes = [episode_id]

    node: dict[str, Any] = {
        "id": _get_next_node_id(graph),
        "type": node_type,
        "label": label,
        "episodes": node_episodes,
        "frequency": 1,
        "success_rate": 1.0,
    }

    graph.setdefault("nodes", []).append(node)
    _save_causal_graph(graph)

    return node


def add_causal_edge(
    source_id: str,
    target_id: str,
    edge_type: str,
    weight: float = 0.5,
) -> dict[str, Any]:
    """Add an edge to the causal graph.

    Args:
        source_id: Source node ID.
        target_id: Target node ID.
        edge_type: Edge type: causes, enables, prevents, correlates.
        weight: Confidence weight (0-1).

    Returns:
        Edge dict with source, target, type, weight, evidence_count.

    Raises:
        ValueError: If edge_type is invalid or weight is out of range.
    """
    valid_types = ("causes", "enables", "prevents", "correlates")
    if edge_type not in valid_types:
        msg = f"Invalid edge type: {edge_type}. Must be one of {valid_types}."
        raise ValueError(msg)
    if not 0 <= weight <= 1:
        msg = f"Weight must be between 0 and 1, got {weight}."
        raise ValueError(msg)

    graph = _get_causal_graph()

    # Check if edge already exists
    for existing in graph.get("edges", []):
        if (
            existing.get("source") == source_id
            and existing.get("target") == target_id
            and existing.get("type") == edge_type
        ):
            evidence_count = int(existing.get("evidence_count", 0)) + 1
            existing["evidence_count"] = evidence_count
            old_weight = float(existing.get("weight", 0))
            existing["weight"] = (
                old_weight * (evidence_count - 1) + weight
            ) / evidence_count
            _save_causal_graph(graph)
            edge_result: dict[str, Any] = existing
            return edge_result

    # Create new edge
    edge: dict[str, Any] = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "weight": weight,
        "evidence_count": 1,
    }

    graph.setdefault("edges", []).append(edge)
    _save_causal_graph(graph)

    return edge


def get_causal_path(
    from_label: str,
    to_label: str,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Find causal path between two nodes using BFS.

    Args:
        from_label: Source node label (substring match).
        to_label: Target node label (substring match).
        max_depth: Maximum path depth to search (1-10).

    Returns:
        Dict with found (bool), path (list of nodes), depth (int), error (str).
    """
    if max_depth < 1 or max_depth > 10:
        msg = "max_depth must be between 1 and 10"
        raise ValueError(msg)

    graph = _get_causal_graph()
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Find source and target nodes (substring match)
    from_node = None
    to_node = None
    for node in nodes:
        node_label = node.get("label", "")
        if from_label in node_label and from_node is None:
            from_node = node
        if to_label in node_label and to_node is None:
            to_node = node

    if not from_node or not to_node:
        return {"found": False, "path": [], "error": "Node not found"}

    # BFS
    queue: deque[dict[str, Any]] = deque()
    queue.append({"node": from_node["id"], "path": [from_node["id"]]})
    visited: set[str] = {from_node["id"]}

    while queue:
        current = queue.popleft()

        if current["node"] == to_node["id"]:
            # Resolve node labels
            path_nodes = []
            for node_id in current["path"]:
                for node in nodes:
                    if node.get("id") == node_id:
                        path_nodes.append(node)
                        break
            return {
                "found": True,
                "path": path_nodes,
                "depth": len(current["path"]) - 1,
            }

        if len(current["path"]) >= max_depth:
            continue

        # Find outgoing edges
        for edge in edges:
            if edge.get("source") == current["node"]:
                target = edge["target"]
                if target not in visited:
                    visited.add(target)
                    queue.append({
                        "node": target,
                        "path": current["path"] + [target],
                    })

    return {
        "found": False,
        "path": [],
        "error": f"No path found within depth {max_depth}",
    }


# ---------------------------------------------------------------------------
# Pattern functions
# ---------------------------------------------------------------------------


def add_pattern(
    name: str,
    trigger: str,
    action: str,
    description: str = "",
    success_rate: float = 1.0,
) -> dict[str, Any]:
    """Add a pattern to the causal graph.

    Args:
        name: Pattern name.
        trigger: Condition that triggers this pattern.
        action: Recommended action.
        description: Pattern description.
        success_rate: Success rate (0-1).

    Returns:
        Pattern dict with id, name, description, trigger, action,
        success_rate, occurrences, last_used.
    """
    if not 0 <= success_rate <= 1:
        msg = f"success_rate must be between 0 and 1, got {success_rate}."
        raise ValueError(msg)

    graph = _get_causal_graph()

    # Check if pattern already exists
    for existing in graph.get("patterns", []):
        if existing.get("name") == name:
            occurrences = existing.get("occurrences", 0) + 1
            existing["occurrences"] = occurrences
            existing["last_used"] = datetime.now(tz=UTC).isoformat()
            old_rate = existing.get("success_rate", 0)
            existing["success_rate"] = (
                old_rate * (occurrences - 1) + success_rate
            ) / occurrences
            _save_causal_graph(graph)
            pattern_result: dict[str, Any] = existing
            return pattern_result

    # Create new pattern
    pattern: dict[str, Any] = {
        "id": _get_next_pattern_id(graph),
        "name": name,
        "description": description,
        "trigger": trigger,
        "action": action,
        "success_rate": success_rate,
        "occurrences": 1,
        "last_used": datetime.now(tz=UTC).isoformat(),
    }

    graph.setdefault("patterns", []).append(pattern)
    _save_causal_graph(graph)

    return pattern


def get_patterns(
    min_success_rate: float = 0,
    min_occurrences: int = 1,
) -> list[dict[str, Any]]:
    """Retrieve patterns matching criteria.

    Args:
        min_success_rate: Minimum success rate filter (0-1).
        min_occurrences: Minimum occurrences filter (1-1000).

    Returns:
        List of pattern dicts sorted by success_rate descending.
    """
    graph = _get_causal_graph()

    result = [
        p
        for p in graph.get("patterns", [])
        if p.get("success_rate", 0) >= min_success_rate
        and p.get("occurrences", 0) >= min_occurrences
    ]

    result.sort(key=lambda p: p.get("success_rate", 0), reverse=True)
    return result


def get_anti_patterns(max_success_rate: float = 0.3) -> list[dict[str, Any]]:
    """Retrieve anti-patterns (low success rate patterns).

    Args:
        max_success_rate: Maximum success rate to qualify as anti-pattern (0-1).

    Returns:
        List of anti-pattern dicts sorted by success_rate ascending.
        Only includes patterns with at least 2 occurrences.
    """
    graph = _get_causal_graph()

    result = [
        p
        for p in graph.get("patterns", [])
        if p.get("success_rate", 0) <= max_success_rate
        and p.get("occurrences", 0) >= 2
    ]

    result.sort(key=lambda p: p.get("success_rate", 0))
    return result


# ---------------------------------------------------------------------------
# Status functions
# ---------------------------------------------------------------------------


def get_reflexion_memory_status() -> dict[str, Any]:
    """Get the status of the reflexion memory system.

    Returns:
        Dict with Episodes, CausalGraph, and Configuration status.
    """
    graph = _get_causal_graph(allow_empty=True)

    episode_count = 0
    if EPISODES_PATH.is_dir():
        try:
            episode_count = len(list(EPISODES_PATH.glob("episode-*.json")))
        except OSError as exc:
            logger.warning("Failed to count episode files: %s", exc)

    return {
        "Episodes": {
            "Path": str(EPISODES_PATH),
            "Count": episode_count,
        },
        "CausalGraph": {
            "Path": str(CAUSAL_GRAPH_FILE),
            "Version": graph.get("version", ""),
            "Updated": graph.get("updated", ""),
            "Nodes": len(graph.get("nodes", [])),
            "Edges": len(graph.get("edges", [])),
            "Patterns": len(graph.get("patterns", [])),
        },
        "Configuration": {
            "EpisodesPath": str(EPISODES_PATH),
            "CausalityPath": str(CAUSALITY_PATH),
        },
    }
