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
    generate_node_id,
    get_decision_patterns,
    get_episode_files,
    load_causal_graph,
    main,
    save_causal_graph,
)


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
        edge = add_causal_edge(graph, "src", "tgt", "causes", 0.8)
        assert edge is not None
        assert edge["weight"] == 0.8
        assert len(graph["edges"]) == 1

    def test_duplicate_averages_weight(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8)
        edge = add_causal_edge(graph, "src", "tgt", "causes", 0.6)
        assert len(graph["edges"]) == 1
        assert edge is not None
        assert edge["weight"] == 0.7
        assert edge["count"] == 2


class TestAddPattern:
    """Tests for adding patterns."""

    def test_add_new_pattern(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        pat = add_pattern(graph, "test", "desc", "trigger", "action", 1.0)
        assert pat is not None
        assert pat["occurrences"] == 1

    def test_duplicate_updates_rate(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0)
        pat = add_pattern(graph, "test", "desc", "trigger", "action", 0.0)
        assert len(graph["patterns"]) == 1
        assert pat is not None
        assert pat["success_rate"] == 0.5
        assert pat["occurrences"] == 2


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
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
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
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
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
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
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
