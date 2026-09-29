#!/usr/bin/env python3
"""Tests for reflexion_memory module.

Coverage target: all public functions for episodes.

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
    schemas_path = tmp_path / "schemas"

    episodes_path.mkdir()
    schemas_path.mkdir()

    # Copy the shipped schemas rather than inventing stubs. Hand-written
    # stubs here declared `nodes` as a bare array, so every node and pattern
    # this module writes went unvalidated and the suite could not see the
    # drift that #3356 is about.
    shipped = Path(rm.__file__).resolve().parent.parent / "resources" / "schemas"
    for name in ("episode.schema.json",):
        (schemas_path / name).write_text(
            (shipped / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    # Patch module-level paths
    with patch.object(rm, "EPISODES_PATH", episodes_path), patch.object(
        rm, "SCHEMAS_PATH", schemas_path
    ), patch.object(
        rm, "EPISODE_SCHEMA_FILE", schemas_path / "episode.schema.json"
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
        decisions = [
            {
                "id": "d001",
                "type": "design",
                "context": "Two writers disagreed on node identity.",
                "chosen": "Derive ids from content.",
                "outcome": "success",
                "timestamp": "2026-01-01T12:00:00+00:00",
            }
        ]
        events = [
            {
                "id": "e001",
                "type": "milestone",
                "content": "Schema and writer agree.",
                "timestamp": "2026-01-01T12:00:00+00:00",
            }
        ]
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
# Status tests
# ---------------------------------------------------------------------------


class TestGetReflexionMemoryStatus:
    """Tests for get_reflexion_memory_status function."""

    def test_returns_status_structure(self) -> None:
        status = rm.get_reflexion_memory_status()
        assert "Episodes" in status
        assert "Configuration" in status

    def test_counts_episode_files(self, sample_episode: dict) -> None:
        status = rm.get_reflexion_memory_status()
        assert status["Episodes"]["Count"] >= 1
