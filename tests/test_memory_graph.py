"""Tests for memory graph traversal and analysis."""

from __future__ import annotations

import pytest

from memory_enhancement.models import (
    LinkType,
    MemoryLink,
    MemoryWithCitations,
)
from memory_enhancement.graph import (
    build_memory_graph,
    detect_cycles,
    find_orphans,
    find_related,
    traverse,
)


def _make_memory(
    memory_id: str, links: list[MemoryLink] | None = None
) -> MemoryWithCitations:
    return MemoryWithCitations(
        memory_id=memory_id,
        title=memory_id,
        content="",
        links=links or [],
    )


def _make_graph(
    specs: dict[str, list[tuple[str, str]]]
) -> dict[str, MemoryWithCitations]:
    """Build a graph from {id: [(link_type, target_id), ...]}."""
    graph: dict[str, MemoryWithCitations] = {}
    for mid, link_specs in specs.items():
        links = [
            MemoryLink(link_type=LinkType(lt), target_id=tid, context="")
            for lt, tid in link_specs
        ]
        graph[mid] = _make_memory(mid, links)
    return graph


class TestBuildMemoryGraph:
    """Build graph from directory of memory files."""

    @pytest.mark.unit
    def test_build_from_directory(self, tmp_path):
        (tmp_path / "a.md").write_text("# A (2026-01-01)\n\nContent\n")
        (tmp_path / "b.md").write_text("# B (2026-01-02)\n\nContent\n")
        graph = build_memory_graph(tmp_path)
        assert "a" in graph
        assert "b" in graph

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        graph = build_memory_graph(tmp_path)
        assert graph == {}


class TestTraverse:
    """BFS traversal from a starting node."""

    @pytest.mark.unit
    def test_simple_chain(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [("depends_on", "c")],
            "c": [],
        })
        results = traverse(graph, "a", max_depth=3)
        ids = [r[0] for r in results]
        assert "b" in ids
        assert "c" in ids

    @pytest.mark.unit
    def test_respects_max_depth(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [("depends_on", "c")],
            "c": [("depends_on", "d")],
            "d": [],
        })
        results = traverse(graph, "a", max_depth=1)
        ids = [r[0] for r in results]
        assert "b" in ids
        assert "c" not in ids

    @pytest.mark.unit
    def test_nonexistent_start_raises(self):
        graph = _make_graph({"a": []})
        with pytest.raises(KeyError, match="nonexistent"):
            traverse(graph, "nonexistent")

    @pytest.mark.unit
    def test_no_links(self):
        graph = _make_graph({"a": []})
        assert traverse(graph, "a") == []

    @pytest.mark.unit
    def test_returns_depth_and_link_type(self):
        graph = _make_graph({
            "a": [("related_to", "b")],
            "b": [],
        })
        results = traverse(graph, "a", max_depth=2)
        assert len(results) == 1
        assert results[0] == ("b", 1, "related_to")


class TestFindRelated:
    """Find directly related memories with optional type filter."""

    @pytest.mark.unit
    def test_find_all_related(self):
        graph = _make_graph({
            "a": [("depends_on", "b"), ("related_to", "c")],
            "b": [],
            "c": [],
        })
        related = find_related(graph, "a")
        assert set(related) == {"b", "c"}

    @pytest.mark.unit
    def test_filter_by_link_type(self):
        graph = _make_graph({
            "a": [("depends_on", "b"), ("related_to", "c")],
            "b": [],
            "c": [],
        })
        related = find_related(graph, "a", link_types=[LinkType.DEPENDS_ON])
        assert related == ["b"]

    @pytest.mark.unit
    def test_nonexistent_memory(self):
        graph = _make_graph({"a": []})
        assert find_related(graph, "nonexistent") == []

    @pytest.mark.unit
    def test_excludes_targets_not_in_graph(self):
        graph = _make_graph({
            "a": [("depends_on", "external")],
        })
        assert find_related(graph, "a") == []


class TestDetectCycles:
    """Cycle detection in the memory graph."""

    @pytest.mark.unit
    def test_no_cycles(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [],
        })
        assert detect_cycles(graph) == []

    @pytest.mark.unit
    def test_simple_cycle(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [("depends_on", "a")],
        })
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1

    @pytest.mark.unit
    def test_self_loop(self):
        graph = _make_graph({
            "a": [("depends_on", "a")],
        })
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1

    @pytest.mark.unit
    def test_triangle_cycle(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [("depends_on", "c")],
            "c": [("depends_on", "a")],
        })
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1


class TestFindOrphans:
    """Find memories with no incoming links."""

    @pytest.mark.unit
    def test_all_orphans(self):
        graph = _make_graph({"a": [], "b": []})
        assert set(find_orphans(graph)) == {"a", "b"}

    @pytest.mark.unit
    def test_no_orphans(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [("depends_on", "a")],
        })
        assert find_orphans(graph) == []

    @pytest.mark.unit
    def test_mixed(self):
        graph = _make_graph({
            "a": [("depends_on", "b")],
            "b": [],
            "c": [],
        })
        orphans = find_orphans(graph)
        assert "a" in orphans
        assert "c" in orphans
        assert "b" not in orphans

    @pytest.mark.unit
    def test_empty_graph(self):
        assert find_orphans({}) == []
