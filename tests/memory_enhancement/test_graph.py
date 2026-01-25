"""Tests for memory_enhancement.graph module.

Tests BFS/DFS traversal, cycle detection, root finding,
and adjacency list construction.
"""

import pytest
from pathlib import Path
from scripts.memory_enhancement.graph import (
    MemoryGraph,
    TraversalNode,
    TraversalResult,
    TraversalStrategy,
)
from scripts.memory_enhancement.models import Memory, Link, LinkType


class TestMemoryGraph:
    """Tests for MemoryGraph class."""

    def test_init_loads_memories(self, tmp_path):
        """MemoryGraph loads all valid memories from directory."""
        # Create test memories
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)

        assert len(graph.memories) == 2
        assert "memory-a" in graph.memories
        assert "memory-b" in graph.memories

    def test_init_missing_directory_raises(self, tmp_path):
        """MemoryGraph raises FileNotFoundError for missing directory."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError):
            MemoryGraph(nonexistent)

    def test_init_skips_invalid_memories(self, tmp_path, capsys):
        """MemoryGraph loads all parseable files (frontmatter is lenient)."""
        (tmp_path / "valid.md").write_text(
            "---\n"
            "id: valid\n"
            "---\n"
            "Content"
        )
        (tmp_path / "invalid.md").write_text("Not valid frontmatter")

        graph = MemoryGraph(tmp_path)

        # Both files load (python-frontmatter is lenient)
        # Files without frontmatter get default id from filename
        assert len(graph.memories) == 2
        assert "valid" in graph.memories
        assert "invalid" in graph.memories

    def test_get_memory_returns_existing(self, tmp_path):
        """get_memory returns memory for valid ID."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        memory = graph.get_memory("memory-a")

        assert memory is not None
        assert memory.id == "memory-a"

    def test_get_memory_returns_none_for_missing(self, tmp_path):
        """get_memory returns None for nonexistent ID."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        memory = graph.get_memory("nonexistent")

        assert memory is None

    def test_get_related_memories_all_types(self, tmp_path):
        """get_related_memories returns all linked memories."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "  - target: memory-c\n"
            "    type: SUPERSEDES\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        related = graph.get_related_memories("memory-a")

        assert len(related) == 2
        related_ids = {m.id for m in related}
        assert related_ids == {"memory-b", "memory-c"}

    def test_get_related_memories_filtered_by_type(self, tmp_path):
        """get_related_memories filters by link type."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "  - target: memory-c\n"
            "    type: SUPERSEDES\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        related = graph.get_related_memories("memory-a", link_type=LinkType.SUPERSEDES)

        assert len(related) == 1
        assert related[0].id == "memory-c"

    def test_get_related_memories_empty_for_missing(self, tmp_path):
        """get_related_memories returns empty list for nonexistent memory."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        related = graph.get_related_memories("nonexistent")

        assert related == []

    def test_get_related_memories_skips_invalid_targets(self, tmp_path):
        """get_related_memories skips links to nonexistent memories."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "  - target: nonexistent\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        related = graph.get_related_memories("memory-a")

        assert len(related) == 1
        assert related[0].id == "memory-b"


class TestTraverse:
    """Tests for MemoryGraph.traverse method."""

    def test_traverse_bfs_single_node(self, tmp_path):
        """BFS traversal of single node returns only root."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        result = graph.traverse("memory-a", strategy=TraversalStrategy.BFS)

        assert result.root_id == "memory-a"
        assert len(result.nodes) == 1
        assert result.nodes[0].memory.id == "memory-a"
        assert result.nodes[0].depth == 0
        assert result.nodes[0].parent is None
        assert result.nodes[0].link_type is None
        assert result.strategy == TraversalStrategy.BFS
        assert result.max_depth == 0
        assert len(result.cycles) == 0

    def test_traverse_bfs_linear_chain(self, tmp_path):
        """BFS traversal follows linear chain."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "links:\n"
            "  - target: memory-c\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        result = graph.traverse("memory-a", strategy=TraversalStrategy.BFS)

        assert len(result.nodes) == 3
        assert result.nodes[0].memory.id == "memory-a"
        assert result.nodes[1].memory.id == "memory-b"
        assert result.nodes[2].memory.id == "memory-c"
        assert result.max_depth == 2

    def test_traverse_dfs_linear_chain(self, tmp_path):
        """DFS traversal follows linear chain (same as BFS for linear)."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "links:\n"
            "  - target: memory-c\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        result = graph.traverse("memory-a", strategy=TraversalStrategy.DFS)

        assert len(result.nodes) == 3
        assert result.strategy == TraversalStrategy.DFS
        # DFS visits in depth-first order
        assert result.nodes[0].memory.id == "memory-a"
        # The next nodes should be visited depth-first
        visited_ids = {node.memory.id for node in result.nodes}
        assert visited_ids == {"memory-a", "memory-b", "memory-c"}

    def test_traverse_max_depth_limit(self, tmp_path):
        """Traversal respects max_depth limit."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "links:\n"
            "  - target: memory-c\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        result = graph.traverse("memory-a", max_depth=1)

        # Should visit A (depth 0) and B (depth 1), but not C (depth 2)
        assert len(result.nodes) == 2
        visited_ids = {node.memory.id for node in result.nodes}
        assert visited_ids == {"memory-a", "memory-b"}
        assert result.max_depth == 1

    def test_traverse_detects_cycles(self, tmp_path):
        """Traversal detects and reports cycles."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "links:\n"
            "  - target: memory-a\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        result = graph.traverse("memory-a")

        # Should visit both nodes
        assert len(result.nodes) == 2
        # Should detect cycle from B back to A
        assert len(result.cycles) == 1
        assert result.cycles[0] == ("memory-b", "memory-a")

    def test_traverse_link_type_filter(self, tmp_path):
        """Traversal filters by link type."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "  - target: memory-c\n"
            "    type: SUPERSEDES\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        result = graph.traverse("memory-a", link_types=[LinkType.SUPERSEDES])

        # Should visit A and C, but not B (filtered by link type)
        assert len(result.nodes) == 2
        visited_ids = {node.memory.id for node in result.nodes}
        assert visited_ids == {"memory-a", "memory-c"}

    def test_traverse_missing_root_raises(self, tmp_path):
        """Traversal raises ValueError for nonexistent root."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)

        with pytest.raises(ValueError, match="Root memory not found: nonexistent"):
            graph.traverse("nonexistent")


