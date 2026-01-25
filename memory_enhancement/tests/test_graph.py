"""Unit tests for graph traversal functionality."""

import tempfile
from pathlib import Path

import pytest

from memory_enhancement.graph import (
    find_blocking_dependencies,
    find_related_memories,
    find_root_memories,
    find_superseded_chain,
    traverse_graph,
)
from memory_enhancement.models import LinkType


@pytest.fixture
def temp_memories_dir():
    """Create a temporary directory with test memory files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memories_dir = Path(tmpdir)

        # Create test memories with YAML frontmatter
        (memories_dir / "mem-root.md").write_text(
            """---
id: mem-root
subject: Root memory
links:
  - related: mem-child1
  - related: mem-child2
---

Root memory content.
"""
        )

        (memories_dir / "mem-child1.md").write_text(
            """---
id: mem-child1
subject: Child 1
links:
  - related: mem-grandchild
---

Child 1 content.
"""
        )

        (memories_dir / "mem-child2.md").write_text(
            """---
id: mem-child2
subject: Child 2
links:
  - supersedes: mem-old-child2
---

Child 2 content.
"""
        )

        (memories_dir / "mem-grandchild.md").write_text(
            """---
id: mem-grandchild
subject: Grandchild
---

Grandchild content (leaf node).
"""
        )

        (memories_dir / "mem-old-child2.md").write_text(
            """---
id: mem-old-child2
subject: Old Child 2 (deprecated)
---

Old content.
"""
        )

        (memories_dir / "mem-blocked.md").write_text(
            """---
id: mem-blocked
subject: Blocked memory
links:
  - blocks: mem-dependency
---

This is blocked by dependencies.
"""
        )

        (memories_dir / "mem-dependency.md").write_text(
            """---
id: mem-dependency
subject: Dependency
---

Dependency content.
"""
        )

        yield memories_dir


def test_traverse_graph_basic(temp_memories_dir):
    """Test basic graph traversal."""
    result = traverse_graph("mem-root", temp_memories_dir, max_depth=2)

    assert result.visited_count > 0
    assert "mem-root" in result.nodes
    assert result.max_depth_reached <= 2


def test_traverse_graph_depth_limit(temp_memories_dir):
    """Test that max_depth is respected."""
    result = traverse_graph("mem-root", temp_memories_dir, max_depth=1)

    # Should visit root and direct children only
    assert "mem-root" in result.nodes
    assert result.max_depth_reached <= 1


def test_traverse_graph_link_type_filter(temp_memories_dir):
    """Test filtering by link type."""
    result = traverse_graph(
        "mem-child2", temp_memories_dir, link_types=[LinkType.SUPERSEDES]
    )

    # Should only follow SUPERSEDES links
    supersedes_edges = [e for e in result.edges if e.link_type == LinkType.SUPERSEDES]
    assert len(supersedes_edges) > 0


def test_find_superseded_chain(temp_memories_dir):
    """Test finding superseded memory chain."""
    chain = find_superseded_chain("mem-child2", temp_memories_dir)

    assert "mem-old-child2" in chain


def test_find_blocking_dependencies(temp_memories_dir):
    """Test finding blocking dependencies."""
    blocking = find_blocking_dependencies("mem-blocked", temp_memories_dir)

    assert "mem-dependency" in blocking


def test_find_related_memories(temp_memories_dir):
    """Test finding memories that link to target."""
    related = find_related_memories("mem-child1", temp_memories_dir)

    # mem-root links to mem-child1
    assert "mem-root" in related


def test_find_root_memories(temp_memories_dir):
    """Test finding root memories (no incoming links)."""
    roots = find_root_memories(temp_memories_dir)

    # mem-root should be a root (nothing links to it)
    assert "mem-root" in roots
    # mem-child1 is NOT a root (mem-root links to it)
    assert "mem-child1" not in roots


def test_nonexistent_memory(temp_memories_dir):
    """Test traversal with nonexistent root."""
    result = traverse_graph("mem-nonexistent", temp_memories_dir)

    assert result.visited_count == 0
    assert len(result.nodes) == 0


def test_cycle_detection(temp_memories_dir):
    """Test handling of cycles in memory graph."""
    # Create a cycle: A -> B -> C -> A
    (temp_memories_dir / "mem-cycle-a.md").write_text(
        """---
id: mem-cycle-a
links:
  - related: mem-cycle-b
---
A
"""
    )

    (temp_memories_dir / "mem-cycle-b.md").write_text(
        """---
id: mem-cycle-b
links:
  - related: mem-cycle-c
---
B
"""
    )

    (temp_memories_dir / "mem-cycle-c.md").write_text(
        """---
id: mem-cycle-c
links:
  - related: mem-cycle-a
---
C
"""
    )

    result = traverse_graph("mem-cycle-a", temp_memories_dir, max_depth=10)

    # Should visit each node exactly once despite cycle
    assert result.visited_count == 3
    assert "mem-cycle-a" in result.nodes
    assert "mem-cycle-b" in result.nodes
    assert "mem-cycle-c" in result.nodes


def test_memory_without_frontmatter(temp_memories_dir):
    """Test handling of memories without YAML frontmatter."""
    (temp_memories_dir / "mem-no-frontmatter.md").write_text(
        """
# Simple Memory

No YAML frontmatter, just plain markdown.
"""
    )

    result = traverse_graph("mem-no-frontmatter", temp_memories_dir)

    # Should handle gracefully (no links found)
    assert result.visited_count == 1
    assert "mem-no-frontmatter" in result.nodes
    assert len(result.nodes["mem-no-frontmatter"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
