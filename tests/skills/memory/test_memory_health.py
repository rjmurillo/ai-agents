"""Tests for test_memory_health.py."""

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import test_memory_health


class TestSerenaAvailable:
    """Tests for test_serena_available function."""

    def test_available_with_files(self, tmp_path):
        # Source expects the serena_path directly (the memories directory)
        memories = tmp_path / "memories"
        memories.mkdir(parents=True)
        (memories / "test.md").write_text("# Test")

        result = test_memory_health.test_serena_available(memories)
        assert result["available"] is True
        assert result["count"] == 1

    def test_unavailable_when_missing(self, tmp_path):
        result = test_memory_health.test_serena_available(tmp_path / "nonexistent")
        assert result["available"] is False
        assert result["count"] == 0


class TestForgetfulAvailable:
    """Tests for test_forgetful_available function."""

    def test_unavailable(self):
        result = test_memory_health.test_forgetful_available()
        # In test env, Forgetful is not running
        assert "available" in result
        assert "endpoint" in result


class TestEpisodesAvailable:
    """Tests for test_episodes_available function."""

    def test_available_with_episodes(self, tmp_path):
        # Source expects the episodes directory path directly
        episodes = tmp_path / "episodes"
        episodes.mkdir(parents=True)
        (episodes / "episode-2026-01-01-session-1.json").write_text("{}")

        result = test_memory_health.test_episodes_available(episodes)
        assert result["available"] is True
        assert result["count"] == 1

    def test_unavailable_when_missing(self, tmp_path):
        result = test_memory_health.test_episodes_available(tmp_path / "nonexistent")
        assert result["available"] is False


class TestCausalGraphAvailable:
    """Tests for test_causal_graph_available function."""

    def test_directory_missing(self, tmp_path):
        result = test_memory_health.test_causal_graph_available(tmp_path / "nonexistent")
        assert result["available"] is False
        assert result["nodes"] == 0

    def test_directory_exists_no_graph(self, tmp_path):
        causality = tmp_path / "causality"
        causality.mkdir(parents=True)

        result = test_memory_health.test_causal_graph_available(causality)
        assert result["available"] is True
        assert result["nodes"] == 0

    def test_graph_with_data(self, tmp_path):
        causality = tmp_path / "causality"
        causality.mkdir(parents=True)
        graph = {"nodes": [{"id": "n1"}], "edges": [], "patterns": []}
        (causality / "causal-graph.json").write_text(json.dumps(graph))

        result = test_memory_health.test_causal_graph_available(causality)
        assert result["available"] is True
        assert result["nodes"] == 1

    def test_corrupted_graph(self, tmp_path):
        causality = tmp_path / "causality"
        causality.mkdir(parents=True)
        (causality / "causal-graph.json").write_text("not json{")

        result = test_memory_health.test_causal_graph_available(causality)
        assert result["available"] is False


class TestModulesAvailable:
    """Tests for test_modules_available function."""

    def test_checks_module_files(self, tmp_path):
        # Source checks for memory_core/memory_router.py and memory_core/reflexion_memory.py
        result = test_memory_health.test_modules_available(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 2
        names = [m["name"] for m in result]
        assert "memory_router" in names
        assert "reflexion_memory" in names

    def test_existing_modules(self, tmp_path):
        core_dir = tmp_path / "memory_core"
        core_dir.mkdir()
        (core_dir / "memory_router.py").write_text("# module")
        result = test_memory_health.test_modules_available(tmp_path)
        router = [m for m in result if m["name"] == "memory_router"][0]
        assert router["available"] is True
