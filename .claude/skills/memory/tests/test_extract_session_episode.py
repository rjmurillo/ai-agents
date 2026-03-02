#!/usr/bin/env python3
"""Tests for extract_session_episode.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..scripts.extract_session_episode import (
    get_decision_type,
    get_session_id_from_path,
    get_session_outcome,
    main,
    parse_decisions,
    parse_events,
    parse_lessons,
    parse_metrics,
    parse_session_metadata,
)

SAMPLE_SESSION_LOG = """\
# Session 2026-01-15: Implement feature X

**Date**: 2026-01-15T10:00:00+00:00
**Status**: Complete

## Objectives

- Implement the new search module
- Add unit tests

## Deliverables

- search_module.py
- test_search.py

## Decisions

- **Architecture**: Chose lexical search over semantic for speed
- **Testing**: Selected pytest framework

## Work Log

- committed as abc1234 feat(search): add lexical search
- The test run: 5 tests pass
- Fixed error in parsing logic

## Lessons Learned

- Always validate input before processing
- Keep functions under 30 lines

## Metrics

- Duration: 45 minutes
- 3 files changed
"""


class TestGetSessionIdFromPath:
    """Tests for session ID extraction."""

    def test_standard_format(self) -> None:
        path = Path("2026-01-15-session-001.md")
        assert get_session_id_from_path(path) == "2026-01-15-session-001"

    def test_session_only_format(self) -> None:
        path = Path("session-042.md")
        assert get_session_id_from_path(path) == "session-042"

    def test_json_extension(self) -> None:
        path = Path("2026-01-15-session-001.json")
        assert get_session_id_from_path(path) == "2026-01-15-session-001"

    def test_fallback_to_stem(self) -> None:
        path = Path("random-filename.md")
        assert get_session_id_from_path(path) == "random-filename"


class TestParseSessionMetadata:
    """Tests for metadata extraction."""

    def test_extracts_title(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metadata = parse_session_metadata(lines)
        assert "Session 2026-01-15" in metadata["title"]

    def test_extracts_date(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metadata = parse_session_metadata(lines)
        assert "2026-01-15" in metadata["date"]

    def test_extracts_status(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metadata = parse_session_metadata(lines)
        assert metadata["status"] == "Complete"

    def test_extracts_objectives(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metadata = parse_session_metadata(lines)
        assert len(metadata["objectives"]) == 2
        assert "search module" in metadata["objectives"][0]

    def test_extracts_deliverables(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metadata = parse_session_metadata(lines)
        assert len(metadata["deliverables"]) == 2

    def test_empty_input(self) -> None:
        metadata = parse_session_metadata([])
        assert metadata["title"] == ""
        assert metadata["objectives"] == []


class TestGetDecisionType:
    """Tests for decision type classification."""

    def test_design(self) -> None:
        assert get_decision_type("Changed the architecture layout") == "design"

    def test_test(self) -> None:
        assert get_decision_type("Added Pester test coverage") == "test"

    def test_recovery(self) -> None:
        assert get_decision_type("Added retry with fallback") == "recovery"

    def test_routing(self) -> None:
        assert get_decision_type("Delegate to agent for handoff") == "routing"

    def test_implementation_default(self) -> None:
        assert get_decision_type("Created new module") == "implementation"


class TestParseDecisions:
    """Tests for decision extraction."""

    def test_extracts_decisions_from_section(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        decisions = parse_decisions(lines)
        assert len(decisions) >= 2

    def test_decision_has_required_fields(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        decisions = parse_decisions(lines)
        if decisions:
            d = decisions[0]
            assert "id" in d
            assert "timestamp" in d
            assert "type" in d
            assert "chosen" in d

    def test_empty_input(self) -> None:
        decisions = parse_decisions([])
        assert decisions == []

    def test_decision_id_format(self) -> None:
        lines = ["**Decision**: Use Python for scripts"]
        decisions = parse_decisions(lines)
        if decisions:
            assert decisions[0]["id"].startswith("d")


class TestParseEvents:
    """Tests for event extraction."""

    def test_extracts_commit_events(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        events = parse_events(lines)
        commit_events = [e for e in events if e["type"] == "commit"]
        assert len(commit_events) >= 1

    def test_extracts_error_events(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        events = parse_events(lines)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1

    def test_extracts_test_events(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        events = parse_events(lines)
        test_events = [e for e in events if e["type"] == "test"]
        assert len(test_events) >= 1

    def test_empty_input(self) -> None:
        events = parse_events([])
        assert events == []


class TestParseLessons:
    """Tests for lesson extraction."""

    def test_extracts_lessons_from_section(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        lessons = parse_lessons(lines)
        assert len(lessons) >= 2

    def test_deduplicates_lessons(self) -> None:
        lines = [
            "## Lessons Learned",
            "- lesson learned from session",
            "- lesson learned from session",
        ]
        lessons = parse_lessons(lines)
        assert len(lessons) == 1

    def test_empty_input(self) -> None:
        lessons = parse_lessons([])
        assert lessons == []


class TestParseMetrics:
    """Tests for metrics extraction."""

    def test_extracts_duration(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metrics = parse_metrics(lines)
        assert metrics["duration_minutes"] == 45

    def test_extracts_files_changed(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metrics = parse_metrics(lines)
        assert metrics["files_changed"] == 3

    def test_counts_errors(self) -> None:
        lines = SAMPLE_SESSION_LOG.splitlines()
        metrics = parse_metrics(lines)
        assert metrics["errors"] >= 1

    def test_empty_input(self) -> None:
        metrics = parse_metrics([])
        assert metrics["duration_minutes"] == 0
        assert metrics["commits"] == 0


class TestGetSessionOutcome:
    """Tests for session outcome determination."""

    def test_complete_status(self) -> None:
        metadata = {"status": "Complete"}
        assert get_session_outcome(metadata, []) == "success"

    def test_partial_status(self) -> None:
        metadata = {"status": "In Progress"}
        assert get_session_outcome(metadata, []) == "partial"

    def test_failure_status(self) -> None:
        metadata = {"status": "Failed"}
        assert get_session_outcome(metadata, []) == "failure"

    def test_infer_from_events_success(self) -> None:
        metadata = {"status": ""}
        events = [
            {"type": "milestone"},
            {"type": "milestone"},
            {"type": "error"},
        ]
        assert get_session_outcome(metadata, events) == "success"

    def test_infer_from_events_failure(self) -> None:
        metadata = {"status": ""}
        events = [
            {"type": "error"},
            {"type": "error"},
            {"type": "milestone"},
        ]
        assert get_session_outcome(metadata, events) == "failure"

    def test_empty_defaults_partial(self) -> None:
        metadata = {"status": ""}
        assert get_session_outcome(metadata, []) == "partial"

    def test_none_status(self) -> None:
        metadata = {"status": None}
        assert get_session_outcome(metadata, []) == "partial"


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_extract_episode(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        session_file = tmp_path / "2026-01-15-session-001.md"
        session_file.write_text(SAMPLE_SESSION_LOG)

        output_dir = tmp_path / "episodes"

        result = main([
            str(session_file),
            "--output-path", str(output_dir),
        ])
        assert result == 0

        episode_file = output_dir / "episode-2026-01-15-session-001.json"
        assert episode_file.exists()

        episode = json.loads(episode_file.read_text())
        assert episode["id"] == "episode-2026-01-15-session-001"
        assert episode["outcome"] == "success"
        assert len(episode["decisions"]) >= 1
        assert len(episode["events"]) >= 1

    def test_missing_file_returns_1(self, tmp_path: Path) -> None:
        result = main([str(tmp_path / "nonexistent.md")])
        assert result == 1

    def test_force_overwrite(self, tmp_path: Path) -> None:
        session_file = tmp_path / "2026-01-15-session-001.md"
        session_file.write_text(SAMPLE_SESSION_LOG)

        output_dir = tmp_path / "episodes"
        output_dir.mkdir()
        episode_file = output_dir / "episode-2026-01-15-session-001.json"
        episode_file.write_text("{}")

        result = main([
            str(session_file),
            "--output-path", str(output_dir),
            "--force",
        ])
        assert result == 0

    def test_no_overwrite_without_force(self, tmp_path: Path) -> None:
        session_file = tmp_path / "2026-01-15-session-001.md"
        session_file.write_text(SAMPLE_SESSION_LOG)

        output_dir = tmp_path / "episodes"
        output_dir.mkdir()
        episode_file = output_dir / "episode-2026-01-15-session-001.json"
        episode_file.write_text("{}")

        result = main([
            str(session_file),
            "--output-path", str(output_dir),
        ])
        assert result == 1

    def test_stdout_contains_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        session_file = tmp_path / "session-001.md"
        session_file.write_text("# Simple session\n**Status**: Done\n")

        output_dir = tmp_path / "episodes"
        result = main([
            str(session_file),
            "--output-path", str(output_dir),
        ])
        assert result == 0

        captured = capsys.readouterr()
        episode = json.loads(captured.out)
        assert "id" in episode
        assert "session" in episode
