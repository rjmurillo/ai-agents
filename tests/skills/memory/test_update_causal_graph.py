"""Tests for update_causal_graph.py."""

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import update_causal_graph


class TestLoadCausalGraph:
    """Tests for load_causal_graph function."""

    def test_empty_graph_structure(self, tmp_path):
        # load_causal_graph returns empty graph when file doesn't exist
        graph = update_causal_graph.load_causal_graph(tmp_path / "nonexistent.json")
        assert "nodes" in graph
        assert "edges" in graph
        assert "patterns" in graph
        assert graph["nodes"] == []


class TestAddCausalNode:
    """Tests for add_causal_node function."""

    def test_adds_new_node(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        node = update_causal_graph.add_causal_node(
            graph, "decision", "Use Python", "ep-1"
        )
        assert node is not None
        assert node["type"] == "decision"
        assert node["label"] == "Use Python"
        assert len(graph["nodes"]) == 1

    def test_updates_existing_node(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_causal_node(graph, "decision", "Use Python", "ep-1")
        node = update_causal_graph.add_causal_node(graph, "decision", "Use Python", "ep-2")
        assert len(graph["nodes"]) == 1
        assert "ep-2" in node["episodes"]


class TestAddCausalEdge:
    """Tests for add_causal_edge function."""

    def test_adds_new_edge(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        edge = update_causal_graph.add_causal_edge(
            graph, "n001", "n002", "causes", 0.8
        )
        assert edge is not None
        assert edge["source"] == "n001"
        assert edge["weight"] == 0.8
        assert len(graph["edges"]) == 1

    def test_updates_existing_edge(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.8)
        edge = update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.6)
        assert len(graph["edges"]) == 1
        assert edge["count"] == 2


class TestAddPattern:
    """Tests for add_pattern function."""

    def test_adds_new_pattern(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        pattern = update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0
        )
        assert pattern is not None
        assert pattern["name"] == "test-pattern"
        assert len(graph["patterns"]) == 1

    def test_updates_existing_pattern(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0
        )
        pattern = update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 0.0
        )
        assert len(graph["patterns"]) == 1
        assert pattern["occurrences"] == 2
        assert pattern["success_rate"] == 0.5


class TestGetDecisionPatterns:
    """Tests for get_decision_patterns function."""

    def test_success_pattern(self):
        episode = {
            "id": "ep-1",
            "decisions": [{
                "type": "design",
                "chosen": "Use factory pattern",
                "outcome": "success",
                "context": "Need flexible creation",
            }],
        }
        patterns = update_causal_graph.get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is True
        assert "design pattern" in patterns[0]["name"]

    def test_failure_antipattern(self):
        episode = {
            "id": "ep-1",
            "decisions": [{
                "type": "test",
                "chosen": "Skip tests",
                "outcome": "failure",
                "context": "",
            }],
        }
        patterns = update_causal_graph.get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is False
        assert "anti-pattern" in patterns[0]["name"]
        assert "AVOID" in patterns[0]["action"]


class TestBuildCausalChains:
    """Tests for build_causal_chains function."""

    def test_error_recovery_chain(self):
        episode = {
            "decisions": [],
            "events": [
                {"type": "error", "content": "Build failed"},
                {"type": "milestone", "content": "Applied fix and recovered"},
            ],
        }
        chains = update_causal_graph.build_causal_chains(episode)
        assert len(chains) >= 1
        assert chains[0]["from_type"] == "error"
        assert chains[0]["edge_type"] == "causes"

    def test_decision_event_chain(self):
        episode = {
            "decisions": [{"chosen": "Use Python scripts", "type": "design"}],
            "events": [
                {"type": "commit", "content": "Converted to Python scripts"},
            ],
        }
        chains = update_causal_graph.build_causal_chains(episode)
        assert len(chains) >= 1

    def test_no_chains(self):
        episode = {"decisions": [], "events": []}
        chains = update_causal_graph.build_causal_chains(episode)
        assert chains == []


class TestGetEpisodeFiles:
    """Tests for get_episode_files function."""

    def test_single_file(self, tmp_path):
        ep = tmp_path / "episode-test.json"
        ep.write_text('{"id": "ep-1"}')
        files = update_causal_graph.get_episode_files(ep, None)
        assert len(files) == 1

    def test_directory(self, tmp_path):
        (tmp_path / "episode-1.json").write_text('{"id": "ep-1"}')
        (tmp_path / "episode-2.json").write_text('{"id": "ep-2"}')
        (tmp_path / "not-an-episode.json").write_text("{}")
        files = update_causal_graph.get_episode_files(tmp_path, None)
        assert len(files) == 2

    def test_missing_path(self, tmp_path):
        files = update_causal_graph.get_episode_files(tmp_path / "missing", None)
        assert files == []

    def test_since_filter(self, tmp_path):
        (tmp_path / "episode-old.json").write_text(
            json.dumps({"timestamp": "2025-01-01T00:00:00"})
        )
        (tmp_path / "episode-new.json").write_text(
            json.dumps({"timestamp": "2026-06-01T00:00:00"})
        )
        # Source expects since as ISO string, not datetime
        files = update_causal_graph.get_episode_files(tmp_path, "2026-01-01")
        assert len(files) == 1
