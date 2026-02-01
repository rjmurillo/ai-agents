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
from scripts.memory_enhancement.models import Memory, Citation, Link, LinkType


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


@pytest.fixture
def memories_dir_simple(tmp_path):
    """Create a simple memory graph: A -> B -> C.

    Returns:
        Path to memories directory
    """
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Memory A (root)
    (memories_dir / "memory-a.md").write_text("""---
id: memory-a
subject: Memory A
links:
  - link_type: RELATED
    target_id: memory-b
---

# Memory A
Root memory.
""")

    # Memory B (middle)
    (memories_dir / "memory-b.md").write_text("""---
id: memory-b
subject: Memory B
links:
  - link_type: RELATED
    target_id: memory-c
---

# Memory B
Middle memory.
""")

    # Memory C (leaf)
    (memories_dir / "memory-c.md").write_text("""---
id: memory-c
subject: Memory C
---

# Memory C
Leaf memory.
""")

    return memories_dir


@pytest.fixture
def memories_dir_cycle(tmp_path):
    """Create a memory graph with a cycle: A -> B -> C -> A.

    Returns:
        Path to memories directory
    """
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Memory A
    (memories_dir / "memory-a.md").write_text("""---
id: memory-a
subject: Memory A
links:
  - link_type: RELATED
    target_id: memory-b
---

# Memory A
""")

    # Memory B
    (memories_dir / "memory-b.md").write_text("""---
id: memory-b
subject: Memory B
links:
  - link_type: RELATED
    target_id: memory-c
---

# Memory B
""")

    # Memory C (creates cycle back to A)
    (memories_dir / "memory-c.md").write_text("""---
id: memory-c
subject: Memory C
links:
  - link_type: RELATED
    target_id: memory-a
---

# Memory C
""")

    return memories_dir


@pytest.fixture
def memories_dir_multi_type(tmp_path):
    """Create a memory graph with multiple link types.

    Returns:
        Path to memories directory
    """
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Memory A with multiple link types
    (memories_dir / "memory-a.md").write_text("""---
id: memory-a
subject: Memory A
links:
  - link_type: RELATED
    target_id: memory-b
  - link_type: SUPERSEDES
    target_id: memory-c
  - link_type: IMPLEMENTS
    target_id: memory-d
---

# Memory A
""")

    # Create target memories
    for mem_id in ["memory-b", "memory-c", "memory-d"]:
        (memories_dir / f"{mem_id}.md").write_text(f"""---
id: {mem_id}
subject: {mem_id.title().replace('-', ' ')}
---

# {mem_id.title().replace('-', ' ')}
""")

    return memories_dir


@pytest.mark.unit
def test_memory_graph_init(memories_dir_simple):
    """Test MemoryGraph initialization."""
    graph = MemoryGraph(memories_dir_simple)

    assert len(graph.memories) == 3
    assert "memory-a" in graph.memories
    assert "memory-b" in graph.memories
    assert "memory-c" in graph.memories


@pytest.mark.unit
def test_memory_graph_init_nonexistent_dir(tmp_path):
    """Test MemoryGraph initialization with nonexistent directory."""
    with pytest.raises(FileNotFoundError):
        MemoryGraph(tmp_path / "nonexistent")


@pytest.mark.unit
def test_memory_graph_get_memory(memories_dir_simple):
    """Test retrieving a memory by ID."""
    graph = MemoryGraph(memories_dir_simple)

    memory_a = graph.get_memory("memory-a")
    assert memory_a is not None
    assert memory_a.id == "memory-a"
    assert memory_a.subject == "Memory A"

    nonexistent = graph.get_memory("nonexistent")
    assert nonexistent is None


@pytest.mark.unit
def test_get_related_memories(memories_dir_simple):
    """Test getting related memories."""
    graph = MemoryGraph(memories_dir_simple)

    # Memory A should have 1 related memory (B)
    related = graph.get_related_memories("memory-a")
    assert len(related) == 1
    assert related[0].id == "memory-b"

    # Memory C should have no related memories (leaf)
    related = graph.get_related_memories("memory-c")
    assert len(related) == 0


