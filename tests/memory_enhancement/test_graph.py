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
from scripts.memory_enhancement.models import LinkType, Memory


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
