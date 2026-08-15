#!/usr/bin/env python3
"""Tests for extract_session_episode.py."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ..scripts.extract_session_episode import (
    _chronological,
    _commit_datetime,
    _link_sequential_events,
    _prose_sha_predates_session,
    extract_from_json,
    get_decision_type,
    get_session_id_from_path,
    get_session_outcome,
    json_events,
    json_metrics,
    json_outcome,
    looks_like_json_session,
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

    def test_extract_episode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_preserve_merges_existing_episode(self, tmp_path: Path) -> None:
        """--preserve must merge over an existing episode without dropping
        curated content. Refs issue #2193: pre-commit hook ran --force
        unconditionally and silently overwrote richer existing episodes.
        """
        session_file = tmp_path / "2026-01-15-session-001.md"
        session_file.write_text(SAMPLE_SESSION_LOG)

        output_dir = tmp_path / "episodes"
        output_dir.mkdir()
        episode_file = output_dir / "episode-2026-01-15-session-001.json"
        existing = {
            "id": "episode-2026-01-15-session-001",
            "timestamp": "2026-01-15T00:00:00+00:00",
            "task": "Curated task summary that fresh extraction lacks",
            "outcome": "success",
            "decisions": [
                {
                    "decision": "Curated decision survives regeneration",
                    "rationale": "Reviewed by maintainer",
                }
            ],
            "events": [],
            "lessons": ["Curated lesson"],
            "metrics": {"errors": 0, "tests_passed": 5, "files_changed": 0},
        }
        episode_file.write_text(json.dumps(existing, indent=2) + "\n")

        result = main([
            str(session_file),
            "--output-path", str(output_dir),
            "--preserve",
        ])
        assert result == 0

        merged = json.loads(episode_file.read_text())
        decision_texts = [d.get("decision") for d in merged["decisions"]]
        assert "Curated decision survives regeneration" in decision_texts, (
            "--preserve must union curated decisions with fresh extraction"
        )
        assert "Curated lesson" in merged["lessons"], (
            "--preserve must union curated lessons with fresh extraction"
        )
        assert len(merged["decisions"]) > 1, (
            "--preserve must keep both curated and freshly extracted decisions"
        )

    def test_force_and_preserve_are_mutually_exclusive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        session_file = tmp_path / "2026-01-15-session-002.md"
        session_file.write_text(SAMPLE_SESSION_LOG)
        with pytest.raises(SystemExit):
            main([
                str(session_file),
                "--output-path", str(tmp_path / "episodes"),
                "--force",
                "--preserve",
            ])

    def test_stdout_contains_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def _gate(complete: bool) -> dict[str, object]:
    return {"level": "MUST", "Complete": complete, "Evidence": "x"}


def _json_log(work_log: list[dict[str, Any]], *, end_complete: bool = True) -> dict[str, Any]:
    gate = _gate(end_complete)
    return {
        "session": {
            "number": 1,
            "date": "2026-05-31",
            "branch": "feat/x",
            "startingCommit": "aaaaaaa",
            "objective": "Do the thing",
        },
        "protocolCompliance": {
            "sessionStart": {},
            "sessionEnd": {
                "checklistComplete": gate,
                "changesCommitted": gate,
                "validationPassed": gate,
            },
        },
        "workLog": work_log,
        "endingCommit": "bbbbbbb1234",
        "nextSteps": [],
    }


def _real_3459_log() -> dict[str, Any]:
    return {
        "session": {
            "number": 3459,
            "date": "2026-07-27",
            "branch": "fix/skill-md-templates-portability",
            "startingCommit": "98caa0e54d",
            "objective": (
                "Close the templates/ gap in check_skill_md_portability.py so shipped "
                "SKILL.md files cannot point at generator inputs that never ship with the plugin"
            ),
        },
        "protocolCompliance": {
            "sessionStart": {},
            "sessionEnd": {
                "checklistComplete": _gate(True),
                "changesCommitted": _gate(True),
                "validationPassed": _gate(True),
            },
        },
        "workLog": [
            {
                "phase": "Measure the gap",
                "actions": [
                    "Read UPSTREAM_PATTERNS in scripts/validation/check_skill_md_portability.py",
                    "Checked each skill for a vendor-portability marker",
                ],
                "outcome": (
                    "Confirmed a real gap rather than a baseline artifact. Filed issue #3459 "
                    "with the evidence before writing code"
                ),
            },
            {
                "phase": "Extend the patterns and prove they are load-bearing",
                "actions": ["Added two patterns scoped to the second segment"],
                "outcome": (
                    "Patterns verified to fire on the true positives and stay silent on "
                    "the four negative shapes"
                ),
            },
            {
                "phase": "Declare the three offenders",
                "actions": ["Regenerated the Copilot mirror"],
                "outcome": (
                    "Validator stays at baseline 0 with the wider patterns in force, so "
                    "the ratchet tightens without grandfathering anything"
                ),
            },
            {
                "phase": "Adversarial review remediation",
                "actions": ["Verified the regex through the validator itself"],
                "outcome": (
                    "Regex verified through the validator itself, not only in isolation. "
                    "55 tests pass, ruff clean, ratchet reports zero refs across zero files."
                ),
            },
            {
                "phase": "Remove bundled memory artifacts per review feedback",
                "actions": ["Hook regeneration is by design"],
                "outcome": (
                    "Hooks regenerate memory artifacts from the session file on every commit; "
                    "files remain as auto-generated derivatives of this session log"
                ),
            },
        ],
        "endingCommit": "ac9a29da8",
        "nextSteps": [],
    }


class TestLooksLikeJsonSession:
    def test_detects_json_session(self):
        content = json.dumps(_json_log([{"task": "t", "outcome": "o", "evidence": "e"}]))
        assert looks_like_json_session(content) is not None

    def test_markdown_is_none(self):
        assert looks_like_json_session("# Heading\n**Status**: Done\n") is None

    def test_unrelated_json_is_none(self):
        assert looks_like_json_session('{"foo": 1}') is None


class TestJsonOutcome:
    def test_all_gates_complete_is_success(self):
        data = _json_log([{"task": "t", "outcome": "shipped", "evidence": "20 passed"}])
        assert json_outcome(data) == "success"

    def test_incomplete_gates_is_partial(self):
        data = _json_log([{"task": "t", "outcome": "wip"}], end_complete=False)
        assert json_outcome(data) == "partial"

    def test_counted_failure_with_incomplete_gates_is_failure(self):
        data = _json_log([{"task": "t", "outcome": "3 failed"}], end_complete=False)
        assert json_outcome(data) == "failure"

    def test_regression_2036_substring_fail_does_not_force_failure(self):
        # The exact #2036 corruption: prose "test still fails" and "0 errors"
        # must NOT be read as failures when the session-end gates are complete.
        data = _json_log([
            {"action": "compress", "outcome": "compression insufficient; test still fails"},
            {"action": "verify", "outcome": "AGENTS.md 2791 B; markdownlint 0 errors"},
        ])
        assert json_outcome(data) == "success"


class TestJsonEvents:
    def test_milestone_from_task(self):
        events = json_events(
            _json_log([{"task": "Build X", "outcome": "done"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert any(e["type"] == "milestone" and e["content"] == "Build X" for e in events)

    def test_milestone_from_action_legacy_schema(self):
        events = json_events(
            _json_log([{"action": "Refactor Y", "outcome": "done"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert any(e["type"] == "milestone" and e["content"] == "Refactor Y" for e in events)

    def test_test_event_from_passed_count(self):
        events = json_events(
            _json_log([{"task": "t", "outcome": "ok", "evidence": "24 passed"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert any(e["type"] == "test" for e in events)

    def test_no_error_event_from_prose_fail(self):
        events = json_events(
            _json_log([{"action": "x", "outcome": "test still fails; 0 errors"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert not any(e["type"] == "error" for e in events)

    def test_error_event_from_counted_failure(self):
        events = json_events(
            _json_log([{"task": "t", "outcome": "2 failed"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert any(e["type"] == "error" for e in events)

    def test_commit_event_from_ending_commit(self):
        events = json_events(
            _json_log([{"task": "t", "outcome": "o"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert any(e["type"] == "commit" for e in events)

    def test_milestone_from_string_entry(self):
        # Some logs store workLog as a list of bare strings (e.g. session 1766).
        events = json_events(
            _json_log(["Reviewed PR 1766: 5 unresolved threads"]),
            "2026-05-31T00:00:00+00:00",
        )
        assert any(e["type"] == "milestone" and "Reviewed PR 1766" in e["content"] for e in events)


class TestCausalEventLinks:
    def test_real_3459_pre_code_milestone_is_not_caused_by_final_commit(self):
        bundle = extract_from_json(_real_3459_log())
        _link_sequential_events(bundle["events"])

        commit = next(e for e in bundle["events"] if e["type"] == "commit")
        pre_code = next(e for e in bundle["events"] if "Filed issue #3459" in e["content"])
        assert commit["content"] == "Commit: ac9a29da8"
        assert pre_code["caused_by"] == []
        assert commit["leads_to"] != [pre_code["id"]]

    def test_commit_is_not_caused_by_later_review_milestone(self):
        bundle = extract_from_json(_json_log([
            {
                "phase": "Review",
                "actions": ["Addressed PR review feedback"],
                "outcome": "PR review round complete",
            }
        ]))
        _link_sequential_events(bundle["events"])

        commit = next(e for e in bundle["events"] if e["type"] == "commit")
        review = next(e for e in bundle["events"] if e["type"] == "milestone")
        assert commit["caused_by"] == []
        assert review["leads_to"] != [commit["id"]]

    def test_pre_and_post_code_milestones_in_same_log_use_observed_order(self):
        bundle = extract_from_json(_json_log([
            {
                "timestamp": "2026-05-30T23:00:00+00:00",
                "phase": "Reproduce",
                "actions": ["Filed the issue before code changed"],
                "outcome": "Filed issue #3464 before writing code",
            },
            {
                "timestamp": "2026-05-31T01:00:00+00:00",
                "phase": "Review",
                "actions": ["Reviewed the completed branch"],
                "outcome": "PR review round complete",
            },
        ]))
        _link_sequential_events(bundle["events"])

        commit = next(e for e in bundle["events"] if e["type"] == "commit")
        pre_code = next(e for e in bundle["events"] if "before writing code" in e["content"])
        post_code = next(e for e in bundle["events"] if "review round" in e["content"])
        assert pre_code["caused_by"] == []
        assert pre_code["leads_to"] == [commit["id"]]
        assert commit["caused_by"] == [pre_code["id"]]
        assert commit["leads_to"] == [post_code["id"]]
        assert post_code["caused_by"] == [commit["id"]]

    def test_rank_only_timestamp_ties_do_not_emit_causal_edges(self):
        events = [
            {
                "id": "e001",
                "timestamp": "2026-07-27T00:00:00+00:00",
                "type": "milestone",
                "content": "Reported the result",
                "caused_by": [],
                "leads_to": [],
            },
            {
                "id": "e002",
                "timestamp": "2026-07-27T00:00:00+00:00",
                "type": "commit",
                "content": "Commit: abc1234",
                "caused_by": [],
                "leads_to": [],
            },
            {
                "id": "e003",
                "timestamp": "2026-07-27T00:00:00+00:00",
                "type": "test",
                "content": "10 passed",
                "caused_by": [],
                "leads_to": [],
            },
        ]

        _link_sequential_events(events)

        by_id = {e["id"]: e for e in events}
        assert by_id["e001"]["caused_by"] == []
        assert by_id["e001"]["leads_to"] == []
        assert by_id["e002"]["caused_by"] == []
        assert by_id["e002"]["leads_to"] == ["e003"]
        assert by_id["e003"]["caused_by"] == ["e002"]
        assert by_id["e003"]["leads_to"] == []

    def test_cli_returns_zero_and_keeps_real_3459_pre_code_edge_sparse(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        session_log = tmp_path / "2026-07-27-session-3459-templates-portability.json"
        session_log.write_text(json.dumps(_real_3459_log()), encoding="utf-8")
        output_dir = tmp_path / "episodes"

        rc = main([str(session_log), "--output-path", str(output_dir)])

        assert rc == 0
        episode = json.loads(capsys.readouterr().out)
        commit = next(e for e in episode["events"] if e["type"] == "commit")
        pre_code = next(e for e in episode["events"] if "Filed issue #3459" in e["content"])
        assert pre_code["caused_by"] == []
        assert commit["leads_to"] != [pre_code["id"]]


class TestStringWorkLog:
    def test_outcome_success_when_gates_complete(self):
        assert json_outcome(_json_log(["did a thing", "did another"])) == "success"

    def test_metrics_do_not_crash(self):
        m = json_metrics(_json_log(["touched 3 files", "ran tests"]))
        assert m["files_changed"] == 3

    def test_main_on_string_worklog(self, tmp_path, capsys):
        log = tmp_path / "2026-05-31-session-9002.json"
        log.write_text(json.dumps(_json_log(["did a thing", "shipped it"])), encoding="utf-8")
        rc = main([str(log), "--output-path", str(tmp_path / "ep")])
        assert rc == 0
        episode = json.loads(capsys.readouterr().out)
        assert episode["outcome"] == "success"
        assert sum(1 for e in episode["events"] if e["type"] == "milestone") == 2


class TestJsonMetrics:
    def test_errors_zero_when_no_counted_failure(self):
        m = json_metrics(_json_log([{"action": "x", "outcome": "test still fails; 0 errors"}]))
        assert m["errors"] == 0

    def test_files_changed_parsed(self):
        m = json_metrics(_json_log([{"task": "t", "outcome": "ok", "evidence": "7 files changed"}]))
        assert m["files_changed"] == 7


class TestJsonMetricsDuration:
    """Duration must read the timestamp under either spelling workLog entries use.

    Issue #3972 reported duration_minutes stuck at 0. The stated cause was the
    regex line-scanning in ``parse_metrics``, but that function is the markdown
    fallback and never runs for a JSON session log. The live path is
    ``json_metrics``, and it read zero because ``_duration_from_worklogs``
    accepted only the key ``time`` while the majority spelling in the tree is
    ``timestamp``. Measured over the 40 most recent session logs: 14 use
    ``timestamp``, 9 use ``time``, 17 carry neither.
    """

    def test_duration_from_time_key(self):
        m = json_metrics(
            _json_log(
                [
                    {"time": "2026-05-31T10:00:00+00:00", "action": "start"},
                    {"time": "2026-05-31T10:45:00+00:00", "action": "end"},
                ]
            )
        )
        assert m["duration_minutes"] == 45

    def test_duration_from_timestamp_key(self):
        """The #3972 regression: this shape read 0 before the fix."""
        m = json_metrics(
            _json_log(
                [
                    {"timestamp": "2026-05-31T10:00:00+00:00", "action": "start"},
                    {"timestamp": "2026-05-31T12:30:00+00:00", "action": "end"},
                ]
            )
        )
        assert m["duration_minutes"] == 150

    def test_duration_from_mixed_spellings(self):
        m = json_metrics(
            _json_log(
                [
                    {"time": "2026-05-31T10:00:00+00:00", "action": "start"},
                    {"timestamp": "2026-05-31T10:20:00+00:00", "action": "end"},
                ]
            )
        )
        assert m["duration_minutes"] == 20

    def test_duration_uses_span_not_first_to_last_entry(self):
        """Entries are not guaranteed chronological, so span must be max minus min."""
        m = json_metrics(
            _json_log(
                [
                    {"time": "2026-05-31T11:00:00+00:00", "action": "middle"},
                    {"time": "2026-05-31T12:00:00+00:00", "action": "latest"},
                    {"time": "2026-05-31T10:00:00+00:00", "action": "earliest"},
                ]
            )
        )
        assert m["duration_minutes"] == 120

    def test_duration_none_when_single_timestamp(self):
        m = json_metrics(_json_log([{"time": "2026-05-31T10:00:00+00:00", "action": "only"}]))
        assert m["duration_minutes"] is None

    def test_duration_none_when_no_timestamps(self):
        """Unmeasured must stay distinguishable from a measured zero."""
        m = json_metrics(_json_log([{"action": "x"}, {"action": "y"}]))
        assert m["duration_minutes"] is None

    def test_duration_none_when_timestamps_unparseable(self):
        m = json_metrics(
            _json_log([{"time": "not-a-date"}, {"timestamp": "also-not-a-date"}])
        )
        assert m["duration_minutes"] is None

    def test_duration_falls_back_to_metrics_block_text(self):
        log = _json_log([{"action": "x"}])
        log["metrics"] = {"duration": "~20 minutes"}
        assert json_metrics(log)["duration_minutes"] == 20

    def test_duration_prefers_worklogs_over_metrics_block(self):
        log = _json_log(
            [
                {"time": "2026-05-31T10:00:00+00:00"},
                {"time": "2026-05-31T10:05:00+00:00"},
            ]
        )
        log["metrics"] = {"duration": "999 minutes"}
        assert json_metrics(log)["duration_minutes"] == 5

    def test_duration_zero_when_timestamps_identical(self):
        """A real measured zero stays 0, not None. The two states are different."""
        m = json_metrics(
            _json_log(
                [
                    {"time": "2026-05-31T10:00:00+00:00"},
                    {"time": "2026-05-31T10:00:00+00:00"},
                ]
            )
        )
        assert m["duration_minutes"] == 0


