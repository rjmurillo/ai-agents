#!/usr/bin/env python3
"""Tests for update_causal_graph.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ..scripts.update_causal_graph import (
    add_causal_edge,
    add_causal_node,
    add_pattern,
    build_causal_chains,
    collect_contributions,
    generate_node_id,
    get_decision_patterns,
    get_episode_files,
    load_causal_graph,
    main,
    process_episode,
    remove_episode_contributions,
    save_causal_graph,
)


def _episode_with_recovery(episode_id: str = "episode-edit") -> dict[str, Any]:
    """An episode that yields one error->recovery edge and one success pattern."""
    return {
        "id": episode_id,
        "timestamp": "2026-01-01T00:00:00",
        "outcome": "success",
        "task": "Ship the fix",
        "decisions": [{
            "type": "design",
            "chosen": "Use Python",
            "outcome": "success",
            "context": "Planning",
        }],
        "events": [
            {"type": "error", "content": "Build failed"},
            {"type": "milestone", "content": "Fixed build configuration"},
        ],
    }


class TestGenerateNodeId:
    """Tests for node ID generation."""

    def test_deterministic(self) -> None:
        id1 = generate_node_id("decision", "use Python")
        id2 = generate_node_id("decision", "use Python")
        assert id1 == id2

    def test_different_inputs(self) -> None:
        id1 = generate_node_id("decision", "use Python")
        id2 = generate_node_id("event", "use Python")
        assert id1 != id2

    def test_length(self) -> None:
        node_id = generate_node_id("test", "label")
        assert len(node_id) == 12


class TestLoadCausalGraph:
    """Tests for loading causal graph."""

    def test_missing_file(self, tmp_path: Path) -> None:
        graph = load_causal_graph(tmp_path / "missing.json")
        assert graph == {"nodes": [], "edges": [], "patterns": []}

    def test_valid_file(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "graph.json"
        data = {"nodes": [{"id": "abc"}], "edges": [], "patterns": []}
        graph_file.write_text(json.dumps(data))

        graph = load_causal_graph(graph_file)
        assert len(graph["nodes"]) == 1

    def test_invalid_json(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "graph.json"
        graph_file.write_text("not json")

        graph = load_causal_graph(graph_file)
        assert graph == {"nodes": [], "edges": [], "patterns": []}


class TestSaveCausalGraph:
    """Tests for saving causal graph."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "sub" / "graph.json"
        save_causal_graph(graph_file, {"nodes": [], "edges": [], "patterns": []})
        assert graph_file.is_file()

    def test_content_roundtrip(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "graph.json"
        data = {"nodes": [{"id": "test"}], "edges": [], "patterns": []}
        save_causal_graph(graph_file, data)

        loaded = json.loads(graph_file.read_text())
        assert loaded["nodes"][0]["id"] == "test"


class TestAddCausalNode:
    """Tests for adding nodes."""

    def test_add_new_node(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        node = add_causal_node(graph, "decision", "test label", "ep-001")
        assert node is not None
        assert node["type"] == "decision"
        assert len(graph["nodes"]) == 1

    def test_duplicate_updates_episodes(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_node(graph, "decision", "test label", "ep-001")
        node = add_causal_node(graph, "decision", "test label", "ep-002")
        assert len(graph["nodes"]) == 1
        assert node is not None
        assert "ep-002" in node["episodes"]


class TestAddCausalEdge:
    """Tests for adding edges."""

    def test_add_new_edge(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        edge = add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        assert edge is not None
        assert edge["weight"] == 0.8
        assert edge["evidence_count"] == 1
        assert edge["episodes"] == ["ep-001"]
        assert len(graph["edges"]) == 1

    def test_duplicate_averages_weight(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        edge = add_causal_edge(graph, "src", "tgt", "causes", 0.6, "ep-002")
        assert len(graph["edges"]) == 1
        assert edge is not None
        assert edge["weight"] == 0.7
        assert edge["evidence_count"] == 2

    def test_same_episode_reprocess_is_noop(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        assert add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001") is None
        assert graph["edges"][0]["evidence_count"] == 1


class TestAddPattern:
    """Tests for adding patterns."""

    def test_add_new_pattern(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        pat = add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-001")
        assert pat is not None
        assert pat["occurrences"] == 1
        assert pat["episodes"] == ["ep-001"]

    def test_duplicate_updates_rate(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-001")
        pat = add_pattern(graph, "test", "desc", "trigger", "action", 0.0, "ep-002")
        assert len(graph["patterns"]) == 1
        assert pat is not None
        assert pat["success_rate"] == 0.5
        assert pat["occurrences"] == 2

    def test_running_average_is_occurrence_weighted(self) -> None:
        # 1.0, 1.0, 0.0 must average to 0.67, not 0.50 (#3034 review).
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-001")
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-002")
        add_pattern(graph, "test", "desc", "trigger", "action", 0.0, "ep-003")
        pat = graph["patterns"][0]
        assert pat["occurrences"] == 3
        assert pat["success_rate"] == 0.67


class TestGetEpisodeFiles:
    """Tests for episode file discovery."""

    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "episode-test.json"
        f.write_text(json.dumps({"id": "test", "timestamp": "2026-01-01T00:00:00"}))
        assert get_episode_files(f) == [f]

    def test_directory(self, tmp_path: Path) -> None:
        (tmp_path / "episode-001.json").write_text("{}")
        (tmp_path / "episode-002.json").write_text("{}")
        (tmp_path / "other.json").write_text("{}")
        files = get_episode_files(tmp_path)
        assert len(files) == 2

    def test_missing_path(self, tmp_path: Path) -> None:
        assert get_episode_files(tmp_path / "missing") == []


class TestGetDecisionPatterns:
    """Tests for decision pattern extraction."""

    def test_success_pattern(self) -> None:
        episode = {
            "id": "ep-001",
            "decisions": [{
                "type": "design",
                "chosen": "Use Python for migration",
                "outcome": "success",
                "context": "Migration planning",
            }],
        }
        patterns = get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is True
        assert "design" in patterns[0]["name"]

    def test_failure_anti_pattern(self) -> None:
        episode = {
            "id": "ep-001",
            "decisions": [{
                "type": "test",
                "chosen": "Skip unit tests",
                "outcome": "failure",
                "context": "Time pressure",
            }],
        }
        patterns = get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is False
        assert "AVOID" in patterns[0]["action"]


class TestBuildCausalChains:
    """Tests for causal chain building."""

    def test_error_recovery_chain(self) -> None:
        episode = {
            "events": [
                {"type": "error", "content": "Build failed"},
                {"type": "milestone", "content": "Fixed build configuration"},
            ],
            "decisions": [],
        }
        chains = build_causal_chains(episode)
        assert len(chains) >= 1
        assert chains[0]["edge_type"] == "causes"

    def test_no_chains_without_errors(self) -> None:
        episode = {
            "events": [
                {"type": "milestone", "content": "Completed task"},
            ],
            "decisions": [],
        }
        chains = build_causal_chains(episode)
        assert len(chains) == 0


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_no_episodes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        result = main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
        ])
        assert result == 0

    def test_processes_episode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        episode = {
            "id": "episode-test",
            "timestamp": "2026-01-01T00:00:00",
            "outcome": "success",
            "task": "Test task",
            "decisions": [{
                "type": "design",
                "chosen": "Use Python",
                "outcome": "success",
                "context": "Planning",
            }],
            "events": [],
            "lessons": [],
        }
        (ep_dir / "episode-test.json").write_text(json.dumps(episode))

        result = main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
        ])
        assert result == 0

        captured = capsys.readouterr()
        stats = json.loads(captured.out)
        assert stats["episodes_processed"] == 1
        assert stats["nodes_added"] > 0

        graph = json.loads(graph_file.read_text())
        assert len(graph["nodes"]) > 0

    def test_dry_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        episode = {
            "id": "episode-dry",
            "timestamp": "2026-01-01T00:00:00",
            "outcome": "success",
            "task": "Dry run test",
            "decisions": [{
                "type": "test",
                "chosen": "Write unit tests",
                "outcome": "success",
            }],
            "events": [],
        }
        (ep_dir / "episode-dry.json").write_text(json.dumps(episode))

        result = main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
            "--dry-run",
        ])
        assert result == 0
        assert not graph_file.exists()


class TestCollectContributions:
    """Tests for single-source contribution derivation (#3039)."""

    def test_includes_chain_endpoint_and_decision_node_labels(self) -> None:
        # The decision loop labels the node "design: Use Python"; the chain
        # endpoint labels the same decision "Use Python". Both must surface so
        # the keep-set never strips a live node.
        episode = _episode_with_recovery()
        nodes, edges, patterns = collect_contributions(episode)
        node_labels = {label for _t, label in nodes}
        assert "design: Use Python" in node_labels
        assert ("outcome", "Outcome: success - Ship the fix") in nodes
        assert len(edges) == 1
        assert edges[0][0] == "error"
        assert edges[0][1] == "Build failed"
        assert any("pattern" in name for name, *_ in patterns)


class TestRemoveEpisodeContributions:
    """Tests for pruning an episode's contributions (#3039)."""

    def test_sole_contributor_node_dropped(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_node(graph, "decision", "only", "ep-001")
        removed = remove_episode_contributions(graph, "ep-001")
        assert graph["nodes"] == []
        assert removed["nodes"] == 1

    def test_kept_node_untouched(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        node = add_causal_node(graph, "decision", "keep", "ep-001")
        assert node is not None
        removed = remove_episode_contributions(
            graph, "ep-001", keep_node_ids=frozenset({node["id"]}),
        )
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["episodes"] == ["ep-001"]
        assert removed["nodes"] == 0

    def test_multi_contributor_edge_decrements_and_preserves_weight(self) -> None:
        # Both episodes contribute the same weight (the generator invariant), so
        # removing one leaves the average exact and just decrements the count.
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-002")
        removed = remove_episode_contributions(graph, "ep-001")
        assert len(graph["edges"]) == 1
        edge = graph["edges"][0]
        assert edge["episodes"] == ["ep-002"]
        assert edge["evidence_count"] == 1
        assert edge["weight"] == 0.8
        assert removed["edges"] == 0

    def test_sole_contributor_edge_dropped(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        removed = remove_episode_contributions(graph, "ep-001")
        assert graph["edges"] == []
        assert removed["edges"] == 1

    def test_pattern_occurrences_decrement(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_pattern(graph, "p", "d", "t", "a", 1.0, "ep-001")
        add_pattern(graph, "p", "d", "t", "a", 1.0, "ep-002")
        remove_episode_contributions(graph, "ep-001")
        assert len(graph["patterns"]) == 1
        assert graph["patterns"][0]["occurrences"] == 1
        assert graph["patterns"][0]["episodes"] == ["ep-002"]

    def test_legacy_edge_without_evidence_count(self) -> None:
        # Pre-#3034 edges stored ``count`` and no ``episodes``; a sole-episode
        # legacy edge that gained provenance is dropped when that episode goes.
        graph: dict[str, Any] = {
            "nodes": [],
            "edges": [{
                "source": "s", "target": "t", "type": "causes",
                "weight": 0.6, "count": 3, "episodes": ["ep-001", "ep-002"],
            }],
            "patterns": [],
        }
        remove_episode_contributions(graph, "ep-001")
        edge = graph["edges"][0]
        assert edge["episodes"] == ["ep-002"]
        assert edge["evidence_count"] == 2
        assert "count" not in edge

    def test_full_removal_with_empty_keep_sets(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_node(graph, "decision", "n", "ep-001")
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        add_pattern(graph, "p", "d", "t", "a", 1.0, "ep-001")
        removed = remove_episode_contributions(graph, "ep-001")
        assert graph == {"nodes": [], "edges": [], "patterns": []}
        assert removed == {"nodes": 1, "edges": 1, "patterns": 1}


class TestReplaceSemantics:
    """Edit-shrinks and deletion pruning through main() (#3039)."""

    def _run(self, ep_dir: Path, graph_file: Path, *extra: str) -> None:
        assert main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
            *extra,
        ]) == 0

    def test_edit_removes_obsolete_edge(self, tmp_path: Path) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        ep_file = ep_dir / "episode-edit.json"

        ep_file.write_text(json.dumps(_episode_with_recovery()))
        self._run(ep_dir, graph_file)
        graph = json.loads(graph_file.read_text())
        assert len(graph["edges"]) == 1

        shrunk = _episode_with_recovery()
        shrunk["events"] = [{"type": "error", "content": "Build failed"}]
        ep_file.write_text(json.dumps(shrunk))
        self._run(ep_dir, graph_file)

        graph = json.loads(graph_file.read_text())
        assert graph["edges"] == []

    def test_edit_removes_obsolete_pattern(self, tmp_path: Path) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        ep_file = ep_dir / "episode-edit.json"

        ep_file.write_text(json.dumps(_episode_with_recovery()))
        self._run(ep_dir, graph_file)
        graph = json.loads(graph_file.read_text())
        assert len(graph["patterns"]) == 1

        shrunk = _episode_with_recovery()
        shrunk["decisions"] = []
        ep_file.write_text(json.dumps(shrunk))
        self._run(ep_dir, graph_file)

        graph = json.loads(graph_file.read_text())
        assert graph["patterns"] == []

    def test_reprocess_unchanged_is_byte_stable(self, tmp_path: Path) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        (ep_dir / "episode-edit.json").write_text(
            json.dumps(_episode_with_recovery()),
        )

        self._run(ep_dir, graph_file)
        first = graph_file.read_text()
        self._run(ep_dir, graph_file)
        second = graph_file.read_text()
        assert first == second

    def test_deleted_episode_id_prunes(self, tmp_path: Path) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        (ep_dir / "episode-del.json").write_text(
            json.dumps(_episode_with_recovery("episode-del")),
        )
        self._run(ep_dir, graph_file)
        graph = json.loads(graph_file.read_text())
        assert graph["nodes"] and graph["edges"] and graph["patterns"]

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        self._run(empty_dir, graph_file, "--deleted-episode-id", "episode-del")

        graph = json.loads(graph_file.read_text())
        assert graph == {"nodes": [], "edges": [], "patterns": []}

    def test_deleted_episode_id_dry_run_preserves_graph(
        self, tmp_path: Path,
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        (ep_dir / "episode-del.json").write_text(
            json.dumps(_episode_with_recovery("episode-del")),
        )
        self._run(ep_dir, graph_file)
        before = graph_file.read_text()

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        self._run(
            empty_dir, graph_file,
            "--deleted-episode-id", "episode-del", "--dry-run",
        )
        assert graph_file.read_text() == before


class TestProcessEpisode:
    """Direct tests for the process_episode helper (#3039)."""

    def test_dry_run_returns_zero_deltas(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        deltas = process_episode(
            graph, _episode_with_recovery(), "episode-edit", dry_run=True,
        )
        assert graph == {"nodes": [], "edges": [], "patterns": []}
        assert deltas["nodes_added"] == 0
        assert deltas["nodes_removed"] == 0

    def test_removes_stale_and_reports_delta(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        process_episode(graph, _episode_with_recovery(), "episode-edit", False)
        assert len(graph["edges"]) == 1

        shrunk = _episode_with_recovery()
        shrunk["events"] = [{"type": "error", "content": "Build failed"}]
        deltas = process_episode(graph, shrunk, "episode-edit", False)
        assert graph["edges"] == []
        assert deltas["edges_removed"] == 1