@pytest.mark.unit
def test_get_related_memories_by_type(memories_dir_multi_type):
    """Test filtering related memories by link type."""
    graph = MemoryGraph(memories_dir_multi_type)

    # Get only RELATED links
    related = graph.get_related_memories("memory-a", link_type=LinkType.RELATED)
    assert len(related) == 1
    assert related[0].id == "memory-b"

    # Get only SUPERSEDES links
    related = graph.get_related_memories("memory-a", link_type=LinkType.SUPERSEDES)
    assert len(related) == 1
    assert related[0].id == "memory-c"

    # Get only IMPLEMENTS links
    related = graph.get_related_memories("memory-a", link_type=LinkType.IMPLEMENTS)
    assert len(related) == 1
    assert related[0].id == "memory-d"


@pytest.mark.unit
def test_traverse_bfs_simple(memories_dir_simple):
    """Test BFS traversal of simple graph."""
    graph = MemoryGraph(memories_dir_simple)

    result = graph.traverse("memory-a", strategy=TraversalStrategy.BFS)

    assert result.root_id == "memory-a"
    assert result.strategy == TraversalStrategy.BFS
    assert len(result.nodes) == 3
    assert result.max_depth == 2
    assert len(result.cycles) == 0

    # BFS should visit in level order: A, B, C
    assert result.nodes[0].memory.id == "memory-a"
    assert result.nodes[0].depth == 0
    assert result.nodes[1].memory.id == "memory-b"
    assert result.nodes[1].depth == 1
    assert result.nodes[2].memory.id == "memory-c"
    assert result.nodes[2].depth == 2


@pytest.mark.unit
def test_traverse_dfs_simple(memories_dir_simple):
    """Test DFS traversal of simple graph."""
    graph = MemoryGraph(memories_dir_simple)

    result = graph.traverse("memory-a", strategy=TraversalStrategy.DFS)

    assert result.root_id == "memory-a"
    assert result.strategy == TraversalStrategy.DFS
    assert len(result.nodes) == 3
    assert result.max_depth == 2
    assert len(result.cycles) == 0

    # DFS visits: A, B, C (depth-first path)
    assert result.nodes[0].memory.id == "memory-a"
    assert result.nodes[1].memory.id == "memory-b"
    assert result.nodes[2].memory.id == "memory-c"


@pytest.mark.unit
def test_traverse_max_depth(memories_dir_simple):
    """Test traversal with max depth limit."""
    graph = MemoryGraph(memories_dir_simple)

    # Limit to depth 1 (should visit A and B only)
    result = graph.traverse("memory-a", max_depth=1)

    assert len(result.nodes) == 2
    assert result.nodes[0].memory.id == "memory-a"
    assert result.nodes[1].memory.id == "memory-b"
    assert result.max_depth == 1


@pytest.mark.unit
def test_traverse_cycle_detection(memories_dir_cycle):
    """Test cycle detection during traversal."""
    graph = MemoryGraph(memories_dir_cycle)

    result = graph.traverse("memory-a")

    assert len(result.nodes) == 3
    assert len(result.cycles) == 1

    # Should detect cycle: C -> A
    cycle_from, cycle_to = result.cycles[0]
    assert cycle_from == "memory-c"
    assert cycle_to == "memory-a"


@pytest.mark.unit
def test_traverse_nonexistent_root(memories_dir_simple):
    """Test traversal with nonexistent root memory."""
    graph = MemoryGraph(memories_dir_simple)

    with pytest.raises(ValueError, match="Root memory not found"):
        graph.traverse("nonexistent-root")


@pytest.mark.unit
def test_traverse_filter_link_types(memories_dir_multi_type):
    """Test traversal filtering by link types."""
    graph = MemoryGraph(memories_dir_multi_type)

    # Only traverse RELATED links
    result = graph.traverse("memory-a", link_types=[LinkType.RELATED])
    assert len(result.nodes) == 2  # A and B only
    assert result.nodes[1].memory.id == "memory-b"

    # Only traverse SUPERSEDES links
    result = graph.traverse("memory-a", link_types=[LinkType.SUPERSEDES])
    assert len(result.nodes) == 2  # A and C only
    assert result.nodes[1].memory.id == "memory-c"

    # Traverse multiple link types
    result = graph.traverse(
        "memory-a", link_types=[LinkType.RELATED, LinkType.IMPLEMENTS]
    )
    assert len(result.nodes) == 3  # A, B, and D
    visited_ids = {node.memory.id for node in result.nodes}
    assert "memory-b" in visited_ids
    assert "memory-d" in visited_ids
    assert "memory-c" not in visited_ids


@pytest.mark.unit
def test_find_roots_simple(memories_dir_simple):
    """Test finding root memories (no incoming links)."""
    graph = MemoryGraph(memories_dir_simple)

    roots = graph.find_roots()

    # Only memory-a should be a root
    assert len(roots) == 1
    assert "memory-a" in roots


