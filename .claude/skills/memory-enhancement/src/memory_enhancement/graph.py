"""Graph traversal for memory relationships.

Builds a directed graph from Memory link data and provides
BFS, DFS, cycle detection, and relationship scoring.
"""

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .models import Memory

_logger = logging.getLogger(__name__)


@dataclass
class TraversalNode:
    """A node visited during graph traversal."""

    memory_id: str
    depth: int
    link_type: str | None = None
    parent_id: str | None = None


@dataclass
class RelationshipScore:
    """Scored relationship between two memories."""

    target_id: str
    score: float
    link_type: str
    distance: int


LINK_WEIGHTS: dict[str, float] = {
    "implements": 1.0,
    "extends": 0.8,
    "blocks": 0.6,
    "supersedes": 0.5,
    "related": 0.3,
}

_DEFAULT_WEIGHT = 0.3


class MemoryGraph:
    """Directed graph over Memory nodes with typed edges.

    Edges are derived from Memory.links. Each edge stores the
    target memory ID and the LinkType value string.
    """

    def __init__(self, memories: dict[str, Memory]) -> None:
        """Build adjacency list from a dict of Memory objects.

        Args:
            memories: Mapping of memory ID to Memory instance.
        """
        self._memories = memories
        self._adjacency: dict[str, list[tuple[str, str]]] = {
            mid: [] for mid in memories
        }
        for mid, memory in memories.items():
            for link in memory.links:
                self._adjacency[mid].append(
                    (link.target_id, link.link_type.value)
                )

    @classmethod
    def from_directory(cls, memories_dir: Path) -> "MemoryGraph":
        """Load all memories from a directory and build a graph.

        Skips files that fail to parse, logging a warning for each.

        Args:
            memories_dir: Path to directory containing .md memory files.

        Returns:
            A MemoryGraph built from successfully parsed memories.
        """
        memories: dict[str, Memory] = {}
        for path in sorted(memories_dir.glob("*.md")):
            try:
                memory = Memory.from_file(path)
                memories[memory.id] = memory
            except (ValueError, KeyError, OSError, UnicodeDecodeError) as exc:
                _logger.warning(
                    "Failed to parse %s: %s: %s",
                    path,
                    type(exc).__name__,
                    exc,
                )
        return cls(memories)

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return len(self._adjacency)

    @property
    def edge_count(self) -> int:
        """Total number of directed edges."""
        return sum(len(neighbors) for neighbors in self._adjacency.values())

    def _validate_start(self, start_id: str) -> None:
        """Raise KeyError if start_id is not in the graph."""
        if start_id not in self._adjacency:
            raise KeyError(
                f"Memory '{start_id}' not found in graph. "
                f"Available: {sorted(self._adjacency.keys())}"
            )

    def bfs(
        self, start_id: str, max_depth: int | None = None
    ) -> list[TraversalNode]:
        """Breadth-first traversal from start_id.

        Args:
            start_id: Memory ID to start traversal from.
            max_depth: Maximum traversal depth. None means unlimited.

        Returns:
            List of TraversalNode in BFS visit order,
            including the start node at depth 0.

        Raises:
            KeyError: If start_id is not in the graph.
        """
        self._validate_start(start_id)

        result: list[TraversalNode] = []
        visited: set[str] = {start_id}
        queue: deque[TraversalNode] = deque()
        start_node = TraversalNode(memory_id=start_id, depth=0)
        queue.append(start_node)

        while queue:
            node = queue.popleft()
            result.append(node)

            if max_depth is not None and node.depth >= max_depth:
                continue

            for target_id, link_type in self._adjacency.get(node.memory_id, []):
                if target_id in visited:
                    continue
                if target_id not in self._adjacency:
                    continue
                visited.add(target_id)
                child = TraversalNode(
                    memory_id=target_id,
                    depth=node.depth + 1,
                    link_type=link_type,
                    parent_id=node.memory_id,
                )
                queue.append(child)

        return result

    def dfs(
        self, start_id: str, max_depth: int | None = None
    ) -> list[TraversalNode]:
        """Depth-first traversal from start_id (iterative).

        Args:
            start_id: Memory ID to start traversal from.
            max_depth: Maximum traversal depth. None means unlimited.

        Returns:
            List of TraversalNode in DFS visit order,
            including the start node at depth 0.

        Raises:
            KeyError: If start_id is not in the graph.
        """
        self._validate_start(start_id)

        result: list[TraversalNode] = []
        visited: set[str] = set()
        stack: list[TraversalNode] = [
            TraversalNode(memory_id=start_id, depth=0)
        ]

        while stack:
            node = stack.pop()
            if node.memory_id in visited:
                continue
            visited.add(node.memory_id)
            result.append(node)

            if max_depth is not None and node.depth >= max_depth:
                continue

            for target_id, link_type in reversed(
                self._adjacency.get(node.memory_id, [])
            ):
                if target_id in visited:
                    continue
                if target_id not in self._adjacency:
                    continue
                child = TraversalNode(
                    memory_id=target_id,
                    depth=node.depth + 1,
                    link_type=link_type,
                    parent_id=node.memory_id,
                )
                stack.append(child)

        return result

    def find_cycles(self) -> list[list[str]]:
        """Find all cycles in the graph using DFS coloring.

        Uses WHITE (unvisited), GRAY (in current path),
        BLACK (fully explored) coloring scheme.

        Returns:
            List of cycles. Each cycle is a list of memory IDs
            forming the cycle path.
        """
        white, gray, black = 0, 1, 2
        color: dict[str, int] = {mid: white for mid in self._adjacency}
        path: list[str] = []
        path_set: set[str] = set()
        cycles: list[list[str]] = []

        for node_id in self._adjacency:
            if color[node_id] == white:
                self._cycle_dfs(
                    node_id, color, path, path_set, cycles, white, gray, black
                )

        return cycles

    def _cycle_dfs(
        self,
        node_id: str,
        color: dict[str, int],
        path: list[str],
        path_set: set[str],
        cycles: list[list[str]],
        white: int,
        gray: int,
        black: int,
    ) -> None:
        """Recursive DFS helper for cycle detection.

        Args:
            node_id: Current node being explored.
            color: Node coloring state map.
            path: Current DFS path stack.
            path_set: Set view of path for O(1) lookup.
            cycles: Accumulator for discovered cycles.
            white: Unvisited color constant.
            gray: In-path color constant.
            black: Fully explored color constant.
        """
        color[node_id] = gray
        path.append(node_id)
        path_set.add(node_id)

        for target_id, _ in self._adjacency.get(node_id, []):
            if target_id not in self._adjacency:
                continue
            if color[target_id] == gray and target_id in path_set:
                cycle_start = path.index(target_id)
                cycle = path[cycle_start:] + [target_id]
                cycles.append(cycle)
            elif color[target_id] == white:
                self._cycle_dfs(
                    target_id, color, path, path_set, cycles,
                    white, gray, black,
                )

        path.pop()
        path_set.discard(node_id)
        color[node_id] = black

    def score_relationships(
        self, memory_id: str
    ) -> list[RelationshipScore]:
        """Score all reachable memories by relationship strength.

        Score formula: LINK_WEIGHTS[link_type] / (1 + distance).
        Closer and more strongly typed links score higher.

        Args:
            memory_id: Memory ID to score relationships from.

        Returns:
            List of RelationshipScore sorted by score descending.
            The start node is excluded.

        Raises:
            KeyError: If memory_id is not in the graph.
        """
        nodes = self.bfs(memory_id)
        scores: list[RelationshipScore] = []

        for node in nodes:
            if node.memory_id == memory_id:
                continue
            weight = LINK_WEIGHTS.get(node.link_type, _DEFAULT_WEIGHT)
            score = weight / (1 + node.depth)
            scores.append(
                RelationshipScore(
                    target_id=node.memory_id,
                    score=score,
                    link_type=node.link_type,
                    distance=node.depth,
                )
            )

        scores.sort(key=lambda s: s.score, reverse=True)
        return scores
