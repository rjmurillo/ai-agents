"""Tests for memory_enhancement.graph module."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from memory_enhancement.graph import (
    LINK_WEIGHTS,
    MemoryGraph,
    RelationshipScore,
    TraversalNode,
)
from memory_enhancement.models import Link, LinkType, Memory


def _make_memory(
    memory_id: str,
    links: list[tuple[LinkType, str]] | None = None,
) -> Memory:
    """Create a Memory with the given id and links.

    Args:
        memory_id: Unique identifier for the memory.
        links: List of (LinkType, target_id) pairs.

    Returns:
        Memory instance with the specified links.
    """
    return Memory(
        id=memory_id,
        subject=f"Subject for {memory_id}",
        path=Path(f"{memory_id}.md"),
        content=f"Content for {memory_id}.",
        links=[
            Link(link_type=lt, target_id=tid)
            for lt, tid in (links or [])
        ],
    )


def _build_graph(specs: dict[str, list[tuple[LinkType, str]]]) -> MemoryGraph:
    """Build a MemoryGraph from a specification dict.

    Args:
        specs: Mapping of memory_id to list of (LinkType, target_id) pairs.

    Returns:
        MemoryGraph constructed from the specifications.
    """
    memories = {
        mid: _make_memory(mid, link_list)
        for mid, link_list in specs.items()
    }
    return MemoryGraph(memories)


class TestMemoryGraph:
    """Tests for MemoryGraph construction."""

    @pytest.mark.unit
    def test_from_directory_loads_memories(self, graph_memories_dir: Path) -> None:
        graph = MemoryGraph.from_directory(graph_memories_dir)
        assert graph.node_count == 5

    @pytest.mark.unit
    def test_from_directory_empty_dir(self, memories_dir: Path) -> None:
        graph = MemoryGraph.from_directory(memories_dir)
        assert graph.node_count == 0
        assert graph.edge_count == 0

    @pytest.mark.unit
    def test_from_directory_skips_invalid_files(self, memories_dir: Path) -> None:
        (memories_dir / "valid.md").write_text(
            "---\nid: valid\nsubject: Valid\n---\nOK.\n",
            encoding="utf-8",
        )
        (memories_dir / "broken.md").write_text(
            "This is not valid YAML frontmatter at all {{{",
            encoding="utf-8",
        )
        graph = MemoryGraph.from_directory(memories_dir)
        assert graph.node_count >= 1

    @pytest.mark.unit
    def test_node_count(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [],
            "c": [],
        })
        assert graph.node_count == 3

    @pytest.mark.unit
    def test_edge_count(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b"), (LinkType.EXTENDS, "c")],
            "b": [(LinkType.BLOCKS, "c")],
            "c": [],
        })
        assert graph.edge_count == 3

    @pytest.mark.unit
    def test_construction_from_dict(self) -> None:
        memories = {
            "x": _make_memory("x", [(LinkType.IMPLEMENTS, "y")]),
            "y": _make_memory("y"),
        }
        graph = MemoryGraph(memories)
        assert graph.node_count == 2
        assert graph.edge_count == 1


class TestBFS:
    """Tests for breadth-first traversal."""

    @pytest.mark.unit
    def test_simple_chain(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "c")],
            "c": [],
        })
        result = graph.bfs("a")
        ids_depths = [(n.memory_id, n.depth) for n in result]
        assert ids_depths == [("a", 0), ("b", 1), ("c", 2)]

    @pytest.mark.unit
    def test_branching(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b"), (LinkType.RELATED, "c")],
            "b": [],
            "c": [],
        })
        result = graph.bfs("a")
        assert result[0].memory_id == "a"
        assert result[0].depth == 0
        depth_1_ids = {n.memory_id for n in result if n.depth == 1}
        assert depth_1_ids == {"b", "c"}

    @pytest.mark.unit
    def test_max_depth_limits(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "c")],
            "c": [(LinkType.RELATED, "d")],
            "d": [],
        })
        result = graph.bfs("a", max_depth=1)
        ids = [n.memory_id for n in result]
        assert "a" in ids
        assert "b" in ids
        assert "c" not in ids
        assert "d" not in ids

    @pytest.mark.unit
    def test_max_depth_zero(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [],
        })
        result = graph.bfs("a", max_depth=0)
        assert len(result) == 1
        assert result[0].memory_id == "a"
        assert result[0].depth == 0

    @pytest.mark.unit
    def test_start_not_found_raises_keyerror(self) -> None:
        graph = _build_graph({"a": []})
        with pytest.raises(KeyError, match="nonexistent"):
            graph.bfs("nonexistent")

    @pytest.mark.unit
    def test_handles_links_to_nonexistent(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "ghost")],
        })
        result = graph.bfs("a")
        ids = [n.memory_id for n in result]
        assert ids == ["a"]

    @pytest.mark.unit
    def test_single_node_no_links(self) -> None:
        graph = _build_graph({"solo": []})
        result = graph.bfs("solo")
        assert len(result) == 1
        assert result[0].memory_id == "solo"
        assert result[0].depth == 0
        assert result[0].parent_id is None
        assert result[0].link_type is None

    @pytest.mark.unit
    def test_parent_and_link_type_populated(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.IMPLEMENTS, "b")],
            "b": [],
        })
        result = graph.bfs("a")
        child = result[1]
        assert child.memory_id == "b"
        assert child.parent_id == "a"
        assert child.link_type == "implements"

    @pytest.mark.unit
    def test_cycle_does_not_loop(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "a")],
        })
        result = graph.bfs("a")
        ids = [n.memory_id for n in result]
        assert ids == ["a", "b"]


class TestDFS:
    """Tests for depth-first traversal."""

    @pytest.mark.unit
    def test_simple_chain(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "c")],
            "c": [],
        })
        result = graph.dfs("a")
        ids_depths = [(n.memory_id, n.depth) for n in result]
        assert ids_depths == [("a", 0), ("b", 1), ("c", 2)]

    @pytest.mark.unit
    def test_branching_differs_from_bfs(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b"), (LinkType.RELATED, "c")],
            "b": [(LinkType.RELATED, "d")],
            "c": [],
            "d": [],
        })
        bfs_result = graph.bfs("a")
        dfs_result = graph.dfs("a")
        bfs_ids = [n.memory_id for n in bfs_result]
        dfs_ids = [n.memory_id for n in dfs_result]
        assert set(bfs_ids) == set(dfs_ids)
        # DFS goes deep first: a -> b -> d, then c
        # BFS goes wide first: a -> b, c, then d
        assert dfs_ids == ["a", "b", "d", "c"]
        assert bfs_ids == ["a", "b", "c", "d"]

    @pytest.mark.unit
    def test_max_depth_limits(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "c")],
            "c": [(LinkType.RELATED, "d")],
            "d": [],
        })
        result = graph.dfs("a", max_depth=1)
        ids = [n.memory_id for n in result]
        assert "a" in ids
        assert "b" in ids
        assert "c" not in ids

    @pytest.mark.unit
    def test_max_depth_zero(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [],
        })
        result = graph.dfs("a", max_depth=0)
        assert len(result) == 1
        assert result[0].memory_id == "a"

    @pytest.mark.unit
    def test_start_not_found_raises_keyerror(self) -> None:
        graph = _build_graph({"a": []})
        with pytest.raises(KeyError, match="nonexistent"):
            graph.dfs("nonexistent")

    @pytest.mark.unit
    def test_cycle_does_not_loop(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "a")],
        })
        result = graph.dfs("a")
        ids = [n.memory_id for n in result]
        assert ids == ["a", "b"]

    @pytest.mark.unit
    def test_parent_and_link_type_populated(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.EXTENDS, "b")],
            "b": [],
        })
        result = graph.dfs("a")
        child = result[1]
        assert child.parent_id == "a"
        assert child.link_type == "extends"

    @pytest.mark.unit
    def test_handles_links_to_nonexistent(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "ghost")],
        })
        result = graph.dfs("a")
        ids = [n.memory_id for n in result]
        assert ids == ["a"]


class TestCycleDetection:
    """Tests for find_cycles."""

    @pytest.mark.unit
    def test_no_cycles(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "c")],
            "c": [],
        })
        cycles = graph.find_cycles()
        assert cycles == []

    @pytest.mark.unit
    def test_simple_cycle(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "a")],
        })
        cycles = graph.find_cycles()
        assert len(cycles) >= 1
        flat = [node for cycle in cycles for node in cycle]
        assert "a" in flat
        assert "b" in flat

    @pytest.mark.unit
    def test_triangle_cycle(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.EXTENDS, "c")],
            "c": [(LinkType.BLOCKS, "a")],
        })
        cycles = graph.find_cycles()
        assert len(cycles) >= 1
        cycle_nodes = set()
        for cycle in cycles:
            cycle_nodes.update(cycle)
        assert {"a", "b", "c"}.issubset(cycle_nodes)

    @pytest.mark.unit
    def test_self_cycle(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "a")],
        })
        cycles = graph.find_cycles()
        assert len(cycles) >= 1
        flat = [node for cycle in cycles for node in cycle]
        assert "a" in flat

    @pytest.mark.unit
    def test_multiple_cycles(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "a")],
            "c": [(LinkType.RELATED, "d")],
            "d": [(LinkType.RELATED, "c")],
        })
        cycles = graph.find_cycles()
        assert len(cycles) >= 2

    @pytest.mark.unit
    def test_empty_graph(self) -> None:
        graph = _build_graph({})
        cycles = graph.find_cycles()
        assert cycles == []

    @pytest.mark.unit
    def test_links_to_nonexistent_skipped(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "ghost")],
        })
        cycles = graph.find_cycles()
        assert cycles == []

    @pytest.mark.unit
    def test_from_directory_with_cycles(self, cyclic_memories_dir: Path) -> None:
        graph = MemoryGraph.from_directory(cyclic_memories_dir)
        cycles = graph.find_cycles()
        assert len(cycles) >= 1


class TestRelationshipScoring:
    """Tests for score_relationships."""

    @pytest.mark.unit
    def test_implements_highest_score(self) -> None:
        graph = _build_graph({
            "a": [
                (LinkType.IMPLEMENTS, "b"),
                (LinkType.RELATED, "c"),
            ],
            "b": [],
            "c": [],
        })
        scores = graph.score_relationships("a")
        score_map = {s.target_id: s for s in scores}
        assert score_map["b"].score > score_map["c"].score
        # implements weight 1.0, distance 1: score = 1.0 / (1+1) = 0.5
        assert score_map["b"].score == pytest.approx(LINK_WEIGHTS["implements"] / 2)
        # related weight 0.3, distance 1: score = 0.3 / (1+1) = 0.15
        assert score_map["c"].score == pytest.approx(LINK_WEIGHTS["related"] / 2)

    @pytest.mark.unit
    def test_distance_decay(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [(LinkType.RELATED, "c")],
            "c": [],
        })
        scores = graph.score_relationships("a")
        score_map = {s.target_id: s for s in scores}
        # b at distance 1: 0.3 / 2 = 0.15
        # c at distance 2: 0.3 / 3 = 0.1
        assert score_map["b"].distance == 1
        assert score_map["c"].distance == 2
        assert score_map["b"].score > score_map["c"].score
        assert score_map["b"].score == pytest.approx(0.3 / 2)
        assert score_map["c"].score == pytest.approx(0.3 / 3)

    @pytest.mark.unit
    def test_sorted_descending(self) -> None:
        graph = _build_graph({
            "a": [
                (LinkType.RELATED, "b"),
                (LinkType.IMPLEMENTS, "c"),
                (LinkType.EXTENDS, "d"),
            ],
            "b": [],
            "c": [],
            "d": [],
        })
        scores = graph.score_relationships("a")
        for i in range(len(scores) - 1):
            assert scores[i].score >= scores[i + 1].score

    @pytest.mark.unit
    def test_start_not_found_raises_keyerror(self) -> None:
        graph = _build_graph({"a": []})
        with pytest.raises(KeyError, match="missing"):
            graph.score_relationships("missing")

    @pytest.mark.unit
    def test_no_reachable_nodes(self) -> None:
        graph = _build_graph({"isolated": []})
        scores = graph.score_relationships("isolated")
        assert scores == []

    @pytest.mark.unit
    def test_excludes_start_node(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.RELATED, "b")],
            "b": [],
        })
        scores = graph.score_relationships("a")
        target_ids = [s.target_id for s in scores]
        assert "a" not in target_ids

    @pytest.mark.unit
    def test_score_uses_link_type_from_traversal(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.EXTENDS, "b")],
            "b": [],
        })
        scores = graph.score_relationships("a")
        assert len(scores) == 1
        assert scores[0].link_type == "extends"
        assert scores[0].score == pytest.approx(LINK_WEIGHTS["extends"] / 2)

    @pytest.mark.unit
    def test_all_link_weights_covered(self) -> None:
        expected_types = {"implements", "extends", "blocks", "supersedes", "related"}
        assert set(LINK_WEIGHTS.keys()) == expected_types

    @pytest.mark.unit
    def test_relationship_score_fields(self) -> None:
        graph = _build_graph({
            "a": [(LinkType.BLOCKS, "b")],
            "b": [],
        })
        scores = graph.score_relationships("a")
        rs = scores[0]
        assert isinstance(rs, RelationshipScore)
        assert rs.target_id == "b"
        assert rs.link_type == "blocks"
        assert rs.distance == 1
        assert rs.score == pytest.approx(LINK_WEIGHTS["blocks"] / 2)


class TestTraversalNode:
    """Tests for TraversalNode dataclass."""

    @pytest.mark.unit
    def test_defaults(self) -> None:
        node = TraversalNode(memory_id="x", depth=0)
        assert node.memory_id == "x"
        assert node.depth == 0
        assert node.link_type is None
        assert node.parent_id is None

    @pytest.mark.unit
    def test_all_fields(self) -> None:
        node = TraversalNode(
            memory_id="y",
            depth=3,
            link_type="implements",
            parent_id="x",
        )
        assert node.memory_id == "y"
        assert node.depth == 3
        assert node.link_type == "implements"
        assert node.parent_id == "x"


class TestFromDirectory:
    """Tests for MemoryGraph.from_directory edge cases."""

    @pytest.mark.unit
    def test_traversal_after_directory_load(self, graph_memories_dir: Path) -> None:
        graph = MemoryGraph.from_directory(graph_memories_dir)
        result = graph.bfs("memory-a")
        ids = {n.memory_id for n in result}
        assert "memory-a" in ids
        assert "memory-b" in ids
        assert "memory-d" in ids

    @pytest.mark.unit
    def test_edge_count_from_directory(self, graph_memories_dir: Path) -> None:
        graph = MemoryGraph.from_directory(graph_memories_dir)
        # A has 2 links, B has 1, D has 1 = 4 total edges
        assert graph.edge_count == 4

    @pytest.mark.unit
    def test_nonexistent_directory_returns_empty_graph(self) -> None:
        graph = MemoryGraph.from_directory(Path("/nonexistent/dir"))
        assert graph.node_count == 0
        assert graph.edge_count == 0

    @pytest.mark.unit
    def test_unicode_decode_error_skipped(self, memories_dir: Path) -> None:
        (memories_dir / "valid.md").write_text(
            "---\nid: valid\nsubject: V\n---\nOK.\n",
            encoding="utf-8",
        )
        (memories_dir / "binary.md").write_bytes(b"\x80\x81\x82\x83")
        graph = MemoryGraph.from_directory(memories_dir)
        assert graph.node_count == 1

    @pytest.mark.unit
    def test_non_md_files_ignored(self, memories_dir: Path) -> None:
        (memories_dir / "readme.txt").write_text("not a memory", encoding="utf-8")
        (memories_dir / "valid.md").write_text(
            "---\nid: valid\nsubject: V\n---\nOK.\n",
            encoding="utf-8",
        )
        graph = MemoryGraph.from_directory(memories_dir)
        assert graph.node_count == 1


class TestPerformance:
    """Performance benchmarks for graph traversal."""

    @pytest.mark.integration
    def test_bfs_1000_nodes_under_500ms(self, large_graph_dir: Path) -> None:
        graph = MemoryGraph.from_directory(large_graph_dir)
        assert graph.node_count >= 1000

        start = time.perf_counter()
        result = graph.bfs("node-0")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) > 0
        assert elapsed_ms < 500, f"BFS took {elapsed_ms:.1f}ms, expected <500ms"

    @pytest.mark.integration
    def test_dfs_1000_nodes_under_500ms(self, large_graph_dir: Path) -> None:
        graph = MemoryGraph.from_directory(large_graph_dir)
        assert graph.node_count >= 1000

        start = time.perf_counter()
        result = graph.dfs("node-0")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) > 0
        assert elapsed_ms < 500, f"DFS took {elapsed_ms:.1f}ms, expected <500ms"

    @pytest.mark.integration
    def test_cycle_detection_1000_nodes(self, large_graph_dir: Path) -> None:
        graph = MemoryGraph.from_directory(large_graph_dir)
        start = time.perf_counter()
        graph.find_cycles()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5000, (
            f"Cycle detection took {elapsed_ms:.1f}ms, expected <5000ms"
        )

    @pytest.mark.integration
    def test_score_relationships_1000_nodes(self, large_graph_dir: Path) -> None:
        graph = MemoryGraph.from_directory(large_graph_dir)
        start = time.perf_counter()
        scores = graph.score_relationships("node-0")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(scores) > 0
        assert elapsed_ms < 1000, (
            f"score_relationships took {elapsed_ms:.1f}ms, expected <1000ms"
        )
