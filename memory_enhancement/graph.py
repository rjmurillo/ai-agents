"""Graph traversal operations for memory relationships."""

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import GraphEdge, GraphResult, Link, LinkType, Memory


def traverse_graph(
    root_id: str,
    memories_dir: Path,
    max_depth: int = 3,
    link_types: Optional[list[LinkType]] = None,
) -> GraphResult:
    """
    BFS traversal of memory graph with typed link filtering.

    Args:
        root_id: Starting memory ID
        memories_dir: Path to .serena/memories/
        max_depth: Maximum traversal depth
        link_types: Filter to specific link types (None = all types)

    Returns:
        GraphResult with nodes, edges, and traversal metadata

    Uses only file I/O on Serena memories - no external graph DB.
    """
    memories_dir = Path(memories_dir)
    visited = set()
    queue = deque([(root_id, 0)])
    graph = {}
    edges = []
    max_depth_reached = 0

    while queue:
        current_id, depth = queue.popleft()

        if current_id in visited or depth > max_depth:
            continue

        visited.add(current_id)
        max_depth_reached = max(max_depth_reached, depth)

        # Try both ID-based and filename-based lookup
        memory_path = memories_dir / f"{current_id}.md"
        if not memory_path.exists():
            # Fallback: search by frontmatter id
            memory_path = _find_memory_by_id(current_id, memories_dir)
            if memory_path is None:
                continue

        memory = Memory.from_serena_file(memory_path)

        # Filter links by type if specified
        filtered_links = memory.links
        if link_types is not None:
            filtered_links = [l for l in memory.links if l.link_type in link_types]

        graph[current_id] = filtered_links

        for link in filtered_links:
            edges.append(
                GraphEdge(
                    source_id=current_id,
                    target_id=link.target_id,
                    link_type=link.link_type,
                )
            )
            if link.target_id not in visited:
                queue.append((link.target_id, depth + 1))

    return GraphResult(
        nodes=graph,
        edges=edges,
        visited_count=len(visited),
        max_depth_reached=max_depth_reached,
    )


def _find_memory_by_id(memory_id: str, memories_dir: Path) -> Optional[Path]:
    """
    Find memory file by frontmatter id field.

    Args:
        memory_id: The memory ID to search for
        memories_dir: Directory containing memory files

    Returns:
        Path to the memory file, or None if not found
    """
    for path in memories_dir.glob("*.md"):
        try:
            memory = Memory.from_serena_file(path)
            if memory.id == memory_id:
                return path
        except Exception:
            continue
    return None


def find_superseded_chain(memory_id: str, memories_dir: Path) -> list[str]:
    """
    Find the deprecation chain via 'supersedes' links.

    Args:
        memory_id: Starting memory ID
        memories_dir: Path to .serena/memories/

    Returns:
        List of superseded memory IDs in chain order
    """
    result = traverse_graph(
        memory_id, memories_dir, max_depth=10, link_types=[LinkType.SUPERSEDES]
    )
    return [e.target_id for e in result.edges]


def find_blocking_dependencies(memory_id: str, memories_dir: Path) -> list[str]:
    """
    Find memories that must be resolved before this one.

    Args:
        memory_id: Target memory ID
        memories_dir: Path to .serena/memories/

    Returns:
        List of blocking memory IDs
    """
    result = traverse_graph(
        memory_id, memories_dir, max_depth=5, link_types=[LinkType.BLOCKS]
    )
    return [e.target_id for e in result.edges]


def find_related_memories(memory_id: str, memories_dir: Path) -> list[str]:
    """
    Find all memories that link TO this memory (reverse lookup).

    Args:
        memory_id: Target memory ID
        memories_dir: Path to .serena/memories/

    Returns:
        List of memory IDs that link to the target
    """
    memories_dir = Path(memories_dir)
    related = []

    for path in memories_dir.glob("*.md"):
        if path.stem == memory_id:
            continue

        try:
            memory = Memory.from_serena_file(path)
            # Check if any link targets this memory
            for link in memory.links:
                if link.target_id == memory_id:
                    related.append(memory.id)
                    break
        except Exception:
            continue

    return related


def find_root_memories(memories_dir: Path) -> list[str]:
    """
    Find memories with no incoming links (graph roots).

    Args:
        memories_dir: Path to .serena/memories/

    Returns:
        List of root memory IDs
    """
    memories_dir = Path(memories_dir)

    # Collect all outgoing links
    all_targets = set()
    all_memories = set()

    for path in memories_dir.glob("*.md"):
        try:
            memory = Memory.from_serena_file(path)
            all_memories.add(memory.id)
            for link in memory.links:
                all_targets.add(link.target_id)
        except Exception:
            continue

    # Roots are memories not targeted by any link
    return list(all_memories - all_targets)