class TestJsonMetricsToolCalls:
    """tool_calls must be null when unrecorded, not zero.

    Modern session logs carry no machine-readable tool count. Emitting 0 made an
    unpopulated field indistinguishable from a session that really made no tool
    calls, and 0 reads as "nothing happened here" (issue #3972).
    """

    def test_tool_calls_none_when_metrics_block_absent(self):
        assert json_metrics(_json_log([{"action": "x"}]))["tool_calls"] is None

    def test_tool_calls_none_when_key_absent(self):
        log = _json_log([{"action": "x"}])
        log["metrics"] = {"duration": "5 minutes"}
        assert json_metrics(log)["tool_calls"] is None

    def test_tool_calls_int_when_recorded(self):
        log = _json_log([{"action": "x"}])
        log["metrics"] = {"toolCalls": 42}
        assert json_metrics(log)["tool_calls"] == 42

    def test_tool_calls_zero_preserved_when_explicitly_recorded(self):
        """An explicit 0 is a measurement and must survive as 0, not become None."""
        log = _json_log([{"action": "x"}])
        log["metrics"] = {"toolCalls": 0}
        assert json_metrics(log)["tool_calls"] == 0


class TestEpisodeSchemaAcceptsUnmeasuredMetrics:
    def test_schema_allows_null_duration_and_tool_calls(self):
        schema_path = (
            Path(__file__).resolve().parents[1] / "resources" / "schemas" / "episode.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        metrics_props = schema["properties"]["metrics"]["properties"]
        assert "null" in metrics_props["duration_minutes"]["type"]
        assert "null" in metrics_props["tool_calls"]["type"]

    def test_schema_still_rejects_a_string_duration(self):
        schema_path = (
            Path(__file__).resolve().parents[1] / "resources" / "schemas" / "episode.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "string" not in schema["properties"]["metrics"]["properties"]["duration_minutes"][
            "type"
        ]


class TestExtractFromJsonEndToEnd:
    def test_bundle_shape(self):
        bundle = extract_from_json(
            _json_log([{"task": "Ship it", "outcome": "done", "evidence": "20 passed"}])
        )
        assert bundle["outcome"] == "success"
        assert bundle["task"] == "Do the thing"
        assert bundle["timestamp"].startswith("2026-05-31")
        assert bundle["lessons"] == []

    def test_main_on_json_log(self, tmp_path, capsys):
        log = tmp_path / "2026-05-31-session-9001.json"
        log.write_text(
            json.dumps(_json_log([{"action": "x", "outcome": "test still fails; 0 errors"}])),
            encoding="utf-8",
        )
        rc = main([str(log), "--output-path", str(tmp_path / "ep")])
        assert rc == 0
        episode = json.loads(capsys.readouterr().out)
        assert episode["outcome"] == "success"
        assert not any(e["type"] == "error" for e in episode["events"])


# ---------------------------------------------------------------------------
# Commit events follow committer date, not provenance rank (issue #3619)
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str, when: str | None = None) -> str:
    """Run git in ``repo`` with a fixed identity and an optional pinned date."""
    env = dict(os.environ)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(var, None)
    env.update(
        {
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
    )
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _repo_with_commits(tmp_path: Path, dates: list[str]) -> list[str]:
    """A repository holding one commit per entry in ``dates``, oldest first.

    Returns the full SHAs in the order the commits were made, so a test can
    state the true chronology independently of anything under test.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    shas: list[str] = []
    for index, when in enumerate(dates):
        (repo / f"f{index}.txt").write_text(str(index), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "--quiet", "--no-gpg-sign", "-m", f"c{index}", when=when)
        shas.append(_git(repo, "rev-parse", "HEAD"))
    return shas


def _log_with_commits(ending: str, evidence_shas: list[str]) -> dict[str, Any]:
    """A session log whose commit record spans ``endingCommit`` and evidence."""
    return {
        "session": {"date": "2026-07-29", "startingCommit": "0" * 40},
        "workLog": [{"step": "did the work"}],
        "protocolCompliance": {
            "sessionEnd": {
                "changesCommitted": {
                    "complete": True,
                    "evidence": "Committed " + ", ".join(evidence_shas),
                }
            }
        },
        "endingCommit": ending,
    }


@pytest.fixture(autouse=True)
def _clear_commit_date_cache():
    """Keep one test's temporary repository out of the next test's lookups."""
    _commit_datetime.cache_clear()
    yield
    _commit_datetime.cache_clear()


class TestCommitEventsFollowChronology:
    def test_episode_comparison_head_excludes_later_qa_rebind(
        self, tmp_path, monkeypatch
    ) -> None:
        shas = _repo_with_commits(
            tmp_path,
            [
                "2026-07-01T10:00:00+00:00",
                "2026-07-02T10:00:00+00:00",
                "2026-07-03T10:00:00+00:00",
            ],
        )
        monkeypatch.chdir(tmp_path / "repo")
        log = _log_with_commits(shas[2], [shas[0]])
        log["episodeMetrics"] = {
            "commitHead": shas[1],
            "filesChanged": 2,
            "comparison": {
                "kind": "gitCommitRange",
                "base": shas[0],
                "head": shas[2],
            },
        }

        events = json_events(log, "2026-07-29T00:00:00Z")
        commits = [e["content"] for e in events if e["type"] == "commit"]

        assert commits == [f"Commit: {sha}" for sha in shas[:2]]

    def test_comparison_head_fallback_excludes_later_qa_rebind(
        self, tmp_path, monkeypatch
    ) -> None:
        shas = _repo_with_commits(
            tmp_path,
            [
                "2026-07-01T10:00:00+00:00",
                "2026-07-02T10:00:00+00:00",
                "2026-07-03T10:00:00+00:00",
            ],
        )
        monkeypatch.chdir(tmp_path / "repo")
        log = _log_with_commits(shas[2], [shas[0]])
        log["episodeMetrics"] = {
            "filesChanged": 2,
            "comparison": {
                "kind": "gitCommitRange",
                "base": shas[0],
                "head": shas[1],
            },
        }

        events = json_events(log, "2026-07-29T00:00:00Z")
        commits = [e["content"] for e in events if e["type"] == "commit"]

        assert commits == [f"Commit: {sha}" for sha in shas[:2]]

    def test_ending_commit_is_emitted_last_not_first(self, tmp_path, monkeypatch) -> None:
        shas = _repo_with_commits(
            tmp_path,
            [
                "2026-07-01T10:00:00+00:00",
                "2026-07-02T10:00:00+00:00",
                "2026-07-03T10:00:00+00:00",
            ],
        )
        monkeypatch.chdir(tmp_path / "repo")
        # endingCommit is the newest commit and is ranked first by _collect_shas.
        log = _log_with_commits(shas[2], [shas[0], shas[1]])
        events = json_events(log, "2026-07-29T00:00:00Z")
        commits = [e["content"] for e in events if e["type"] == "commit"]
        assert commits == [f"Commit: {sha}" for sha in shas]

    def test_the_chain_no_longer_claims_the_newest_commit_caused_the_oldest(
        self, tmp_path, monkeypatch
    ) -> None:
        shas = _repo_with_commits(
            tmp_path,
            ["2026-07-01T10:00:00+00:00", "2026-07-02T10:00:00+00:00"],
        )
        monkeypatch.chdir(tmp_path / "repo")
        events = json_events(_log_with_commits(shas[1], [shas[0]]), "2026-07-29T00:00:00Z")
        _link_sequential_events(events)
        by_sha = {e["content"].removeprefix("Commit: "): e for e in events if e["type"] == "commit"}
        older, newer = by_sha[shas[0]], by_sha[shas[1]]
        assert newer["id"] not in older["caused_by"]
        if older["leads_to"] or newer["caused_by"]:
            assert newer["id"] in older["leads_to"]
            assert older["id"] in newer["caused_by"]

    def test_a_single_commit_episode_is_untouched(self, tmp_path, monkeypatch) -> None:
        shas = _repo_with_commits(tmp_path, ["2026-07-01T10:00:00+00:00"])
        monkeypatch.chdir(tmp_path / "repo")
        log = _log_with_commits(shas[0], [])
        events = json_events(log, "2026-07-29T00:00:00Z")
        commits = [e["content"] for e in events if e["type"] == "commit"]
        assert commits == [f"Commit: {shas[0]}"]


class TestOrderingRefusesToGuess:
    def test_an_unresolvable_sha_leaves_the_whole_order_untouched(
        self, tmp_path, monkeypatch
    ) -> None:
        shas = _repo_with_commits(
            tmp_path,
            ["2026-07-01T10:00:00+00:00", "2026-07-02T10:00:00+00:00"],
        )
        monkeypatch.chdir(tmp_path / "repo")
        absent = "abcdef1234567890abcdef1234567890abcdef12"
        given = [shas[1], absent, shas[0]]
        assert _chronological(given) == given

    def test_outside_a_checkout_the_order_is_preserved(self, tmp_path, monkeypatch) -> None:
        shas = _repo_with_commits(
            tmp_path,
            ["2026-07-01T10:00:00+00:00", "2026-07-02T10:00:00+00:00"],
        )
        outside = tmp_path / "not-a-repo"
        outside.mkdir()
        monkeypatch.chdir(outside)
        reversed_order = [shas[1], shas[0]]
        assert _chronological(reversed_order) == reversed_order

    def test_commits_sharing_a_second_keep_their_provenance_order(
        self, tmp_path, monkeypatch
    ) -> None:
        shas = _repo_with_commits(
            tmp_path,
            ["2026-07-01T10:00:00+00:00", "2026-07-01T10:00:00+00:00"],
        )
        monkeypatch.chdir(tmp_path / "repo")
        # Asserted in both directions on purpose. A tiebreak that fell through
        # to the SHA text would satisfy one direction by luck; it cannot
        # satisfy both.
        assert _chronological([shas[1], shas[0]]) == [shas[1], shas[0]]
        _commit_datetime.cache_clear()
        assert _chronological([shas[0], shas[1]]) == [shas[0], shas[1]]

    def test_an_empty_set_is_not_an_error(self) -> None:
        assert _chronological([]) == []


class TestTheSharedLookupStillGatesProseShas:
    def test_a_commit_predating_the_session_is_still_rejected(
        self, tmp_path, monkeypatch
    ) -> None:
        shas = _repo_with_commits(tmp_path, ["2020-01-01T10:00:00+00:00"])
        monkeypatch.chdir(tmp_path / "repo")
        assert _prose_sha_predates_session(shas[0], "2026-07-29") is True

    def test_a_commit_inside_the_window_is_kept(self, tmp_path, monkeypatch) -> None:
        shas = _repo_with_commits(tmp_path, ["2026-07-29T10:00:00+00:00"])
        monkeypatch.chdir(tmp_path / "repo")
        assert _prose_sha_predates_session(shas[0], "2026-07-29") is False

    def test_an_unresolvable_sha_fails_open(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        assert _prose_sha_predates_session("a" * 40, "2026-07-29") is False
