"""Graph traversal for memory relationships.

This module provides BFS and DFS traversal of memory links,
supporting all Serena link types (RELATED, SUPERSEDES, BLOCKS, etc.)
with cycle detection and configurable depth limits.
"""

import sys
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

from .models import Link, LinkType, Memory


class TraversalStrategy(Enum):
    """Graph traversal algorithms."""

    BFS = "bfs"  # Breadth-first search
    DFS = "dfs"  # Depth-first search


@dataclass
class TraversalNode:
    """Node in the traversal tree.

    Attributes:
        memory: The memory at this node
        depth: Distance from root (0 = root)
        parent: ID of parent node (None for root)
        link_type: Type of link from parent (None for root)
    """

    memory: Memory
    depth: int
    parent: Optional[str] = None
    link_type: Optional[LinkType] = None


@dataclass
class TraversalResult:
    """Result of a graph traversal.

    Attributes:
        root_id: ID of the root memory
        nodes: List of traversed nodes in visit order
        cycles: List of detected cycles (pairs of memory IDs)
        strategy: Traversal algorithm used
        max_depth: Maximum depth reached
    """

    root_id: str
    nodes: list[TraversalNode]
    cycles: list[tuple[str, str]]
    strategy: TraversalStrategy
    max_depth: int


class MemoryGraph:
    """Graph representation of memory relationships.

    Loads memories from a directory and provides traversal operations.
    """

    def __init__(self, memories_dir: Path):
        """Initialize graph from memory directory.

        Args:
            memories_dir: Path to directory containing memory files
        """
        self.memories_dir = memories_dir
        self._memory_cache: dict[str, Memory] = {}
        self._load_memories()

    @property
    def memories(self) -> dict[str, Memory]:
        """Public access to memory cache.

        Returns a shallow copy to prevent external modification of the internal cache.
        """
        return dict(self._memory_cache)

    def _load_memories(self):
        """Load all memories from directory into cache."""
        if not self.memories_dir.exists():
            raise FileNotFoundError(f"Memories directory not found: {self.memories_dir}")

        for memory_file in self.memories_dir.glob("*.md"):
            try:
                memory = Memory.from_serena_file(memory_file)
                self._memory_cache[memory.id] = memory
            except (OSError, UnicodeDecodeError, ValueError, KeyError, yaml.YAMLError) as e:
                # Skip invalid memory files but continue loading others
                print(f"Warning: Failed to load {memory_file}: {e}", file=sys.stderr)

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID.

        Args:
            memory_id: Memory identifier

        Returns:
            Memory instance or None if not found
        """
        return self._memory_cache.get(memory_id)

    def get_related_memories(
        self, memory_id: str, link_type: Optional[LinkType] = None
    ) -> list[Memory]:
        """Get memories directly linked from the given memory.

        Args:
            memory_id: Source memory ID
            link_type: Filter by link type (None = all types)

        Returns:
            List of related memories
        """
        memory = self.get_memory(memory_id)
        if not memory:
            return []

        # Filter links by type if specified
        links = memory.links
        if link_type:
            links = [link for link in links if link.link_type == link_type]

        # Resolve link targets
        related = []
        for link in links:
            target = self.get_memory(link.target_id)
            if target:
                related.append(target)

        return related

    def _enqueue_children(
        self,
        current: TraversalNode,
        visited: set[str],
        queue: deque,
        cycles: list[tuple[str, str]],
        link_types: Optional[list[LinkType]],
    ) -> None:
        """Enqueue unvisited children of the current node.

        Mutates *visited*, *queue*, and *cycles* in place.
        Records cycles when a link target has already been visited.
        Skips links whose type is not in *link_types* (when provided)
        and targets not present in the graph.
        """
        for link in current.memory.links:
            if link_types and link.link_type not in link_types:
                continue

            target = self.get_memory(link.target_id)
            if not target:
                continue

            if link.target_id in visited:
                cycles.append((current.memory.id, link.target_id))
                continue

            visited.add(link.target_id)
            queue.append(TraversalNode(
                memory=target,
                depth=current.depth + 1,
                parent=current.memory.id,
                link_type=link.link_type,
            ))

    def traverse(
        self,
        root_id: str,
        strategy: TraversalStrategy = TraversalStrategy.BFS,
        max_depth: Optional[int] = None,
        link_types: Optional[list[LinkType]] = None,
    ) -> TraversalResult:
        """Traverse the memory graph starting from a root node.

        Args:
            root_id: ID of the root memory
            strategy: Traversal algorithm (BFS or DFS)
            max_depth: Maximum depth to traverse (None = unlimited)
            link_types: Filter by link types (None = all types)

        Returns:
            TraversalResult with visited nodes and detected cycles

        Raises:
            ValueError: If root memory doesn't exist
        """
        root = self.get_memory(root_id)
        if not root:
            raise ValueError(f"Root memory not found: {root_id}")

        visited: set[str] = {root_id}
        nodes: list[TraversalNode] = []
        cycles: list[tuple[str, str]] = []
        queue: deque[TraversalNode] = deque([TraversalNode(memory=root, depth=0)])
        current_max_depth = 0
        pop = queue.popleft if strategy == TraversalStrategy.BFS else queue.pop

        while queue:
            current = pop()
            nodes.append(current)
            current_max_depth = max(current_max_depth, current.depth)

            if max_depth is not None and current.depth >= max_depth:
                continue

            self._enqueue_children(current, visited, queue, cycles, link_types)

        return TraversalResult(
            root_id=root_id,
            nodes=nodes,
            cycles=cycles,
            strategy=strategy,
            max_depth=current_max_depth,
        )

    def find_roots(self) -> list[str]:
        """Find all root memories (memories with no incoming links).

        Returns:
            List of memory IDs that are not referenced by any other memory
        """
        # Collect all target IDs
        referenced_ids: set[str] = set()
        for memory in self._memory_cache.values():
            for link in memory.links:
                referenced_ids.add(link.target_id)

        # Find memories not in referenced set
        roots = [
            memory_id
            for memory_id in self._memory_cache.keys()
            if memory_id not in referenced_ids
        ]

        return roots

    def get_adjacency_list(self) -> dict[str, list[tuple[str, LinkType]]]:
        """Build adjacency list representation of the graph.

        Returns:
            Dictionary mapping memory IDs to lists of (target_id, link_type) pairs
        """
        adjacency: dict[str, list[tuple[str, LinkType]]] = {}

        for memory_id, memory in self._memory_cache.items():
            adjacency[memory_id] = [
                (link.target_id, link.link_type) for link in memory.links
            ]

        return adjacency
