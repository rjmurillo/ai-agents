"""Memory graph traversal and analysis.

Builds an in-memory graph from MemoryWithCitations objects and provides
traversal, cycle detection, and orphan identification.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from .models import LinkType, MemoryWithCitations
from .serena_integration import load_memories


def build_memory_graph(memories_dir: Path) -> dict[str, MemoryWithCitations]:
    """Build a graph mapping memory_id to MemoryWithCitations.

    Args:
        memories_dir: Root directory containing memory .md files.

    Returns:
        Dictionary keyed by memory_id.
    """
    memories = load_memories(memories_dir)
    return {m.memory_id: m for m in memories}


def traverse(
    graph: dict[str, MemoryWithCitations],
    start_id: str,
    max_depth: int = 3,
) -> list[tuple[str, int, str]]:
    """Breadth-first traversal from a starting memory.

    Args:
        graph: Memory graph built by build_memory_graph.
        start_id: Memory ID to start traversal from.
        max_depth: Maximum link depth to traverse.

    Returns:
        List of (memory_id, depth, link_type) tuples visited.
    """
    if start_id not in graph:
        raise KeyError(f"start_id '{start_id}' not found in graph")

    visited: set[str] = {start_id}
    queue: deque[tuple[str, int]] = deque([(start_id, 0)])
    results: list[tuple[str, int, str]] = []

    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        _enqueue_neighbors(graph, current_id, depth, visited, queue, results)

    return results


def find_related(
    graph: dict[str, MemoryWithCitations],
    memory_id: str,
    link_types: list[LinkType] | None = None,
) -> list[str]:
    """Find directly related memory IDs, optionally filtered by link type.

    Args:
        graph: Memory graph.
        memory_id: Source memory ID.
        link_types: If provided, only return links of these types.

    Returns:
        List of related memory IDs.
    """
    memory = graph.get(memory_id)
    if memory is None:
        return []

    related: list[str] = []
    for link in memory.links:
        if link_types is not None and link.link_type not in link_types:
            continue
        if link.target_id in graph:
            related.append(link.target_id)
    return related


def detect_cycles(graph: dict[str, MemoryWithCitations]) -> list[list[str]]:
    """Detect cycles in the memory graph using DFS.

    Args:
        graph: Memory graph.

    Returns:
        List of cycles, each represented as a list of memory IDs.
    """
    visited: set[str] = set()
    cycles: list[list[str]] = []

    for memory_id in graph:
        if memory_id not in visited:
            _dfs_detect_cycles(graph, memory_id, visited, [], set(), cycles)

    return cycles


def find_orphans(graph: dict[str, MemoryWithCitations]) -> list[str]:
    """Find memory IDs with no incoming links from other memories.

    Args:
        graph: Memory graph.

    Returns:
        List of orphan memory IDs sorted alphabetically.
    """
    targets_with_incoming = _collect_incoming_targets(graph)
    orphans = [mid for mid in graph if mid not in targets_with_incoming]
    return sorted(orphans)


def _enqueue_neighbors(
    graph: dict[str, MemoryWithCitations],
    current_id: str,
    depth: int,
    visited: set[str],
    queue: deque[tuple[str, int]],
    results: list[tuple[str, int, str]],
) -> None:
    # Separated from traverse to keep BFS loop body under complexity limit.
    memory = graph.get(current_id)
    if memory is None:
        return

    for link in memory.links:
        if link.target_id in visited:
            continue
        if link.target_id not in graph:
            continue
        visited.add(link.target_id)
        results.append((link.target_id, depth + 1, link.link_type.value))
        queue.append((link.target_id, depth + 1))


def _dfs_detect_cycles(
    graph: dict[str, MemoryWithCitations],
    node: str,
    visited: set[str],
    path: list[str],
    on_stack: set[str],
    cycles: list[list[str]],
) -> None:
    """Recursive DFS for cycle detection."""
    visited.add(node)
    on_stack.add(node)
    path.append(node)

    memory = graph.get(node)
    if memory is not None:
        for link in memory.links:
            target = link.target_id
            if target not in graph:
                continue
            if target in on_stack:
                cycle_start = path.index(target)
                cycles.append(path[cycle_start:] + [target])
            elif target not in visited:
                _dfs_detect_cycles(graph, target, visited, path, on_stack, cycles)

    path.pop()
    on_stack.discard(node)


def _collect_incoming_targets(graph: dict[str, MemoryWithCitations]) -> set[str]:
    """Collect all memory IDs that are targets of at least one link."""
    targets: set[str] = set()
    for memory in graph.values():
        for link in memory.links:
            if link.target_id in graph:
                targets.add(link.target_id)
    return targets