@pytest.mark.unit
def test_find_roots_cycle(memories_dir_cycle):
    """Test finding roots in graph with cycle."""
    graph = MemoryGraph(memories_dir_cycle)

    roots = graph.find_roots()

    # In a cycle, no memory is a root
    assert len(roots) == 0


@pytest.mark.unit
def test_find_roots_multiple(tmp_path):
    """Test finding multiple root memories."""
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Create two independent trees
    (memories_dir / "root-a.md").write_text("""---
id: root-a
subject: Root A
links:
  - link_type: RELATED
    target_id: child-a
---

# Root A
""")

    (memories_dir / "child-a.md").write_text("""---
id: child-a
subject: Child A
---

# Child A
""")

    (memories_dir / "root-b.md").write_text("""---
id: root-b
subject: Root B
---

# Root B
""")

    graph = MemoryGraph(memories_dir)
    roots = graph.find_roots()

    assert len(roots) == 2
    assert "root-a" in roots
    assert "root-b" in roots


@pytest.mark.unit
def test_get_adjacency_list(memories_dir_simple):
    """Test building adjacency list representation."""
    graph = MemoryGraph(memories_dir_simple)

    adjacency = graph.get_adjacency_list()

    assert len(adjacency) == 3

    # Memory A links to B
    assert len(adjacency["memory-a"]) == 1
    assert adjacency["memory-a"][0][0] == "memory-b"
    assert adjacency["memory-a"][0][1] == LinkType.RELATED

    # Memory B links to C
    assert len(adjacency["memory-b"]) == 1
    assert adjacency["memory-b"][0][0] == "memory-c"

    # Memory C has no outgoing links
    assert len(adjacency["memory-c"]) == 0


@pytest.mark.unit
def test_traversal_node_dataclass(tmp_path):
    """Test TraversalNode dataclass."""
    test_path = tmp_path / "test-memory.md"
    memory = Memory(
        id="test-memory",
        subject="Test",
        path=test_path,
        content="# Test content",
        tags=[],
        citations=[],
        links=[],
        confidence=1.0,
    )

    node = TraversalNode(
        memory=memory, depth=2, parent="parent-id", link_type=LinkType.RELATED
    )

    assert node.memory.id == "test-memory"
    assert node.depth == 2
    assert node.parent == "parent-id"
    assert node.link_type == LinkType.RELATED


@pytest.mark.unit
def test_traversal_result_dataclass():
    """Test TraversalResult dataclass."""
    result = TraversalResult(
        root_id="root",
        nodes=[],
        cycles=[("a", "b")],
        strategy=TraversalStrategy.BFS,
        max_depth=3,
    )

    assert result.root_id == "root"
    assert len(result.nodes) == 0
    assert len(result.cycles) == 1
    assert result.cycles[0] == ("a", "b")
    assert result.strategy == TraversalStrategy.BFS
    assert result.max_depth == 3


@pytest.mark.unit
def test_invalid_memory_file_skipped(tmp_path):
    """Test that invalid memory files are skipped during loading."""
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Valid memory
    (memories_dir / "valid.md").write_text("""---
id: valid
subject: Valid Memory
---

# Valid
""")

    # Invalid memory (corrupted YAML)
    (memories_dir / "invalid.md").write_text("""---
id: invalid
subject: [unclosed list
---

# Invalid
""")

    # Should load only the valid memory
    graph = MemoryGraph(memories_dir)
    assert len(graph.memories) == 1
    assert "valid" in graph.memories
    assert "invalid" not in graph.memories


@pytest.mark.unit
def test_traverse_with_invalid_target(tmp_path):
    """Test traversal with link to nonexistent memory."""
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Memory with link to nonexistent target
    (memories_dir / "memory-a.md").write_text("""---
id: memory-a
subject: Memory A
links:
  - link_type: RELATED
    target_id: nonexistent
  - link_type: RELATED
    target_id: memory-b
---

# Memory A
""")

    (memories_dir / "memory-b.md").write_text("""---
id: memory-b
subject: Memory B
---

# Memory B
""")

    graph = MemoryGraph(memories_dir)
    result = graph.traverse("memory-a")

    # Should skip invalid link and continue with valid one
    assert len(result.nodes) == 2
    assert result.nodes[0].memory.id == "memory-a"
    assert result.nodes[1].memory.id == "memory-b"
