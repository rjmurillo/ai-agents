#!/usr/bin/env python3
"""Tests for reflexion_memory module.

Coverage target: all public functions for episodes, causal graph, and patterns.

Exit codes (ADR-035):
    0 - Success: all tests passed
    1 - Error: one or more tests failed
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import memory_core.reflexion_memory as rm
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path: Path) -> Iterator[None]:
    """Redirect all paths to temp directory for test isolation."""
    episodes_path = tmp_path / "episodes"
    causality_path = tmp_path / "causality"
    schemas_path = tmp_path / "schemas"

    episodes_path.mkdir()
    causality_path.mkdir()
    schemas_path.mkdir()

    # Create minimal schemas for validation
    episode_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["id", "session", "timestamp", "outcome", "task"],
        "properties": {
            "id": {"type": "string"},
            "session": {"type": "string"},
            "timestamp": {"type": "string"},
            "outcome": {"type": "string"},
            "task": {"type": "string"},
            "decisions": {"type": "array"},
            "events": {"type": "array"},
            "metrics": {"type": "object"},
            "lessons": {"type": "array"},
        },
    }
    (schemas_path / "episode.schema.json").write_text(
        json.dumps(episode_schema, indent=2), encoding="utf-8"
    )

    causal_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["version", "updated", "nodes", "edges", "patterns"],
        "properties": {
            "version": {"type": "string"},
            "updated": {"type": "string"},
            "nodes": {"type": "array"},
            "edges": {"type": "array"},
            "patterns": {"type": "array"},
        },
    }
    (schemas_path / "causal-graph.schema.json").write_text(
        json.dumps(causal_schema, indent=2), encoding="utf-8"
    )

    # Patch module-level paths
    with patch.object(rm, "EPISODES_PATH", episodes_path), patch.object(
        rm, "CAUSALITY_PATH", causality_path
    ), patch.object(
        rm, "CAUSAL_GRAPH_FILE", causality_path / "causal-graph.json"
    ), patch.object(rm, "SCHEMAS_PATH", schemas_path), patch.object(
        rm, "EPISODE_SCHEMA_FILE", schemas_path / "episode.schema.json"
    ), patch.object(
        rm,
        "CAUSAL_GRAPH_SCHEMA_FILE",
        schemas_path / "causal-graph.schema.json",
    ):
        yield


@pytest.fixture()
def sample_episode(tmp_path: Path) -> dict:
    """Create a sample episode file and return its data."""
    episode = {
        "id": "episode-2026-01-01-session-001",
        "session": "2026-01-01-session-001",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "outcome": "success",
        "task": "Implement feature",
        "decisions": [
            {
                "id": "d001",
                "timestamp": "2026-01-01T12:05:00+00:00",
                "type": "design",
                "chosen": "Strategy pattern",
                "rationale": "CVA analysis",
            },
            {
                "id": "d002",
                "timestamp": "2026-01-01T12:01:00+00:00",
                "type": "implementation",
                "chosen": "TDD approach",
                "rationale": "Test first",
            },
        ],
        "events": [],
        "metrics": {"duration_minutes": 45},
        "lessons": ["TDD works well for clear requirements"],
    }

    episode_file = rm.EPISODES_PATH / "episode-2026-01-01-session-001.json"
    episode_file.write_text(json.dumps(episode, indent=2), encoding="utf-8")

    return episode


# ---------------------------------------------------------------------------
# Episode tests
# ---------------------------------------------------------------------------


class TestGetEpisode:
    """Tests for get_episode function."""

    def test_returns_none_when_not_found(self) -> None:
        result = rm.get_episode("nonexistent-session")
        assert result is None

    def test_returns_episode_when_found(self, sample_episode: dict) -> None:
        result = rm.get_episode("2026-01-01-session-001")
        assert result is not None
        assert result["id"] == "episode-2026-01-01-session-001"
        assert result["outcome"] == "success"

    def test_raises_on_corrupted_file(self) -> None:
        episode_file = rm.EPISODES_PATH / "episode-corrupted.json"
        episode_file.write_text("not valid json{{{", encoding="utf-8")

        with pytest.raises(ValueError, match="corrupted"):
            rm.get_episode("corrupted")


class TestGetEpisodes:
    """Tests for get_episodes function."""

    def test_returns_empty_when_no_episodes(self) -> None:
        result = rm.get_episodes()
        assert result == []

    def test_returns_all_episodes(self, sample_episode: dict) -> None:
        result = rm.get_episodes()
        assert len(result) >= 1

    def test_filters_by_outcome(self, sample_episode: dict) -> None:
        result = rm.get_episodes(outcome="success")
        assert len(result) >= 1
        for ep in result:
            assert ep["outcome"] == "success"

        result = rm.get_episodes(outcome="failure")
        assert len(result) == 0

    def test_filters_by_task_substring(self, sample_episode: dict) -> None:
        result = rm.get_episodes(task="Implement")
        assert len(result) >= 1

        result = rm.get_episodes(task="nonexistent task")
        assert len(result) == 0

    def test_limits_results(self, sample_episode: dict) -> None:
        result = rm.get_episodes(max_results=1)
        assert len(result) <= 1

    def test_validates_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            rm.get_episodes(outcome="invalid")

    def test_skips_corrupted_files(self) -> None:
        bad_file = rm.EPISODES_PATH / "episode-bad.json"
        bad_file.write_text("{{invalid}}", encoding="utf-8")

        result = rm.get_episodes()
        # Should not raise, just skip the bad file
        assert isinstance(result, list)


class TestNewEpisode:
    """Tests for new_episode function."""

    def test_creates_episode_file(self) -> None:
        result = rm.new_episode(
            session_id="test-session-001",
            task="Test task",
            outcome="success",
        )

        assert result["id"] == "episode-test-session-001"
        assert result["outcome"] == "success"

        episode_file = rm.EPISODES_PATH / "episode-test-session-001.json"
        assert episode_file.exists()

    def test_includes_decisions_and_events(self) -> None:
        decisions = [{"id": "d1", "type": "design"}]
        events = [{"type": "start"}]
        lessons = ["lesson1"]
        metrics = {"duration": 30}

        result = rm.new_episode(
            session_id="test-session-002",
            task="Test task",
            outcome="partial",
            decisions=decisions,
            events=events,
            lessons=lessons,
            metrics=metrics,
        )

        assert len(result["decisions"]) == 1
        assert len(result["events"]) == 1
        assert len(result["lessons"]) == 1
        assert result["metrics"]["duration"] == 30

    def test_rejects_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            rm.new_episode(
                session_id="test",
                task="Test",
                outcome="invalid",
            )

    def test_skip_validation_bypasses_schema(self) -> None:
        result = rm.new_episode(
            session_id="test-skip",
            task="Test",
            outcome="success",
            skip_validation=True,
        )
        assert result["id"] == "episode-test-skip"


class TestGetDecisionSequence:
    """Tests for get_decision_sequence function."""

    def test_returns_empty_for_missing_episode(self) -> None:
        result = rm.get_decision_sequence("episode-nonexistent")
        assert result == []

    def test_returns_decisions_sorted_by_timestamp(
        self, sample_episode: dict
    ) -> None:
        result = rm.get_decision_sequence("episode-2026-01-01-session-001")
        assert len(result) == 2
        # d002 has earlier timestamp than d001
        assert result[0]["id"] == "d002"
        assert result[1]["id"] == "d001"


# ---------------------------------------------------------------------------
# Causal graph tests
# ---------------------------------------------------------------------------


class TestAddCausalNode:
    """Tests for add_causal_node function."""

    def test_creates_new_node(self) -> None:
        node = rm.add_causal_node(
            node_type="decision",
            label="Choose routing strategy",
            episode_id="episode-001",
        )

        assert node["id"] == "n001"
        assert node["type"] == "decision"
        assert node["label"] == "Choose routing strategy"
        assert node["frequency"] == 1
        assert "episode-001" in node["episodes"]

    def test_increments_frequency_for_existing_node(self) -> None:
        rm.add_causal_node(
            node_type="decision",
            label="Same label",
            episode_id="ep-001",
        )
        node = rm.add_causal_node(
            node_type="decision",
            label="Same label",
            episode_id="ep-002",
        )

        assert node["frequency"] == 2
        assert "ep-001" in node["episodes"]
        assert "ep-002" in node["episodes"]

    def test_creates_node_without_episode(self) -> None:
        node = rm.add_causal_node(
            node_type="event",
            label="Generic event",
        )
        assert node["episodes"] == []

    def test_rejects_invalid_node_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid node type"):
            rm.add_causal_node(node_type="invalid", label="test")

    def test_increments_node_ids(self) -> None:
        n1 = rm.add_causal_node(node_type="decision", label="First")
        n2 = rm.add_causal_node(node_type="event", label="Second")
        assert n1["id"] == "n001"
        assert n2["id"] == "n002"


class TestAddCausalEdge:
    """Tests for add_causal_edge function."""

    def test_creates_new_edge(self) -> None:
        edge = rm.add_causal_edge(
            source_id="n001",
            target_id="n002",
            edge_type="causes",
            weight=0.9,
        )

        assert edge["source"] == "n001"
        assert edge["target"] == "n002"
        assert edge["type"] == "causes"
        assert edge["weight"] == 0.9
        assert edge["evidence_count"] == 1

    def test_updates_existing_edge_weight(self) -> None:
        rm.add_causal_edge("n001", "n002", "causes", weight=0.8)
        edge = rm.add_causal_edge("n001", "n002", "causes", weight=0.6)

        assert edge["evidence_count"] == 2
        # Running average: (0.8 * 1 + 0.6) / 2 = 0.7
        assert abs(edge["weight"] - 0.7) < 0.01

    def test_rejects_invalid_edge_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid edge type"):
            rm.add_causal_edge("n001", "n002", "invalid")

    def test_rejects_out_of_range_weight(self) -> None:
        with pytest.raises(ValueError, match="Weight must be"):
            rm.add_causal_edge("n001", "n002", "causes", weight=1.5)


class TestGetCausalPath:
    """Tests for get_causal_path function."""

    def test_returns_not_found_for_missing_nodes(self) -> None:
        result = rm.get_causal_path("nonexistent", "also nonexistent")
        assert result["found"] is False
        assert result["error"] == "Node not found"

    def test_finds_direct_path(self) -> None:
        rm.add_causal_node(node_type="decision", label="Node A")
        rm.add_causal_node(node_type="outcome", label="Node B")
        rm.add_causal_edge("n001", "n002", "causes")

        result = rm.get_causal_path("Node A", "Node B")
        assert result["found"] is True
        assert result["depth"] == 1

    def test_finds_multi_hop_path(self) -> None:
        rm.add_causal_node(node_type="decision", label="Start")
        rm.add_causal_node(node_type="event", label="Middle")
        rm.add_causal_node(node_type="outcome", label="End")
        rm.add_causal_edge("n001", "n002", "causes")
        rm.add_causal_edge("n002", "n003", "enables")

        result = rm.get_causal_path("Start", "End")
        assert result["found"] is True
        assert result["depth"] == 2

    def test_respects_max_depth(self) -> None:
        rm.add_causal_node(node_type="decision", label="Far Start")
        rm.add_causal_node(node_type="event", label="Far Middle")
        rm.add_causal_node(node_type="outcome", label="Far End")
        rm.add_causal_edge("n001", "n002", "causes")
        rm.add_causal_edge("n002", "n003", "causes")

        result = rm.get_causal_path("Far Start", "Far End", max_depth=1)
        assert result["found"] is False


# ---------------------------------------------------------------------------
# Pattern tests
# ---------------------------------------------------------------------------


class TestAddPattern:
    """Tests for add_pattern function."""

    def test_creates_new_pattern(self) -> None:
        pattern = rm.add_pattern(
            name="TDD First",
            trigger="New feature request",
            action="Write failing test before code",
            description="Test-driven development",
            success_rate=0.9,
        )

        assert pattern["id"] == "p001"
        assert pattern["name"] == "TDD First"
        assert pattern["occurrences"] == 1
        assert pattern["success_rate"] == 0.9

    def test_increments_existing_pattern(self) -> None:
        rm.add_pattern(
            name="Same Pattern",
            trigger="trigger",
            action="action",
            success_rate=0.8,
        )
        pattern = rm.add_pattern(
            name="Same Pattern",
            trigger="trigger",
            action="action",
            success_rate=0.6,
        )

        assert pattern["occurrences"] == 2
        # Running average: (0.8 * 1 + 0.6) / 2 = 0.7
        assert abs(pattern["success_rate"] - 0.7) < 0.01

    def test_rejects_out_of_range_success_rate(self) -> None:
        with pytest.raises(ValueError, match="success_rate must be"):
            rm.add_pattern(
                name="test", trigger="t", action="a", success_rate=1.5
            )


class TestGetPatterns:
    """Tests for get_patterns function."""

    def test_returns_empty_when_no_patterns(self) -> None:
        result = rm.get_patterns()
        assert result == []

    def test_filters_by_min_success_rate(self) -> None:
        rm.add_pattern(name="Good", trigger="t", action="a", success_rate=0.9)
        rm.add_pattern(name="Bad", trigger="t", action="a", success_rate=0.2)

        result = rm.get_patterns(min_success_rate=0.5)
        assert len(result) == 1
        assert result[0]["name"] == "Good"

    def test_filters_by_min_occurrences(self) -> None:
        rm.add_pattern(name="Once", trigger="t", action="a")
        rm.add_pattern(name="Twice", trigger="t", action="a")
        rm.add_pattern(name="Twice", trigger="t", action="a")

        result = rm.get_patterns(min_occurrences=2)
        assert len(result) == 1
        assert result[0]["name"] == "Twice"

    def test_sorted_by_success_rate_descending(self) -> None:
        rm.add_pattern(name="Low", trigger="t", action="a", success_rate=0.3)
        rm.add_pattern(name="High", trigger="t", action="a", success_rate=0.9)
        rm.add_pattern(name="Mid", trigger="t", action="a", success_rate=0.6)

        result = rm.get_patterns()
        rates = [p["success_rate"] for p in result]
        assert rates == sorted(rates, reverse=True)


class TestGetAntiPatterns:
    """Tests for get_anti_patterns function."""

    def test_returns_empty_when_no_anti_patterns(self) -> None:
        result = rm.get_anti_patterns()
        assert result == []

    def test_finds_low_success_rate_patterns(self) -> None:
        rm.add_pattern(name="Bad", trigger="t", action="a", success_rate=0.1)
        rm.add_pattern(name="Bad", trigger="t", action="a", success_rate=0.1)
        rm.add_pattern(name="Good", trigger="t", action="a", success_rate=0.9)

        result = rm.get_anti_patterns(max_success_rate=0.3)
        assert len(result) == 1
        assert result[0]["name"] == "Bad"

    def test_requires_min_two_occurrences(self) -> None:
        rm.add_pattern(name="Once", trigger="t", action="a", success_rate=0.1)

        result = rm.get_anti_patterns()
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------


class TestGetReflexionMemoryStatus:
    """Tests for get_reflexion_memory_status function."""

    def test_returns_status_structure(self) -> None:
        status = rm.get_reflexion_memory_status()
        assert "Episodes" in status
        assert "CausalGraph" in status
        assert "Configuration" in status

    def test_counts_episode_files(self, sample_episode: dict) -> None:
        status = rm.get_reflexion_memory_status()
        assert status["Episodes"]["Count"] >= 1

    def test_reports_causal_graph_version(self) -> None:
        status = rm.get_reflexion_memory_status()
        assert status["CausalGraph"]["Version"] == "1.0"