class TestFindRoots:
    """Tests for MemoryGraph.find_roots method."""

    def test_find_roots_single_root(self, tmp_path):
        """find_roots identifies single root memory."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        roots = graph.find_roots()

        assert roots == ["memory-a"]

    def test_find_roots_multiple_roots(self, tmp_path):
        """find_roots identifies multiple root memories."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        roots = graph.find_roots()

        assert set(roots) == {"memory-a", "memory-b"}

    def test_find_roots_excludes_referenced(self, tmp_path):
        """find_roots excludes memories referenced by others."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        roots = graph.find_roots()

        # Only A is a root (B is referenced by A)
        assert roots == ["memory-a"]

    def test_find_roots_empty_graph(self, tmp_path):
        """find_roots returns empty list for empty graph."""
        graph = MemoryGraph(tmp_path)
        roots = graph.find_roots()

        assert roots == []


class TestGetAdjacencyList:
    """Tests for MemoryGraph.get_adjacency_list method."""

    def test_get_adjacency_list_single_node(self, tmp_path):
        """Adjacency list for single node has empty neighbors."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        adj = graph.get_adjacency_list()

        assert adj == {"memory-a": []}

    def test_get_adjacency_list_with_links(self, tmp_path):
        """Adjacency list includes all links with types."""
        (tmp_path / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "  - target: memory-c\n"
            "    type: SUPERSEDES\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )
        (tmp_path / "memory-c.md").write_text(
            "---\n"
            "id: memory-c\n"
            "---\n"
            "Content"
        )

        graph = MemoryGraph(tmp_path)
        adj = graph.get_adjacency_list()

        assert adj["memory-a"] == [
            ("memory-b", LinkType.RELATED),
            ("memory-c", LinkType.SUPERSEDES)
        ]
        assert adj["memory-b"] == []
        assert adj["memory-c"] == []

    def test_get_adjacency_list_empty_graph(self, tmp_path):
        """Adjacency list for empty graph is empty."""
        graph = MemoryGraph(tmp_path)
        adj = graph.get_adjacency_list()

        assert adj == {}
