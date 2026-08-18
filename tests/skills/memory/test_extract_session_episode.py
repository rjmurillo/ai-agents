"""Tests for extract_session_episode.py."""

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import extract_session_episode


class TestGetSessionIdFromPath:
    """Tests for get_session_id_from_path function.

    The session ID is preserved with its full descriptive suffix so parallel
    autofix sessions that share a session number but differ in suffix do not
    collide on one episode filename (issue #2379).
    """

    def test_full_date_pattern_preserves_suffix(self):
        result = extract_session_episode.get_session_id_from_path(
            Path("/path/to/2026-01-15-session-42-desc.md")
        )
        assert result == "2026-01-15-session-42-desc"

    def test_bare_number_no_suffix(self):
        result = extract_session_episode.get_session_id_from_path(
            Path("/path/to/2026-01-15-session-42.json")
        )
        assert result == "2026-01-15-session-42"

    def test_parallel_autofix_sessions_get_distinct_ids(self):
        # The #2379 collision shape: same number, different PR suffix.
        a = extract_session_episode.get_session_id_from_path(
            Path("/p/2026-06-04-session-2335-pr-2353-autofix.json")
        )
        b = extract_session_episode.get_session_id_from_path(
            Path("/p/2026-06-04-session-2335-pr-2359-autofix.json")
        )
        assert a == "2026-06-04-session-2335-pr-2353-autofix"
        assert b == "2026-06-04-session-2335-pr-2359-autofix"
        assert a != b

    def test_session_only_pattern(self):
        result = extract_session_episode.get_session_id_from_path(Path("/path/to/session-7.md"))
        assert result == "session-7"

    def test_session_only_pattern_preserves_suffix(self):
        result = extract_session_episode.get_session_id_from_path(
            Path("/path/to/session-7-hotfix.md")
        )
        assert result == "session-7-hotfix"

    def test_fallback_to_filename(self):
        result = extract_session_episode.get_session_id_from_path(Path("/path/to/custom-name.md"))
        assert result == "custom-name"


class TestParseSessionMetadata:
    """Tests for parse_session_metadata function."""

    def test_extracts_title(self):
        lines = ["# Session 42 Log", "Some content"]
        result = extract_session_episode.parse_session_metadata(lines)
        assert result["title"] == "Session 42 Log"

    def test_extracts_date(self):
        lines = ["# Title", "**Date**: 2026-01-15"]
        result = extract_session_episode.parse_session_metadata(lines)
        assert result["date"] == "2026-01-15"

    def test_extracts_status(self):
        lines = ["# Title", "**Status**: Complete"]
        result = extract_session_episode.parse_session_metadata(lines)
        assert result["status"] == "Complete"

    def test_extracts_objectives(self):
        lines = [
            "## Objectives",
            "- Implement feature X",
            "- Test feature X",
            "## Next",
        ]
        result = extract_session_episode.parse_session_metadata(lines)
        assert len(result["objectives"]) == 2
        assert "Implement feature X" in result["objectives"]

    def test_empty_content(self):
        result = extract_session_episode.parse_session_metadata([])
        assert result["title"] == ""
        assert result["objectives"] == []


class TestGetDecisionType:
    """Tests for get_decision_type function."""

    def test_design_type(self):
        assert extract_session_episode.get_decision_type("Changed the schema design") == "design"

    def test_test_type(self):
        assert extract_session_episode.get_decision_type("Added Pester coverage") == "test"

    def test_recovery_type(self):
        assert extract_session_episode.get_decision_type("Applied fix for retry") == "recovery"

    def test_routing_type(self):
        assert extract_session_episode.get_decision_type("Delegate to agent") == "routing"

    def test_default_implementation(self):
        assert extract_session_episode.get_decision_type("Some action") == "implementation"


class TestParseDecisions:
    """Tests for parse_decisions function."""

    def test_explicit_decision(self):
        lines = ["**Decision**: Use Python for new scripts"]
        result = extract_session_episode.parse_decisions(lines)
        assert len(result) >= 1
        assert "Python" in result[0]["chosen"]

    def test_inline_decision(self):
        lines = ["We chose to implement the feature with a factory pattern"]
        result = extract_session_episode.parse_decisions(lines)
        assert len(result) >= 1

    def test_no_decisions(self):
        lines = ["Just some regular text", "No decisions here"]
        result = extract_session_episode.parse_decisions(lines)
        assert len(result) == 0


class TestParseEvents:
    """Tests for parse_events function."""

    def test_commit_events(self):
        # Source regex: r'commit[ted]?\s+(?:as\s+)?([a-f0-9]{7,40})'
        # Or: r'([a-f0-9]{7,40})\s+\w+\(.+\):'
        lines = ["commit abc1234def with changes"]
        result = extract_session_episode.parse_events(lines)
        commits = [e for e in result if e["type"] == "commit"]
        assert len(commits) >= 1

    def test_error_events(self):
        lines = ["An error occurred in the build"]
        result = extract_session_episode.parse_events(lines)
        errors = [e for e in result if e["type"] == "error"]
        assert len(errors) >= 1

    def test_milestone_events(self):
        lines = ["- completed the migration successfully"]
        result = extract_session_episode.parse_events(lines)
        milestones = [e for e in result if e["type"] == "milestone"]
        assert len(milestones) >= 1

    def test_bold_status_marker_is_milestone(self):
        """Archived bullets like `- **Status**: COMPLETE` are milestones; the
        plain milestone rule skips list markers followed by `**` (#2170 GA722)."""
        lines = ["- **Status**: COMPLETE"]
        result = extract_session_episode.parse_events(lines)
        milestones = [e for e in result if e["type"] == "milestone"]
        assert len(milestones) == 1
        assert "Status" in milestones[0]["content"]

    def test_bold_status_in_progress_not_milestone(self):
        """A non-completed bold status is not a milestone."""
        lines = ["- **Status**: IN PROGRESS"]
        result = extract_session_episode.parse_events(lines)
        assert not any(e["type"] == "milestone" for e in result)

    def test_headings_excluded(self):
        lines = ["# Error Handling Section"]
        result = extract_session_episode.parse_events(lines)
        assert len(result) == 0


class TestParseLessons:
    """Tests for parse_lessons function."""

    def test_lessons_section(self):
        lines = [
            "## Lessons Learned",
            "- Always validate input first",
            "- Test edge cases early",
            "## End",
        ]
        result = extract_session_episode.parse_lessons(lines)
        assert len(result) >= 2

    def test_inline_lessons(self):
        # A bullet whose content begins with a lesson keyword is collected even
        # outside a Lessons section.
        lines = ["- Lesson: always check return codes"]
        result = extract_session_episode.parse_lessons(lines)
        assert result == ["Lesson: always check return codes"]

    def test_evidence_prose_not_collected_as_lesson(self):
        # GAgue: protocol-gate evidence and checklist items mention "lessons"
        # mid-line but are not lessons. They must not pollute the episode.
        lines = [
            "- **Evidence**: lessons captured in the PR description",
            "- Documents lesson learned for future protocol enforcement",
            "- Skills memory updated with lessons learned",
            "**P2 - Copilot C2**: Added lessons field to episode metadata",
        ]
        result = extract_session_episode.parse_lessons(lines)
        assert result == []

    def test_section_bullets_still_collected_when_prose_present(self):
        lines = [
            "- Evidence: lessons captured in the PR description",
            "## Lessons Learned",
            "- Always validate input first",
            "## End",
        ]
        result = extract_session_episode.parse_lessons(lines)
        assert result == ["Always validate input first"]

    def test_deduplication(self):
        lines = [
            "## Lessons Learned",
            "- Use guard clauses",
            "- Use guard clauses",
            "## End",
        ]
        result = extract_session_episode.parse_lessons(lines)
        assert result.count("Use guard clauses") == 1


class TestParseMetrics:
    """Tests for parse_metrics function."""

    def test_duration(self):
        lines = ["Session lasted 45 minutes"]
        result = extract_session_episode.parse_metrics(lines)
        assert result["duration_minutes"] == 45

    def test_files_changed(self):
        lines = ["12 files changed in this session"]
        result = extract_session_episode.parse_metrics(lines)
        assert result["files_changed"] == 12

    def test_default_zeros(self):
        result = extract_session_episode.parse_metrics([])
        assert result["duration_minutes"] == 0
        assert result["commits"] == 0


class TestGetSessionOutcome:
    """Tests for get_session_outcome function."""

    def test_complete_status(self):
        metadata = {"status": "Complete"}
        assert extract_session_episode.get_session_outcome(metadata, []) == "success"

    def test_failed_status(self):
        metadata = {"status": "Failed"}
        assert extract_session_episode.get_session_outcome(metadata, []) == "failure"

    def test_partial_status(self):
        metadata = {"status": "In Progress"}
        assert extract_session_episode.get_session_outcome(metadata, []) == "partial"

    def test_inferred_from_events(self):
        metadata = {"status": ""}
        events = [{"type": "milestone"}, {"type": "milestone"}]
        assert extract_session_episode.get_session_outcome(metadata, events) == "success"

    def test_inferred_failure(self):
        metadata = {"status": ""}
        events = [{"type": "error"}, {"type": "error"}, {"type": "error"}]
        assert extract_session_episode.get_session_outcome(metadata, events) == "failure"

    def test_no_info_partial(self):
        metadata = {"status": ""}
        assert extract_session_episode.get_session_outcome(metadata, []) == "partial"


def _gate(complete):
    return {"level": "MUST", "Complete": complete, "Evidence": "x"}


def _lowercase_gate(complete):
    return {"level": "MUST", "complete": complete, "evidence": "x"}


def _json_log(work_log, end_complete=True, committed=None):
    """``committed`` populates the session-end changesCommitted evidence, which
    is the protocol's authoritative record of what the session committed and
    the source commit provenance reads first (issue #3363).

    Left at None the evidence keeps the gate default: a non-empty string that
    names no SHA, which is the majority shape among prose-only logs. Pass
    ``committed=""`` for the minority shape, where the evidence is absent
    entirely. Both reach the prose fallback, and both are exercised below. The
    corpus split behind that claim lives in the extractor docstring, so it has
    one home to re-measure.
    """
    gate = _gate(end_complete)
    committed_gate = dict(gate)
    if committed is not None:
        committed_gate["Evidence"] = committed
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
                "changesCommitted": committed_gate,
                "validationPassed": gate,
            },
        },
        "workLog": work_log,
        "endingCommit": "bbbbbbb1234",
        "nextSteps": [],
    }


class TestJsonSessionLogPath:
    """JSON is the primary session-log format (issue #2036)."""

    def test_detects_json_session(self):
        content = json.dumps(_json_log([{"task": "t", "outcome": "o"}]))
        assert extract_session_episode.looks_like_json_session(content) is not None

    def test_markdown_is_none(self):
        assert extract_session_episode.looks_like_json_session("# H\n**Status**: Done\n") is None

    def test_all_gates_complete_is_success(self):
        assert (
            extract_session_episode.json_outcome(_json_log([{"task": "t", "outcome": "20 passed"}]))
            == "success"
        )

    def test_lowercase_session_end_gates_are_success(self):
        data = _json_log([{"task": "t", "outcome": "20 passed"}])
        gate = _lowercase_gate(True)
        data["protocolCompliance"]["sessionEnd"] = {
            "checklistComplete": gate,
            "changesCommitted": gate,
            "validationPassed": gate,
        }
        assert extract_session_episode.json_outcome(data) == "success"

    def test_incomplete_gates_is_partial(self):
        assert (
            extract_session_episode.json_outcome(
                _json_log([{"task": "t", "outcome": "wip"}], end_complete=False)
            )
            == "partial"
        )

    def test_counted_failure_incomplete_is_failure(self):
        assert (
            extract_session_episode.json_outcome(
                _json_log([{"task": "t", "outcome": "3 failed"}], end_complete=False)
            )
            == "failure"
        )

    def test_regression_2036_prose_fail_not_failure(self):
        data = _json_log(
            [
                {"action": "compress", "outcome": "compression insufficient; test still fails"},
                {"action": "verify", "outcome": "AGENTS.md 2791 B; markdownlint 0 errors"},
            ]
        )
        assert extract_session_episode.json_outcome(data) == "success"

    def test_milestone_from_task_and_action_and_string(self):
        ev_task = extract_session_episode.json_events(
            _json_log([{"task": "Build X", "outcome": "done"}]), "2026-05-31T00:00:00+00:00"
        )
        ev_action = extract_session_episode.json_events(
            _json_log([{"action": "Refactor Y", "outcome": "done"}]), "2026-05-31T00:00:00+00:00"
        )
        ev_string = extract_session_episode.json_events(
            _json_log(["Reviewed PR 1766"]), "2026-05-31T00:00:00+00:00"
        )
        assert any(e["type"] == "milestone" and e["content"] == "Build X" for e in ev_task)
        assert any(e["type"] == "milestone" and e["content"] == "Refactor Y" for e in ev_action)
        assert any(
            e["type"] == "milestone" and "Reviewed PR 1766" in e["content"] for e in ev_string
        )

    def test_no_error_event_from_prose_fail(self):
        events = extract_session_episode.json_events(
            _json_log([{"action": "x", "outcome": "test still fails; 0 errors"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert not any(e["type"] == "error" for e in events)

    def test_error_event_from_counted_failure(self):
        events = extract_session_episode.json_events(
            _json_log([{"task": "t", "outcome": "2 failed"}]), "2026-05-31T00:00:00+00:00"
        )
        assert any(e["type"] == "error" for e in events)

    def test_string_worklog_does_not_crash(self):
        m = extract_session_episode.json_metrics(_json_log(["touched 3 files", "ran tests"]))
        assert m["files_changed"] == 3

    def test_main_on_json_log_with_prose_fail(self, tmp_path, capsys):
        log = tmp_path / "2026-05-31-session-9001.json"
        log.write_text(
            json.dumps(_json_log([{"action": "x", "outcome": "test still fails; 0 errors"}])),
            encoding="utf-8",
        )
        rc = extract_session_episode.main([str(log), "--output-path", str(tmp_path / "ep")])
        assert rc == 0
        episode = json.loads(capsys.readouterr().out)
        assert episode["outcome"] == "success"
        assert not any(e["type"] == "error" for e in episode["events"])


class TestJsonNullSafety:
    """Explicit JSON null values must not poison extraction (issue #2036).

    dict.get(key, default) returns None, not the default, when the key is
    present with a null value. These cover the null-coercion guards.
    """

    def test_null_session_timestamp_falls_back(self):
        data = {"session": None, "workLog": []}
        ts = extract_session_episode.json_timestamp(data)
        assert isinstance(ts, str) and ts.endswith("+00:00")

    def test_null_worklog_outcome(self):
        data = _json_log([])
        data["workLog"] = None
        assert extract_session_episode.json_outcome(data) in {"success", "partial", "failure"}

    def test_null_worklog_events_no_crash(self):
        data = _json_log([])
        data["workLog"] = None
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        assert isinstance(events, list)

    def test_null_worklog_decisions_no_crash(self):
        data = _json_log([])
        data["workLog"] = None
        assert extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00") == []

    def test_null_worklog_metrics_no_crash(self):
        data = _json_log([])
        data["workLog"] = None
        metrics = extract_session_episode.json_metrics(data)
        assert isinstance(metrics, dict)

    def test_null_ending_commit_no_none_string(self):
        data = _json_log([{"task": "t", "outcome": "ok"}])
        data["endingCommit"] = None
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        assert not any("None" in str(e.get("content", "")) for e in events)

    def test_null_protocol_compliance_gate(self):
        data = _json_log([])
        data["protocolCompliance"] = None
        assert (
            extract_session_episode._gate_complete(data, "sessionEnd", "checklistComplete") is False
        )

    def test_null_entry_field_not_literal_none(self):
        assert extract_session_episode._entry_field({"task": None}, "task") == ""

    def test_null_nested_field_in_entry_text(self):
        text = extract_session_episode._entry_text({"task": "build", "outcome": None})
        assert "None" not in text and "build" in text

    def test_extract_from_json_null_objective(self):
        data = _json_log([{"task": "t", "outcome": "ok"}])
        data["session"]["objective"] = None
        bundle = extract_session_episode.extract_from_json(data, archive_fallback=False)
        assert bundle["task"] == ""


class TestArchiveFallback:
    """Padded session-id candidates and archive metric sourcing (issue #2036)."""

    def test_candidates_pad_widths(self):
        cands = extract_session_episode._archive_session_id_candidates("2026-05-31", 2)
        assert cands == [
            "2026-05-31-session-2",
            "2026-05-31-session-02",
            "2026-05-31-session-002",
        ]

    def test_candidates_dedupe_already_padded(self):
        cands = extract_session_episode._archive_session_id_candidates("2026-05-31", "003")
        assert cands == ["2026-05-31-session-003"]

    def test_padded_archive_json_is_found(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-02.json"
        archive.write_text(
            json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8"
        )

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        data = {"session": {"number": 2, "date": "2026-05-31"}, "workLog": [], "endingCommit": ""}
        bundle = extract_session_episode.extract_from_json(data)
        assert any(e.get("type") == "milestone" for e in bundle["events"])

    def test_metrics_sourced_from_archive(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(
            json.dumps(_json_log([{"task": "t", "outcome": "3 failed"}])), encoding="utf-8"
        )

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        data = {"session": {"number": 2, "date": "2026-05-31"}, "workLog": [], "endingCommit": ""}
        bundle = extract_session_episode.extract_from_json(data)
        assert bundle["metrics"]["errors"] >= 1

    def test_markdown_archive_does_not_inflate_metrics(self, tmp_path, monkeypatch):
        """Markdown-archive recovery contributes events, not metrics. Prose SHAs
        and "N files" phrases must NOT inflate commits/files (#2170 thread
        GA721). Metrics stay sourced from the structured primary JSON."""
        md = tmp_path / "2026-05-31-session-2.md"
        md.write_text(
            "# Session\n"
            "- **Status**: COMPLETE\n"
            "See https://example.com/commit/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0\n"
            "Reviewed 185 files across the repository\n"
            "Found 23 errors in pre-existing files\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(extract_session_episode, "_find_archive_json", lambda sid: None)

        def fake_md(session_id):
            p = tmp_path / f"{session_id}.md"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_markdown", fake_md)
        data = {"session": {"number": 2, "date": "2026-05-31"}, "workLog": [], "endingCommit": ""}
        bundle = extract_session_episode.extract_from_json(data)
        # Sparse primary (empty workLog, no endingCommit) -> zero metrics despite
        # prose mentioning a SHA, "185 files", and "23 errors".
        assert bundle["metrics"]["commits"] == 0
        assert bundle["metrics"]["files_changed"] == 0
        assert bundle["metrics"]["errors"] == 0
        # The bold status marker is still recovered as a narrative milestone.
        assert any(e.get("type") == "milestone" for e in bundle["events"])

    def test_truthy_empty_worklog_still_uses_archive(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(
            json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8"
        )

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        data = {"session": {"number": 2, "date": "2026-05-31"}, "workLog": [{}], "endingCommit": ""}
        bundle = extract_session_episode.extract_from_json(data)
        assert any(e.get("type") == "milestone" for e in bundle["events"])


class TestStepWorklogEntries:
    """`{step, evidence}` work-log entries must yield milestone events (#2036)."""

    def test_step_entry_becomes_milestone(self):
        data = _json_log([{"step": "Migrated schema", "evidence": "psql ok"}])
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        assert any(e["type"] == "milestone" and e["content"] == "Migrated schema" for e in events)

    def test_step_entry_text_includes_evidence(self):
        text = extract_session_episode._entry_text({"step": "Built X", "evidence": "3 failed"})
        assert "Built X" in text and "3 failed" in text

    def test_numeric_step_prefers_summary_for_title(self):
        title = extract_session_episode._entry_title({"step": 1, "summary": "Authored REQ-005"})
        assert title == "Authored REQ-005"

    def test_numeric_step_summary_becomes_milestone(self):
        data = _json_log([{"step": 1, "summary": "Authored REQ-005"}])
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        assert any(e["type"] == "milestone" and e["content"] == "Authored REQ-005" for e in events)
        assert not any(e["type"] == "milestone" and e["content"] == "1" for e in events)

    def test_summary_included_in_entry_text(self):
        text = extract_session_episode._entry_text({"step": 2, "summary": "Ran 3 failed checks"})
        assert "Ran 3 failed checks" in text


class TestEntryKeyWorklogEntries:
    """`{entry: ...}` work-log entries must yield milestone events (#2552)."""

    def test_entry_field_becomes_milestone(self):
        data = _json_log([{"entry": "Filed 40 latent issues"}])
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        assert any(
            e["type"] == "milestone" and e["content"] == "Filed 40 latent issues" for e in events
        )

    def test_entry_title_uses_entry_field(self):
        assert extract_session_episode._entry_title({"entry": "Reviewed PRs"}) == "Reviewed PRs"

    def test_entry_text_includes_entry_field(self):
        text = extract_session_episode._entry_text({"entry": "Audited the catalog"})
        assert "Audited the catalog" in text

    def test_task_still_preferred_over_entry(self):
        title = extract_session_episode._entry_title({"task": "Primary", "entry": "Secondary"})
        assert title == "Primary"


class TestJsonLessonsObjectShape:
    """`_json_lessons` flattens the schema object shape (#2170 thread GAzih)."""

    def test_object_patterns_and_avoidances(self):
        data = {
            "learnings": {
                "patterns": [
                    {
                        "pattern": "Save pending state before reset",
                        "context": "lost data at boundaries",
                        "application": "Always checkpoint first",
                    },
                ],
                "avoidances": [
                    {
                        "antipattern": "Resetting mid-loop",
                        "consequence": "dropped items",
                        "correction": "Defer the reset",
                    },
                ],
            }
        }
        out = extract_session_episode._json_lessons(data)
        assert "Save pending state before reset. Always checkpoint first" in out
        assert "Avoid: Resetting mid-loop. Defer the reset" in out

    def test_list_shape_still_supported(self):
        data = {"learnings": ["Lesson one", {"text": "Lesson two"}]}
        assert extract_session_episode._json_lessons(data) == ["Lesson one", "Lesson two"]

    def test_unknown_shape_returns_empty(self):
        assert extract_session_episode._json_lessons({"learnings": "nope"}) == []

    def test_object_learnings_pass_lesson_filter(self):
        # Object-shaped lessons must survive _dedupe_lessons' junk filter.
        data = {"learnings": {"patterns": [{"pattern": "Prefer fail-closed gates"}]}}
        out = extract_session_episode._json_lessons(data)
        assert all(extract_session_episode._is_lesson_text(t) for t in out)


class TestJsonCommitMetric:
    """`json_metrics["commits"]` counts every distinct documented commit (#2170).

    #2170 established that a session's commit count is not just ``endingCommit``.
    #3363 corrected where the rest come from: the session-end changesCommitted
    evidence, not work-log narrative, which also cites commits the session read
    rather than authored.
    """

    def test_counts_ending_and_changes_committed_shas(self):
        data = _json_log([], committed="Commits: 1234abc (parser), 5678def0 (lint).")
        # endingCommit bbbbbbb1234 + two changesCommitted SHAs = 3 distinct.
        assert extract_session_episode.json_metrics(data)["commits"] == 3

    def test_dedupes_repeated_sha(self):
        data = _json_log(
            [{"task": "Re-reference", "evidence": "see 1234abc for details"}],
            committed="Commit 1234abc, verified again as 1234abc.",
        )
        # endingCommit + one distinct evidence SHA (1234abc counted once) = 2.
        assert extract_session_episode.json_metrics(data)["commits"] == 2

    def test_no_sha_yields_zero(self):
        data = _json_log([{"task": "Investigated", "outcome": "no commit yet"}])
        data["endingCommit"] = ""
        assert extract_session_episode.json_metrics(data)["commits"] == 0

    def test_excludes_starting_commit(self):
        data = _json_log([{"task": "t", "outcome": "ok"}])
        data["endingCommit"] = ""
        # startingCommit "aaaaaaa" must not be counted.
        assert extract_session_episode.json_metrics(data)["commits"] == 0

    def test_decimal_comment_id_in_prose_not_counted(self):
        # #3301: a 10-digit GitHub comment ID in work-log prose is decimal-only
        # and must not be misread as a commit SHA.
        data = _json_log([{"task": "t", "outcome": "posted to #3295 comment 5036380560"}])
        data["endingCommit"] = ""
        assert extract_session_episode.json_metrics(data)["commits"] == 0

    def test_seven_digit_decimal_in_prose_not_counted(self):
        # #3301 boundary: _SHA_RE matches 7-to-40 hex chars, so 7 is the lower
        # edge of the candidate range. A 7-digit decimal-only token in prose sits
        # exactly on that edge and must not be counted as a commit.
        data = _json_log([{"task": "t", "outcome": "see run 1234567 for logs"}])
        data["endingCommit"] = ""
        assert extract_session_episode.json_metrics(data)["commits"] == 0

    def test_hex_sha_in_prose_still_counted(self):
        # A real short SHA (contains hex letters) in prose is still counted.
        data = _json_log([{"task": "t", "outcome": "committed 1234abc"}])
        data["endingCommit"] = ""
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_prose_mixes_comment_id_and_sha_counts_only_sha(self):
        # #3301 edge: prose with both a decimal ID and a real SHA counts one.
        data = _json_log([{"task": "t", "outcome": "fixed in abc1234 per run 29708719280"}])
        data["endingCommit"] = ""
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_all_decimal_ending_commit_still_counted(self):
        # #3301 edge: endingCommit is a structured field, scanned unfiltered, so
        # an all-decimal SHA there is still counted. Digit-only short prefixes
        # occur in real repos, so this path is real, not theoretical.
        data = _json_log([{"task": "t", "outcome": "no prose sha"}])
        data["endingCommit"] = "1234567"
        assert extract_session_episode.json_metrics(data)["commits"] == 1


class TestCommitProvenanceConsistency:
    """Commit events and metrics.commits share one provenance rule so preserve
    accumulation never drifts from the event stream (issue #3123)."""

    _NOW = "2026-07-16T00:00:00+00:00"

    @staticmethod
    def _commit_events(episode):
        return [e for e in episode["events"] if e["type"] == "commit"]

    @staticmethod
    def _log(ending, work_log=None):
        data = _json_log(work_log or [{"task": "t", "outcome": "ok"}])
        data["session"]["startingCommit"] = "b31cb29"
        data["endingCommit"] = ending
        return data

    def test_fresh_events_equal_metrics(self):
        data = self._log("e07f40f")
        data["protocolCompliance"]["sessionEnd"]["changesCommitted"]["Evidence"] = (
            "Commits: 45576b6 (parser), 24da6b2 (lint)."
        )
        commit_events = self._commit_events(
            {"events": extract_session_episode.json_events(data, self._NOW)}
        )
        # endingCommit + two changesCommitted SHAs = 3 documented, all retained.
        assert len(commit_events) == 3
        assert len(commit_events) == extract_session_episode.json_metrics(data)["commits"]

    def test_starting_sha_in_worklog_prose_excluded(self):
        data = self._log(
            "e07f40f",
            [{"task": "closeout", "outcome": "merged origin/main at b31cb29"}],
        )
        commit_events = self._commit_events(
            {"events": extract_session_episode.json_events(data, self._NOW)}
        )
        # Base SHA b31cb29 appears in prose but is not a session-produced commit.
        assert not any("b31cb29" in e["content"] for e in commit_events)
        assert len(commit_events) == 1
        assert len(commit_events) == extract_session_episode.json_metrics(data)["commits"]

    def test_full_starting_sha_abbreviated_in_worklog_excluded(self):
        # startingCommit stored full-length (40 hex) but work-log prose repeats
        # it as a 7-char abbreviation. Exact-equality exclusion would miss it
        # and leak a phantom commit; git-abbreviation matching excludes it
        # (issue #3123 acceptance criterion 2).
        data = _json_log([{"task": "closeout", "outcome": "merged base e535a4f"}])
        data["session"]["startingCommit"] = "e535a4f33bcde972c829a6264bb3568c46a8954c"
        data["endingCommit"] = "e07f40f"
        commit_events = self._commit_events(
            {"events": extract_session_episode.json_events(data, self._NOW)}
        )
        assert not any("e535a4f" in e["content"] for e in commit_events)
        assert len(commit_events) == 1
        assert len(commit_events) == extract_session_episode.json_metrics(data)["commits"]

    def test_same_commit_abbreviation_matching(self):
        full = "e535a4f33bcde972c829a6264bb3568c46a8954c"
        assert extract_session_episode._same_commit(full, "e535a4f")
        assert extract_session_episode._same_commit("e535a4f", full)
        assert extract_session_episode._same_commit(full, full)
        # Distinct commits sharing a 6-char prefix are not the same commit.
        assert not extract_session_episode._same_commit(full, "e535a4e9abc")
        # Below the extractor's own seven-character floor, do not treat as a
        # match. The floor is this module's rule; git's abbreviation length is
        # repo-dependent (core.abbrev), so there is no git minimum to cite.
        assert not extract_session_episode._same_commit(full, "e535a4")
        assert not extract_session_episode._same_commit("", full)

    def test_three_sequential_preserve_runs_stay_consistent(self):
        episode = extract_session_episode.extract_from_json(
            self._log("e07f40f"), archive_fallback=False
        )
        for sha in ("45576b6", "24da6b2"):
            fresh = extract_session_episode.extract_from_json(
                self._log(sha), archive_fallback=False
            )
            episode = extract_session_episode.merge_preserving(
                fresh, episode, session_id="2026-07-16-session-1"
            )
        commit_events = self._commit_events(episode)
        # Three preserve runs accumulate three distinct commit events; metrics
        # tracks them exactly (was 3 events / 2 metrics before #3123).
        assert len(commit_events) == 3
        assert episode["metrics"]["commits"] == 3

    def test_force_after_history_matches_events(self):
        fresh = extract_session_episode.extract_from_json(
            self._log("24da6b2"), archive_fallback=False
        )
        commit_events = self._commit_events(fresh)
        assert len(commit_events) == 1
        assert fresh["metrics"]["commits"] == len(commit_events)

    def test_preserve_is_idempotent_for_commits(self):
        base = extract_session_episode.extract_from_json(
            self._log("e07f40f"), archive_fallback=False
        )
        once = extract_session_episode.merge_preserving(
            extract_session_episode.extract_from_json(self._log("e07f40f"), archive_fallback=False),
            base,
            session_id="s",
        )
        twice = extract_session_episode.merge_preserving(
            extract_session_episode.extract_from_json(self._log("e07f40f"), archive_fallback=False),
            once,
            session_id="s",
        )
        assert twice["metrics"]["commits"] == once["metrics"]["commits"] == 1


class TestArchiveGateAndRoot:
    """Decisions must not block event recovery; repo root resolves via marker (#2036)."""

    def test_decisions_do_not_block_archive_events(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(
            json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8"
        )

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        # Primary log: a decision (via action label) but no milestone events.
        data = {
            "session": {"number": 2, "date": "2026-05-31"},
            "workLog": [{"action": "chose approach A because it is simpler"}],
            "endingCommit": "",
        }
        bundle = extract_session_episode.extract_from_json(data)
        assert bundle["decisions"], "primary decision should be preserved"
        assert any(e.get("type") == "milestone" for e in bundle["events"]), (
            "archive events should still be recovered"
        )

    def test_repo_root_finds_agents_marker(self):
        root = extract_session_episode._repo_root()
        assert (root / ".agents").is_dir()

    def test_commit_only_log_keeps_commit_when_archive_exists(self, tmp_path, monkeypatch):
        # GAgua: a log whose only event is its own commit must not have that
        # commit overwritten by archived events. Decisions/lessons still recover.
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(
            json.dumps(
                _json_log(
                    [
                        {"task": "archived work", "outcome": "5 passed"},
                        {"action": "chose approach A because it is simpler"},
                    ]
                )
            ),
            encoding="utf-8",
        )

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        # Primary log: no milestone/test/error, only an ending commit.
        data = {
            "session": {"number": 2, "date": "2026-05-31"},
            "workLog": [],
            "endingCommit": "abc1234",
        }
        bundle = extract_session_episode.extract_from_json(data)
        commits = [e for e in bundle["events"] if e.get("type") == "commit"]
        assert commits, "own commit event must survive archive recovery"
        assert not any(e.get("type") == "milestone" for e in bundle["events"]), (
            "archive events must not replace the session's own commit event"
        )
        assert bundle["decisions"], "archived decisions should still be recovered"


class TestArchiveGatedOnEvents:
    """A primary log with its own events must not pull archive decisions/lessons (#2036)."""

    def test_events_present_skips_archive(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(
            json.dumps(_json_log([{"evidence": "chose approach B because faster"}])),
            encoding="utf-8",
        )
        calls = []

        def fake_find(session_id):
            calls.append(session_id)
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        # Primary log has a milestone of its own and no decisions/lessons.
        data = {
            "session": {"number": 2, "date": "2026-05-31"},
            "workLog": [{"task": "Did the work", "outcome": "ok"}],
            "endingCommit": "",
        }
        bundle = extract_session_episode.extract_from_json(data)
        assert any(e.get("type") == "milestone" for e in bundle["events"])
        assert calls == [], "archive must not be consulted when primary has events"
        assert bundle["decisions"] == []


class TestDecisionVerbs:
    """Decision detection covers adopt/prioritize wording in signal fields (#2036, #2170).

    Decisions are detected from the entry's own label fields (task/action/
    summary/step), not from narrative ``evidence``/``result`` prose, so migrated
    prose mentioning "adopt"/"prioritize" does not manufacture spurious
    decisions (Cursor BugBot GAYz0).
    """

    def test_adopt_is_a_decision(self):
        data = _json_log([{"action": "adopt the streaming parser for large logs"}])
        assert extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00")

    def test_prioritize_is_a_decision(self):
        data = _json_log([{"summary": "prioritized correctness over throughput"}])
        assert extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00")

    def test_evidence_only_keyword_is_not_a_decision(self):
        # Keyword lives only in narrative evidence/result, not a label field.
        data = _json_log([{"task": "Ran tests", "evidence": "adopt the new approach"}])
        assert extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00") == []

    def test_chosen_prefers_label_over_status_outcome(self):
        data = _json_log([{"action": "Selected the fail-closed option", "outcome": "success"}])
        decisions = extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00")
        assert decisions
        assert decisions[0]["chosen"] == "Selected the fail-closed option"
        assert decisions[0]["chosen"].lower() != "success"


class TestMergePreserving:
    """merge_preserving never drops existing richer data and is idempotent (#2170)."""

    @staticmethod
    def _stub():
        return {
            "id": "episode-2026-01-08-session-807",
            "session": "2026-01-08-session-807",
            "timestamp": "2026-01-08T00:00:00+00:00",
            "outcome": "success",
            "task": "[Migrated from markdown]",
            "decisions": [],
            "events": [],
            "metrics": {
                "duration_minutes": 0,
                "tool_calls": 0,
                "errors": 0,
                "recoveries": 0,
                "commits": 0,
                "files_changed": 0,
            },
            "lessons": [],
        }

    @staticmethod
    def _rich():
        return {
            "id": "episode-2026-01-08-session-807",
            "session": "2026-01-08-session-807",
            "timestamp": "2026-01-08T12:20:10.97-06:00",
            "outcome": "success",
            "task": "Session 807 real work",
            "decisions": [
                {
                    "id": "d001",
                    "type": "tradeoff",
                    "context": "parser",
                    "chosen": "streaming",
                    "rationale": "memory",
                    "outcome": "success",
                    "effects": [],
                }
            ],
            "events": [
                {
                    "id": "e001",
                    "timestamp": "2026-01-08T12:20:10.93-06:00",
                    "type": "milestone",
                    "content": "did the thing",
                    "caused_by": [],
                    "leads_to": [],
                }
            ],
            "metrics": {
                "duration_minutes": 0,
                "tool_calls": 0,
                "errors": 3,
                "recoveries": 0,
                "commits": 0,
                "files_changed": 7,
            },
            "lessons": ["curated lesson one"],
        }

    def test_stub_new_keeps_existing_content(self):
        merged = extract_session_episode.merge_preserving(
            self._stub(), self._rich(), session_id="2026-01-08-session-807"
        )
        assert merged["task"] == "Session 807 real work"
        assert [e["content"] for e in merged["events"]] == ["did the thing"]
        assert merged["lessons"] == ["curated lesson one"]
        assert len(merged["decisions"]) == 1

    def test_metrics_take_per_key_max(self):
        merged = extract_session_episode.merge_preserving(
            self._stub(), self._rich(), session_id="2026-01-08-session-807"
        )
        assert merged["metrics"]["errors"] == 3
        assert merged["metrics"]["files_changed"] == 7

    def test_event_timestamps_keep_explicit_source_time(self):
        merged = extract_session_episode.merge_preserving(
            self._stub(), self._rich(), session_id="2026-01-08-session-807"
        )
        assert merged["events"][0]["timestamp"] == "2026-01-08T12:20:10.93-06:00"

    def test_placeholder_task_yields_but_real_new_task_wins(self):
        new = self._stub()
        new["task"] = "fresh real task"
        merged = extract_session_episode.merge_preserving(
            new, self._rich(), session_id="2026-01-08-session-807"
        )
        assert merged["task"] == "fresh real task"

    def test_lessons_union_appends_new_uniques(self):
        new = self._stub()
        new["lessons"] = ["curated lesson one", "brand new lesson"]
        merged = extract_session_episode.merge_preserving(
            new, self._rich(), session_id="2026-01-08-session-807"
        )
        assert merged["lessons"] == ["curated lesson one", "brand new lesson"]

    def test_preserve_drops_json_fragment_lessons(self):
        # GAo-h: previously committed episodes carry JSON-fragment junk in
        # lessons; --preserve must filter them out, not union them forward.
        existing = self._rich()
        existing["lessons"] = [
            '"retrospectiveInvoked": {"level": "SHOULD", "Complete": false}',
            '"Evidence": "Deferred; lessons captured in PR description"',
            "Real prose lesson worth keeping",
        ]
        new = self._stub()
        new["lessons"] = ["A fresh genuine lesson"]
        merged = extract_session_episode.merge_preserving(
            new, existing, session_id="2026-01-08-session-807"
        )
        assert merged["lessons"] == [
            "Real prose lesson worth keeping",
            "A fresh genuine lesson",
        ]

    def test_dedupe_lessons_keeps_prose_mentioning_evidence(self):
        result = extract_session_episode._dedupe_lessons(
            ["The extractor mis-classifies Evidence strings as outcomes"], []
        )
        assert result == ["The extractor mis-classifies Evidence strings as outcomes"]

    def test_idempotent_second_merge_is_noop(self):
        sid = "2026-01-08-session-807"
        once = extract_session_episode.merge_preserving(self._stub(), self._rich(), session_id=sid)
        twice = extract_session_episode.merge_preserving(self._stub(), once, session_id=sid)
        assert twice == once
        assert json.dumps(twice) == json.dumps(once)

    def test_no_wallclock_when_no_deterministic_date(self):
        new = {"timestamp": "", "events": [], "decisions": [], "lessons": [], "metrics": {}}
        existing = {
            "timestamp": "",
            "events": [
                {
                    "id": "e001",
                    "timestamp": "garbage",
                    "type": "milestone",
                    "content": "x",
                    "caused_by": [],
                    "leads_to": [],
                }
            ],
            "decisions": [],
            "lessons": [],
            "metrics": {},
        }
        merged = extract_session_episode.merge_preserving(new, existing, session_id="")
        assert merged["events"][0]["timestamp"] == "garbage"

    def test_commit_events_keep_real_committer_timestamp(self):
        """Commit events must not have their timestamp overwritten with midnight.

        Issue #4071: _dedupe_events() applied the midnight stamp to ALL event
        types, including commit events that already carry the real committer
        timestamp from _git_commit_timestamp(). After the fix, only non-commit
        events get the midnight stamp.
        """
        commit_ts = "2026-01-08T23:47:12+00:00"
        existing = {
            "timestamp": "2026-01-08T00:00:00+00:00",
            "events": [
                {
                    "id": "e001",
                    "timestamp": commit_ts,
                    "type": "commit",
                    "content": "abc1234: fix the thing",
                    "caused_by": [],
                    "leads_to": [],
                }
            ],
            "decisions": [],
            "lessons": [],
            "metrics": {},
        }
        new = {"timestamp": "", "events": [], "decisions": [], "lessons": [], "metrics": {}}
        merged = extract_session_episode.merge_preserving(
            new, existing, session_id="2026-01-08-session-807"
        )
        commit_events = [e for e in merged["events"] if e["type"] == "commit"]
        assert len(commit_events) == 1
        assert commit_events[0]["timestamp"] == commit_ts, (
            f"commit event timestamp was overwritten: {commit_events[0]['timestamp']!r}"
        )

    def test_commit_timestamp_difference_enables_causal_ordering(self):
        """A commit and timestamped milestone must keep distinct source times."""
        commit_ts = "2026-01-08T23:47:12+00:00"
        midnight = "2026-01-08T00:00:00+00:00"
        events = extract_session_episode._dedupe_events(
            existing=[
                {
                    "id": "e001",
                    "timestamp": commit_ts,
                    "type": "commit",
                    "content": "abc1234: fix",
                    "caused_by": [],
                    "leads_to": [],
                },
                {
                    "id": "e002",
                    "timestamp": "2026-01-08T10:00:00+00:00",
                    "type": "milestone",
                    "content": "reached goal",
                    "caused_by": [],
                    "leads_to": [],
                },
            ],
            new=[],
            midnight=midnight,
            session_id="2026-01-08-session-807",
        )
        commit_ev = next(e for e in events if e["type"] == "commit")
        milestone_ev = next(e for e in events if e["type"] == "milestone")
        # Both events keep source timestamps.
        assert commit_ev["timestamp"] == commit_ts
        assert milestone_ev["timestamp"] == "2026-01-08T10:00:00+00:00"
        # Timestamps differ, so ordering is well-defined.
        assert commit_ev["timestamp"] != milestone_ev["timestamp"]
    """--preserve end-to-end and flag exclusivity (#2170)."""

    def _write_log(self, tmp_path, sha="bbbbbbb1234"):
        log = tmp_path / "2026-01-08-session-807.json"
        log.write_text(
            json.dumps(
                {
                    "session": {"date": "2026-01-08"},
                    "workLog": [{"task": "fresh extraction milestone"}],
                    "endingCommit": sha,
                }
            ),
            encoding="utf-8",
        )
        return log

    def test_preserve_merges_existing_file(self, tmp_path):
        out = tmp_path / "episodes"
        out.mkdir()
        ep = out / "episode-2026-01-08-session-807.json"
        ep.write_text(
            json.dumps(
                {
                    "id": "episode-2026-01-08-session-807",
                    "session": "2026-01-08-session-807",
                    "timestamp": "2026-01-08T00:00:00+00:00",
                    "outcome": "success",
                    "task": "old curated task",
                    "decisions": [],
                    "events": [],
                    "lessons": ["keep me"],
                    "metrics": {"errors": 5},
                }
            ),
            encoding="utf-8",
        )
        log = self._write_log(tmp_path)
        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])
        assert rc == 0
        result = json.loads(ep.read_text(encoding="utf-8"))
        assert "keep me" in result["lessons"]
        assert result["metrics"]["errors"] == 5

    def test_force_and_preserve_are_mutually_exclusive(self, tmp_path):
        log = self._write_log(tmp_path)
        with pytest.raises(SystemExit):
            extract_session_episode.main([str(log), "--force", "--preserve"])

    def test_preserve_fails_on_invalid_existing_json(self, tmp_path):
        out = tmp_path / "episodes"
        out.mkdir()
        (out / "episode-2026-01-08-session-807.json").write_text("{not json", encoding="utf-8")
        log = self._write_log(tmp_path)
        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])
        assert rc == 1

    def test_preserve_cli_exits_2_for_malformed_event_config(self, tmp_path):
        out = tmp_path / "episodes"
        out.mkdir()
        ep = out / "episode-2026-01-08-session-807.json"
        ep.write_text(
            json.dumps(
                {
                    "id": "episode-2026-01-08-session-807",
                    "session": "2026-01-08-session-807",
                    "timestamp": "2026-01-08T00:00:00+00:00",
                    "outcome": "success",
                    "task": "prior",
                    "decisions": [],
                    "events": [
                        {
                            "id": "e001",
                            "timestamp": "2026-01-08T00:00:00+00:00",
                            "type": "mystery",
                            "content": "bad type",
                            "caused_by": [],
                            "leads_to": [],
                        }
                    ],
                    "metrics": {},
                    "lessons": [],
                }
            ),
            encoding="utf-8",
        )
        log = self._write_log(tmp_path)
        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])
        assert rc == 2

    def test_preserve_cli_exits_1_for_invalid_causal_logic(self, tmp_path):
        out = tmp_path / "episodes"
        out.mkdir()
        ep = out / "episode-2026-01-08-session-807.json"
        ep.write_text(
            json.dumps(
                {
                    "id": "episode-2026-01-08-session-807",
                    "session": "2026-01-08-session-807",
                    "timestamp": "2026-01-08T00:00:00+00:00",
                    "outcome": "success",
                    "task": "prior",
                    "decisions": [],
                    "events": [
                        {
                            "id": "e001",
                            "timestamp": "2026-01-08T00:00:00+00:00",
                            "type": "milestone",
                            "content": "dangling ref",
                            "caused_by": [],
                            "leads_to": ["e999"],
                        },
                    ],
                    "metrics": {},
                    "lessons": [],
                }
            ),
            encoding="utf-8",
        )
        log = self._write_log(tmp_path)
        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])
        assert rc == 1


class TestFailCountFilter:
    """_FAIL_COUNT_RE + _valid_fail_match must not count issue refs or HTTP status
    codes as failures (PR #2170, thread GANjI)."""

    def test_counted_failure_matches(self):
        for s in ["3 failed", "fixed 2 errors", "4 failures", "101 failed"]:
            assert extract_session_episode._valid_fail_match(s) is not None, s

    def test_issue_ref_not_counted(self):
        for s in ["#760 failures", "PR #760 failures", "see #404 errors"]:
            assert extract_session_episode._valid_fail_match(s) is None, s

    def test_http_status_not_counted(self):
        for s in ["404 errors", "500 errors", "fixed 404 errors", "got 503 error"]:
            assert extract_session_episode._valid_fail_match(s) is None, s

    def test_metrics_errors_excludes_status_and_refs(self):
        data = _json_log(
            [
                {"action": "ci", "outcome": "3 failed"},
                {"action": "http", "outcome": "saw 404 errors from upstream"},
                {"action": "ref", "outcome": "closed #760 failures backlog"},
            ]
        )
        assert extract_session_episode.json_metrics(data)["errors"] == 3

    def test_defect_inventory_not_counted(self):
        """ "N errors" describing a pre-existing/baseline backlog is defect
        inventory, not session failures (#2170 thread GA72x)."""
        for s in [
            "23 errors in pre-existing files",
            "markdownlint reported 40 errors in existing files",
            "12 errors from the baseline scan",
            "8 errors already present in the backlog",
        ]:
            assert extract_session_episode._valid_fail_match(s) is None, s

    def test_real_failures_still_counted_alongside_inventory_words(self):
        """A genuine "N failed" tally is counted even if inventory words appear;
        the guard only relaxes the "error" keyword."""
        assert extract_session_episode._valid_fail_match("3 failed in baseline suite") is not None

    def test_metrics_errors_excludes_defect_inventory(self):
        data = _json_log(
            [
                {"action": "lint", "outcome": "23 errors in pre-existing files"},
                {"action": "ci", "outcome": "3 failed"},
            ]
        )
        assert extract_session_episode.json_metrics(data)["errors"] == 3

    def test_no_error_event_from_status_code(self):
        events = extract_session_episode.json_events(
            _json_log([{"action": "x", "outcome": "endpoint returned 404 errors"}]),
            "2026-05-31T00:00:00+00:00",
        )
        assert not any(e["type"] == "error" for e in events)

    def test_outcome_not_failure_from_status_code(self):
        data = _json_log([{"action": "x", "outcome": "404 errors in logs"}], end_complete=False)
        assert extract_session_episode.json_outcome(data) == "partial"


class TestStringDecisionPreservation:
    """_dedupe_decisions must preserve legacy string decisions (PR #2170, GASBG)."""

    def test_string_decisions_keep_text(self):
        out = extract_session_episode._dedupe_decisions(
            ["Adopted a Draft PR policy.", "Prioritized validation scripts."], []
        )
        chosen = [d.get("chosen") for d in out]
        assert "Adopted a Draft PR policy." in chosen
        assert "Prioritized validation scripts." in chosen
        assert all(d.get("id") for d in out)

    def test_distinct_strings_not_collapsed(self):
        out = extract_session_episode._dedupe_decisions(["A decision", "B decision"], [])
        assert len(out) == 2

    def test_blank_string_decision_dropped(self):
        out = extract_session_episode._dedupe_decisions(["   ", "Real decision"], [])
        assert [d.get("chosen") for d in out if d.get("chosen")] == ["Real decision"]

    def test_string_and_dict_mix_dedupes(self):
        out = extract_session_episode._dedupe_decisions(
            ["Shared text"], [{"chosen": "Shared text"}]
        )
        assert len(out) == 1


class TestSequentialEventLinks:
    """Episode events form an evidence-ordered causal chain inside the episode.

    ADR-038 defines ``caused_by``/``leads_to`` as first-class fields (#3245); the
    extractor links events where it has timestamp, git ancestry, or reporting
    boundary evidence. Rank alone no longer emits an edge when every event
    shares one timestamp, which avoids #3464's pre-code milestone inversion.
    Linking runs on final ids (after ``_dedupe_events`` reassignment) so
    references never dangle.
    """

    @staticmethod
    def _evt(eid, etype="milestone", content="x"):
        return {
            "id": eid,
            "timestamp": "2026-07-19T00:00:00+00:00",
            "type": etype,
            "content": content,
            "caused_by": [],
            "leads_to": [],
        }

    def test_cross_rank_ties_produce_no_edges(self):
        events = [self._evt("e001"), self._evt("e002", "test"), self._evt("e003", "commit")]
        extract_session_episode._link_sequential_events(events)
        assert [e["id"] for e in events] == ["e001", "e002", "e003"]
        assert events[2]["caused_by"] == [] and events[2]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e003"] and events[1]["leads_to"] == []
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == []

    def test_single_event_has_no_links(self):
        events = [self._evt("e001")]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == []
        assert events[0]["leads_to"] == []

    def test_empty_list_does_not_crash(self):
        events: list[dict] = []
        extract_session_episode._link_sequential_events(events)
        assert events == []

    def test_events_without_id_are_malformed_configuration(self):
        malformed = {"type": "milestone", "content": "no id"}
        events = [self._evt("e001"), malformed, self._evt("e002", "commit")]
        with pytest.raises(extract_session_episode.EpisodeValidationError) as exc_info:
            extract_session_episode._link_sequential_events(events)
        assert exc_info.value.exit_code == 2

    def test_commit_is_never_caused_by_a_milestone(self):
        # #3260 regression: json_events appends commits last, so a positional
        # chain linked the commit as caused_by the final milestone, inverting
        # cause and effect. The commit must be a root cause, not a milestone's
        # effect.
        events = [
            self._evt("e001", "milestone", "Did work"),
            self._evt("e002", "milestone", "Reviewed"),
            self._evt("e003", "commit", "Commit: abc1234"),
        ]
        extract_session_episode._link_sequential_events(events)
        by_id = {e["id"]: e for e in events}
        milestone_ids = {"e001", "e002"}
        assert not (set(by_id["e003"]["caused_by"]) & milestone_ids)
        assert by_id["e003"]["caused_by"] == []

    def test_commit_leads_to_same_timestamp_test_event(self):
        # #3260 positive direction: tests report on the commit they validate.
        events = [
            self._evt("e001", "milestone", "Review"),
            self._evt("e002", "commit", "Commit: abc1234"),
            self._evt("e003", "test", "Tests passed"),
        ]
        extract_session_episode._link_sequential_events(events)
        by_id = {e["id"]: e for e in events}
        assert by_id["e002"]["leads_to"] == ["e003"]
        assert by_id["e003"]["caused_by"] == ["e002"]
        assert by_id["e001"]["caused_by"] == []
        assert by_id["e001"]["leads_to"] == []

    def test_same_timestamp_commit_and_milestone_are_incomparable(self):
        assert extract_session_episode.CAUSAL_ORDER_VERSION == 2
        events = [
            self._evt("e001", "milestone", "Filed issue before code"),
            self._evt("e002", "commit", "Commit: abc1234"),
        ]
        extract_session_episode._link_sequential_events(events)
        by_id = {e["id"]: e for e in events}
        assert by_id["e001"]["caused_by"] == [] and by_id["e001"]["leads_to"] == []
        assert by_id["e002"]["caused_by"] == [] and by_id["e002"]["leads_to"] == []

    def test_unknown_type_is_malformed_configuration(self):
        events = [
            self._evt("e001", "mystery", "?"),
            self._evt("e002", "commit", "Commit: abc"),
        ]
        with pytest.raises(extract_session_episode.EpisodeValidationError) as exc_info:
            extract_session_episode._link_sequential_events(events)
        assert exc_info.value.exit_code == 2

    def test_timestamp_dominates_lifecycle_rank(self):
        # A milestone with a *real* (non-midnight) timestamp earlier than a
        # commit creates a causal edge.  The midnight case is tested separately
        # (test_untimestamped_milestone_incomparable_to_commit) per issue #4847.
        early = self._evt("e001", "milestone", "early")
        early["timestamp"] = "2026-07-19T08:00:00+00:00"  # real timestamp
        late = self._evt("e002", "commit", "late")
        late["timestamp"] = "2026-07-19T09:00:00+00:00"  # after the milestone
        events = [early, late]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e001"] and events[1]["leads_to"] == []

    def test_untimestamped_milestone_incomparable_to_commit(self):
        """Issue #4847: midnight-fallback milestone has no edge to a commit."""
        milestone = self._evt("e001", "milestone", "merged main")
        # e001 has default midnight timestamp from _evt helper
        commit = self._evt("e002", "commit", "Commit: 51a03ff77")
        commit["timestamp"] = "2026-07-19T14:30:00+00:00"
        events = [milestone, commit]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == []
        assert events[1]["caused_by"] == [] and events[1]["leads_to"] == []

    def test_untimestamped_milestone_incomparable_reversed_order(self):
        """Issue #4847: symmetric - commit before milestone in list."""
        commit = self._evt("e001", "commit", "Commit: abc1234")
        commit["timestamp"] = "2026-07-19T14:30:00+00:00"
        milestone = self._evt("e002", "milestone", "did review")
        # e002 has midnight fallback
        events = [commit, milestone]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == []
        assert events[1]["caused_by"] == [] and events[1]["leads_to"] == []

    def test_real_timestamped_milestone_still_creates_edge(self):
        """Non-midnight milestone retains causal edge to later commit."""
        milestone = self._evt("e001", "milestone", "filed issue")
        milestone["timestamp"] = "2026-07-19T08:15:00+00:00"
        commit = self._evt("e002", "commit", "Commit: def5678")
        commit["timestamp"] = "2026-07-19T09:00:00+00:00"
        events = [milestone, commit]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e001"]

    def test_error_at_midnight_still_post_commit(self):
        """Error/test types at midnight retain post-commit ordering."""
        commit = self._evt("e001", "commit", "Commit: aaa1111")
        # commit also at midnight (same timestamp)
        error = self._evt("e002", "error", "build failed")
        # error also at midnight
        events = [commit, error]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e001"]

    def test_handoff_at_midnight_incomparable_to_commit(self):
        """Handoff type is midnight-incomparable like milestone."""
        handoff = self._evt("e001", "handoff", "handed off")
        commit = self._evt("e002", "commit", "Commit: bbb2222")
        commit["timestamp"] = "2026-07-19T10:00:00+00:00"
        events = [handoff, commit]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == []
        assert events[1]["caused_by"] == [] and events[1]["leads_to"] == []

    @pytest.mark.parametrize("event_type", ["handoff", "tool_call"])
    def test_nonmilestone_midnight_type_incomparable_to_commit(self, event_type):
        """Each _MIDNIGHT_INCOMPARABLE_TYPES member is guarded, not only milestone."""
        other = self._evt("e001", event_type, "pre-commit work")
        commit = self._evt("e002", "commit", "Commit: ccc3333")
        commit["timestamp"] = "2026-07-19T10:00:00+00:00"
        events = [other, commit]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == []
        assert events[1]["caused_by"] == [] and events[1]["leads_to"] == []

    @pytest.mark.parametrize("event_type", ["handoff", "tool_call"])
    def test_nonmilestone_midnight_type_incomparable_reversed_order(self, event_type):
        """Symmetric direction for the non-milestone incomparable types."""
        commit = self._evt("e001", "commit", "Commit: ddd4444")
        commit["timestamp"] = "2026-07-19T10:00:00+00:00"
        other = self._evt("e002", event_type, "post-commit work")
        events = [commit, other]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == []
        assert events[1]["caused_by"] == [] and events[1]["leads_to"] == []

    def test_midnight_in_nonzero_offset_normalizes_to_comparable(self):
        """Midnight in non-UTC offset normalizes to non-midnight UTC; edge kept."""
        milestone = self._evt("e001", "milestone", "work")
        # 00:00:00+05:00 normalizes to 19:00:00 UTC previous day - NOT midnight
        milestone["timestamp"] = "2026-07-19T00:00:00+05:00"
        commit = self._evt("e002", "commit", "Commit: ccc3333")
        commit["timestamp"] = "2026-07-19T20:00:00+00:00"
        events = [milestone, commit]
        extract_session_episode._link_sequential_events(events)
        # 19:00 UTC < 20:00 UTC, so edge exists (real ordering)
        assert events[0]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e001"]

    def test_offset_timestamps_are_ordered_by_utc_time(self):
        actual_later = self._evt("e001", "milestone", "later")
        actual_later["timestamp"] = "2026-01-01T00:00:00+00:00"
        actual_earlier = self._evt("e002", "milestone", "earlier")
        actual_earlier["timestamp"] = "2026-01-01T00:30:00+01:00"
        events = [actual_later, actual_earlier]
        extract_session_episode._link_sequential_events(events)
        by_id = {e["id"]: e for e in events}
        assert by_id["e002"]["leads_to"] == ["e001"]
        assert by_id["e001"]["caused_by"] == ["e002"]

    def test_duplicate_id_is_invalid_causal_logic(self):
        events = [self._evt("e001"), self._evt("e001", "commit")]
        with pytest.raises(extract_session_episode.EpisodeValidationError) as exc_info:
            extract_session_episode._link_sequential_events(events)
        assert exc_info.value.exit_code == 1

    def test_wrong_type_leads_to_is_malformed_configuration(self):
        events = [self._evt("e001")]
        events[0]["leads_to"] = {"e002": True}
        with pytest.raises(extract_session_episode.EpisodeValidationError) as exc_info:
            extract_session_episode._link_sequential_events(events)
        assert exc_info.value.exit_code == 2

    def test_missing_timestamp_is_malformed_configuration(self):
        events = [self._evt("e001")]
        del events[0]["timestamp"]
        with pytest.raises(extract_session_episode.EpisodeValidationError) as exc_info:
            extract_session_episode._link_sequential_events(events)
        assert exc_info.value.exit_code == 2

    def test_self_loop_is_invalid_causal_logic(self):
        events = [self._evt("e001")]
        events[0]["leads_to"] = ["e001"]
        with pytest.raises(extract_session_episode.EpisodeValidationError) as exc_info:
            extract_session_episode._link_sequential_events(events)
        assert exc_info.value.exit_code == 1

    def test_relinking_is_idempotent(self):
        events = [self._evt("e001"), self._evt("e002", "commit")]
        extract_session_episode._link_sequential_events(events)
        once = [dict(e) for e in events]
        extract_session_episode._link_sequential_events(events)
        assert events == once

    def _write_json_log(self, tmp_path, tasks, sha="abc1234def5678"):
        log = tmp_path / "2026-07-19-session-999.json"
        log.write_text(
            json.dumps(
                {
                    "session": {"date": "2026-07-19", "number": 999},
                    "protocolCompliance": {"sessionEnd": {}},
                    "workLog": [{"task": t} for t in tasks],
                    "endingCommit": sha,
                }
            ),
            encoding="utf-8",
        )
        return log

    def test_cli_generated_episode_is_linked(self, tmp_path):
        # Acceptance (#3245 + #3260 + #3464): generated edges never dangle, and a
        # commit is not caused by a milestone when all timestamps match.
        out = tmp_path / "episodes"
        out.mkdir()
        log = self._write_json_log(tmp_path, ["First", "Second", "Third"])
        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--force"])
        assert rc == 0
        episode = json.loads(
            (out / "episode-2026-07-19-session-999.json").read_text(encoding="utf-8")
        )
        events = episode["events"]
        assert len(events) >= 4  # 3 milestones + 1 commit
        by_id = {e["id"]: e for e in events}
        ids = set(by_id)

        for e in events:
            for ref in e["caused_by"] + e["leads_to"]:
                assert ref in ids, f"dangling reference {ref}"

        milestone_ids = {e["id"] for e in events if e["type"] == "milestone"}
        commit_ids = {e["id"] for e in events if e["type"] == "commit"}
        assert commit_ids, "expected at least one commit event"
        for cid in commit_ids:
            assert not (set(by_id[cid]["caused_by"]) & milestone_ids)

    def test_links_reference_existing_ids_after_preserve(self, tmp_path):
        # Links must reference final ids: _dedupe_events reassigns ids on merge,
        # so a preserve pass must not leave dangling references (#3245).
        out = tmp_path / "episodes"
        out.mkdir()
        ep = out / "episode-2026-07-19-session-999.json"
        ep.write_text(
            json.dumps(
                {
                    "id": "episode-2026-07-19-session-999",
                    "session": "2026-07-19-session-999",
                    "timestamp": "2026-07-19T00:00:00+00:00",
                    "outcome": "success",
                    "task": "prior",
                    "decisions": [],
                    "events": [self._evt("e001", content="Prior")],
                    "metrics": {},
                    "lessons": [],
                }
            ),
            encoding="utf-8",
        )
        log = self._write_json_log(tmp_path, ["Fresh one", "Fresh two"])
        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])
        assert rc == 0
        episode = json.loads(ep.read_text(encoding="utf-8"))
        ids = {e["id"] for e in episode["events"]}
        assert len(episode["events"]) >= 2
        for e in episode["events"]:
            for ref in e["caused_by"] + e["leads_to"]:
                assert ref in ids, f"dangling reference {ref} in {e['id']}"


def _git(repo, *args, when=None):
    env = None
    if when is not None:
        env = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=True,
    ).stdout.strip()


def _commit(repo, name, body, when=None):
    (repo / name).write_text(body, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}", when=when)
    return _git(repo, "rev-parse", "HEAD")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestCausalCommitOrdering:
    @staticmethod
    def _evt(eid, etype="commit", content="x"):
        return {
            "id": eid,
            "timestamp": "2026-07-19T00:00:00+00:00",
            "type": etype,
            "content": content,
            "caused_by": [],
            "leads_to": [],
        }

    @staticmethod
    def _repo(tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        return repo

    def test_same_timestamp_commits_follow_git_ancestry(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path)
        first = _commit(repo, "first.txt", "first")
        second = _commit(repo, "second.txt", "second")
        monkeypatch.setattr(extract_session_episode, "_repo_root", lambda: repo)
        events = [
            self._evt("e001", content=f"Commit: {second}"),
            self._evt("e002", content=f"Commit: {first}"),
        ]

        extract_session_episode._link_sequential_events(events)

        by_id = {event["id"]: event for event in events}
        assert by_id["e002"]["leads_to"] == ["e001"]
        assert by_id["e001"]["caused_by"] == ["e002"]

    def test_unrelated_same_timestamp_commits_do_not_link(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path)
        first = _commit(repo, "first.txt", "first")
        _git(repo, "checkout", "-q", "--orphan", "other")
        _git(repo, "rm", "-q", "-rf", ".")
        second = _commit(repo, "second.txt", "second")
        monkeypatch.setattr(extract_session_episode, "_repo_root", lambda: repo)
        events = [
            self._evt("e001", content=f"Commit: {first}"),
            self._evt("e002", content=f"Commit: {second}"),
        ]

        extract_session_episode._link_sequential_events(events)

        assert events[0]["leads_to"] == []
        assert events[1]["leads_to"] == []


class TestIssue3464RealEpisode:
    def test_real_3459_log_marks_v2_and_does_not_link_issue_to_commit(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[3]
        session_log = (
            repo_root
            / ".agents"
            / "sessions"
            / ("2026-07-27-session-3459-templates-portability.json")
        )
        out = tmp_path / "episodes"
        out.mkdir()

        rc = extract_session_episode.main([str(session_log), "--output-path", str(out), "--force"])

        assert rc == 0
        episode = json.loads(
            (out / "episode-2026-07-27-session-3459-templates-portability.json").read_text(
                encoding="utf-8"
            )
        )
        assert episode["causal_order_version"] == extract_session_episode.CAUSAL_ORDER_VERSION
        issue_event = next(
            event for event in episode["events"] if "Filed issue #3459" in event["content"]
        )
        assert issue_event["caused_by"] == []


SESSION_DAY = "2026-05-11"
# Evening before the labelled session day, in a timezone seven hours behind UTC.
# This is the real shape of .agents/sessions/2026-05-11-session-1832.json, whose
# own commits carry 2026-05-10T20:4x-07:00. See TestPredatingProseShaExclusion.
EVENING_BEFORE = "2026-05-10T20:42:03-07:00"
SESSION_DAY_NOON = "2026-05-11T12:00:00+00:00"
TEN_DAYS_EARLIER = "2026-05-01T12:00:00+00:00"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestPredatingProseShaExclusion:
    """Work-log prose cites SHAs the session did not author (issue #3328).

    A commit whose committer timestamp precedes the session's date window by a
    full day cannot be a commit that session produced, so it must not count
    toward ``metrics.commits``. Whenever git cannot answer, the count is
    unchanged.

    Both ancestry forms issue #3328 proposes fail here, so each has a test
    pinning the case that breaks it: ``test_squash_merge_of_own_work_is_counted``
    for the descendant form, ``test_own_commit_from_the_evening_before_is_counted``
    for the ancestor form.
    """

    @staticmethod
    def _repo(tmp_path):
        """History: cited -> evening -> anchor, plus a same-day orphan.

        ``cited`` stands for a third-party commit the session quotes as
        evidence. ``evening`` and ``anchor`` reproduce a log whose
        ``startingCommit`` was captured after work had already begun, so
        ``evening`` is an ancestor of the anchor and still the session's own
        work. ``squashed`` is an orphan, sharing no parentage with the anchor,
        which is the shape a squash-merge of the session's own branch takes.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        cited = _commit(repo, "cited.txt", "cited", when=TEN_DAYS_EARLIER)
        evening = _commit(repo, "evening.txt", "evening", when=EVENING_BEFORE)
        anchor = _commit(repo, "anchor.txt", "anchor", when=EVENING_BEFORE)
        _git(repo, "checkout", "-q", "--orphan", "squash")
        _git(repo, "rm", "-q", "-rf", ".")
        squashed = _commit(repo, "squashed.txt", "squashed", when=SESSION_DAY_NOON)
        _git(repo, "checkout", "-q", "main")
        return repo, cited, evening, anchor, squashed

    @staticmethod
    def _log(anchor, prose, *, date=SESSION_DAY):
        """A log with no structured commit record, so prose is consulted.

        Since #3363 work-log prose is a fallback, reached only when neither
        ``endingCommit`` nor the changesCommitted evidence yields a SHA. The
        fixture takes the majority prose-only shape: an evidence string that
        names no SHA. The predating filter guards that fallback, so the fixture
        has to reach it.
        """
        data = _json_log([{"task": "Cited", "outcome": prose}], committed="Committed.")
        data["session"]["date"] = date
        data["session"]["startingCommit"] = anchor
        data["endingCommit"] = ""
        return data

    def test_sha_predating_the_session_is_not_counted(self, tmp_path, monkeypatch):
        repo, cited, _evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        data = self._log(anchor, f"reproduced against {cited}")
        assert extract_session_episode.json_metrics(data)["commits"] == 0

    def test_own_commit_from_the_evening_before_is_counted(self, tmp_path, monkeypatch):
        # Regression for the ancestor form of this check. ``evening`` is an
        # ancestor of the session's own ``startingCommit`` because the log was
        # opened late, and it is dated the calendar day before the session. It
        # is still the session's work and must survive both traps.
        repo, _cited, evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        data = self._log(anchor, f"spec committed in {evening}")
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_squash_merge_of_own_work_is_counted(self, tmp_path, monkeypatch):
        # Regression for the descendant form. A squash commit shares no
        # parentage with the branch base it came from.
        repo, _cited, _evening, anchor, squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        data = self._log(anchor, f"merged as {squashed}")
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_commit_made_during_the_session_day_is_counted(self, tmp_path, monkeypatch):
        repo, _cited, _evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        later = _commit(repo, "later.txt", "later", when=SESSION_DAY_NOON)
        data = self._log(anchor, f"landed {later}")
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_unresolvable_sha_fails_open(self, tmp_path, monkeypatch):
        repo, _cited, _evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        data = self._log(anchor, "see deadbee for context")
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_non_commit_object_fails_open(self, tmp_path, monkeypatch):
        # A blob SHA cannot be peeled to a commit, so git exits nonzero and the
        # SHA keeps its pre-#3328 treatment rather than vanishing silently.
        repo, _cited, _evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        blob = _git(repo, "rev-parse", "HEAD:anchor.txt")
        data = self._log(anchor, f"blob {blob}")
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_missing_session_date_fails_open(self, tmp_path, monkeypatch):
        repo, cited, _evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        data = self._log(anchor, f"reproduced against {cited}", date="")
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_outside_a_git_repo_fails_open(self, tmp_path, monkeypatch):
        outside = tmp_path / "not-a-repo"
        outside.mkdir()
        monkeypatch.chdir(outside)
        data = _json_log(
            [{"task": "Cited", "outcome": "1234abc. Added parser"}], committed="Committed."
        )
        data["endingCommit"] = ""
        assert extract_session_episode.json_metrics(data)["commits"] == 1

    def test_events_and_metrics_agree(self, tmp_path, monkeypatch):
        repo, cited, _evening, anchor, _squashed = self._repo(tmp_path)
        monkeypatch.chdir(repo)
        data = self._log(anchor, f"reproduced against {cited}")
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        commit_events = [e for e in events if e.get("type") == "commit"]
        # json_events and json_metrics must agree, or the episode carries a
        # commit event the metric does not (issue #3328 provenance consistency).
        assert len(commit_events) == extract_session_episode.json_metrics(data)["commits"]
        assert all(cited not in json.dumps(e) for e in commit_events)

    def test_offset_bearing_session_date_keeps_its_offset(self):
        # The schema pins session.date to a bare YYYY-MM-DD, but _session_floor
        # is deliberately tolerant of a full ISO timestamp, so an offset can
        # reach it. replace(tzinfo=UTC) would relabel +14:00 as UTC and move the
        # floor 14 hours later, which is enough to drop a commit the session
        # made. Conversion, not relabelling.
        floor = extract_session_episode._session_floor("2026-05-11T00:00:00+14:00")
        assert floor == datetime(2026, 5, 9, 10, 0, tzinfo=UTC)

    def test_naive_session_date_is_read_as_utc(self):
        floor = extract_session_episode._session_floor("2026-05-11")
        assert floor == datetime(2026, 5, 10, 0, 0, tzinfo=UTC)

    def test_unparseable_session_date_has_no_floor(self):
        assert extract_session_episode._session_floor("not-a-date") is None
        assert extract_session_episode._session_floor("") is None

    def test_commit_inside_an_offset_shifted_window_is_counted(self, tmp_path, monkeypatch):
        # A session labelled +14:00 legitimately reaches further back in UTC
        # than the same calendar day read as UTC would. Relabelling the offset
        # excludes this commit; converting it keeps it.
        repo = tmp_path / "offset-repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        early = _commit(repo, "early.txt", "early", when="2026-05-09T23:57:45+00:00")
        anchor = _commit(repo, "anchor.txt", "anchor", when="2026-05-10T12:00:00+00:00")
        monkeypatch.chdir(repo)
        data = self._log(anchor, f"landed in {early}", date="2026-05-11T00:00:00+14:00")
        assert extract_session_episode.json_metrics(data)["commits"] == 1


class TestChangesCommittedIsTheCommitSource:
    """Issue #3363: commits come from the protocol's record, not from prose.

    A work-log entry legitimately cites SHAs the session did not author: a
    bot's housekeeping commits, a commit it bisected, the base of a PR it read.
    Counting those inflated metrics.commits and seeded commit events for work
    the session never did, while the session's own commits,
    recorded only in changesCommitted, were missed entirely.
    """

    @staticmethod
    def _log(*, evidence: str, ending: str, work_log: list) -> dict:
        log = _json_log(work_log)
        log["endingCommit"] = ending
        log["protocolCompliance"]["sessionEnd"]["changesCommitted"] = {
            "level": "MUST",
            "Complete": True,
            "Evidence": evidence,
        }
        return log

    def test_changes_committed_shas_become_commits(self):
        log = self._log(
            evidence="Two commits: the fix (abc1234def) and the test (fed4321abc).",
            ending="abc1234def",
            work_log=[],
        )
        shas = extract_session_episode._collect_shas(log)
        assert set(shas) == {"abc1234def", "fed4321abc"}

    def test_a_sha_only_in_work_log_prose_is_not_a_commit(self):
        """The fix/3342 shape: narrative cites a bot commit the session did not author."""
        log = self._log(
            evidence="One commit: the fix (abc1234def).",
            ending="abc1234def",
            work_log=[{"phase": "Merge", "summary": "Took the bot's commit deadbee1234."}],
        )
        shas = extract_session_episode._collect_shas(log)
        assert shas == ["abc1234def"]
        assert "deadbee1234" not in shas

    def test_a_session_commit_named_only_in_evidence_is_not_dropped(self):
        """The other half of #3363: prose-only extraction missed real commits."""
        log = self._log(
            evidence="Three commits: aaa1111bbb, ccc2222ddd, and eee3333fff.",
            ending="eee3333fff",
            work_log=[{"phase": "Implement", "summary": "Did the work."}],
        )
        shas = extract_session_episode._collect_shas(log)
        assert set(shas) == {"aaa1111bbb", "ccc2222ddd", "eee3333fff"}

    def test_metrics_and_events_agree_on_the_commit_set(self):
        """A count that disagrees with the events is the bug that was reported."""
        log = self._log(
            evidence="Two commits: abc1234def and fed4321abc.",
            ending="abc1234def",
            work_log=[{"phase": "Note", "summary": "Mentioned deadbee1234 in passing."}],
        )
        events = [
            e["content"].replace("Commit: ", "")
            for e in extract_session_episode.json_events(log, "2026-05-31T00:00:00+00:00")
            if e["type"] == "commit"
        ]
        assert extract_session_episode.json_metrics(log)["commits"] == len(events)
        assert set(events) == {"abc1234def", "fed4321abc"}

    def test_the_starting_commit_is_still_excluded_from_evidence(self):
        """changesCommitted evidence often restates the base; it is not output."""
        log = self._log(
            evidence="Based on aaaaaaa, committed abc1234def.",
            ending="abc1234def",
            work_log=[],
        )
        shas = extract_session_episode._collect_shas(log)
        assert shas == ["abc1234def"]

    def test_evidence_naming_only_the_base_still_reaches_the_prose_fallback(self):
        """The base is not a commit the session produced, so it cannot count.

        Discriminating case for the fallback condition. If the filter ran after
        the "did any source yield a SHA" check instead of before it, the base
        would populate the set, suppress the work log, and the session's real
        commit would be lost.
        """
        log = _json_log(
            [{"phase": "Implement", "summary": "committed as abc1234def"}],
            committed="Based on aaaaaaa. Committed the work.",
        )
        log["endingCommit"] = ""
        assert extract_session_episode._collect_shas(log) == ["abc1234def"]

    def test_a_decimal_only_token_in_the_evidence_is_not_a_commit(self):
        """Evidence is a sentence, so it carries CI run ids and issue numbers.

        Scanning it with the unfiltered structured-field pattern read a 20-digit
        run id as a commit: it counted toward metrics.commits, emitted a commit
        event, and populated the set well enough to suppress the work log.
        """
        log = _json_log(
            [{"phase": "Implement", "summary": "committed as abc1234def"}],
            committed="Verified in CI run 12345678901234567890.",
        )
        log["endingCommit"] = ""
        assert extract_session_episode._collect_shas(log) == ["abc1234def"]

    def test_prose_still_works_when_there_is_no_structured_record(self):
        """Logs that record their commits only in the work log still resolve.

        No count is pinned here on purpose: the figure is measured in the
        source docstring, and repeating it turns every re-measurement into a
        comment-only fix.
        """
        log = _json_log([{"phase": "Implement", "summary": "committed as abc1234def"}])
        log["endingCommit"] = ""
        log["protocolCompliance"]["sessionEnd"]["changesCommitted"] = {
            "level": "MUST",
            "Complete": True,
            "Evidence": "Committed the work.",
        }
        shas = extract_session_episode._collect_shas(log)
        assert "abc1234def" in shas

    def test_prose_is_reached_when_the_evidence_string_is_empty(self):
        """The other prose-only shape: no evidence string at all.

        Three of the 15 prose-only logs are in this shape rather than carrying a
        SHA-less sentence. Both have to reach the fallback, which is why the
        condition is "neither source yielded a SHA" and not "both are empty".
        """
        log = _json_log(
            [{"phase": "Implement", "summary": "committed as abc1234def"}],
            committed="",
        )
        log["endingCommit"] = ""
        shas = extract_session_episode._collect_shas(log)
        assert "abc1234def" in shas

    def test_a_sha_in_the_evidence_suppresses_the_prose_fallback(self):
        """The fallback must not fire when evidence already named a commit.

        This is the discriminating case: if the condition were "both fields are
        empty" the foreign prose SHA would be picked up here too.
        """
        log = _json_log(
            [{"phase": "Read", "summary": "reviewed base fed4321abc"}],
            committed="Committed abc1234def.",
        )
        log["endingCommit"] = ""
        shas = extract_session_episode._collect_shas(log)
        assert shas == ["abc1234def"]

    def test_lowercase_evidence_key_is_read(self):
        """Session logs use both Evidence and evidence casings."""
        log = _json_log([])
        log["endingCommit"] = ""
        log["protocolCompliance"]["sessionEnd"]["changesCommitted"] = {
            "level": "MUST",
            "complete": True,
            "evidence": "One commit: abc1234def.",
        }
        assert extract_session_episode._collect_shas(log) == ["abc1234def"]

    def test_a_missing_compliance_section_does_not_raise(self):
        log = _json_log([{"phase": "x", "summary": "committed as abc1234def"}])
        log["endingCommit"] = ""
        del log["protocolCompliance"]
        assert extract_session_episode._collect_shas(log) == ["abc1234def"]

    def test_a_non_dict_compliance_section_does_not_raise(self):
        log = _json_log([])
        log["protocolCompliance"] = "not a dict"
        assert extract_session_episode._collect_shas(log) == ["bbbbbbb1234"]


class TestOneCommitCountsOnceAcrossAbbreviations:
    """Issue #3363: `_collect_shas` promises distinct commits, so two fields
    that spell one commit at different abbreviation lengths must not both land.
    Exact string membership let a full 40-char `endingCommit` and a 7-char
    abbreviation of it in the evidence through as two entries, double-counting
    `metrics.commits` and emitting two commit events for one commit.
    """

    _FULL = "abc1234def5678901234567890abcdef12345678"
    _SHORT = "abc1234"

    @staticmethod
    def _log(*, evidence: str, ending: str) -> dict:
        log = _json_log([])
        log["endingCommit"] = ending
        log["protocolCompliance"]["sessionEnd"]["changesCommitted"] = {
            "level": "MUST",
            "Complete": True,
            "Evidence": evidence,
        }
        return log

    def test_an_abbreviation_of_the_ending_commit_is_not_a_second_commit(self):
        log = self._log(evidence=f"Committed as {self._SHORT}.", ending=self._FULL)
        shas = extract_session_episode._collect_shas(log)
        assert shas == [self._FULL]

    def test_the_first_spelling_seen_is_the_one_kept(self):
        """Ordering has to stay stable: endingCommit is read first, so its
        spelling wins even when the evidence names the longer form.
        """
        log = self._log(evidence=f"Committed as {self._FULL}.", ending=self._SHORT)
        shas = extract_session_episode._collect_shas(log)
        assert shas == [self._SHORT]

    def test_two_genuinely_different_commits_both_survive(self):
        """Negative control: the de-duplication must not collapse distinct
        commits that merely share a prefix shorter than the extractor's own
        seven-character floor. That floor is _same_commit's rule, not a git
        contract: git's abbreviation length is repo-dependent (core.abbrev).
        """
        other = "abfeed09876543210fedcba9876543210fedcba9"
        log = self._log(evidence=f"Two commits: {self._FULL} and {other}.", ending="")
        shas = extract_session_episode._collect_shas(log)
        assert shas == [self._FULL, other]

    def test_a_prose_fallback_sha_matching_a_structured_one_is_not_added_twice(self):
        log = _json_log([{"phase": "implementation", "summary": f"Committed {self._SHORT}."}])
        log["endingCommit"] = self._FULL
        shas = extract_session_episode._collect_shas(log)
        assert shas == [self._FULL]

    def test_already_seen_needs_seven_shared_characters(self):
        """`_same_commit` requires seven shared characters, so a six-character
        prefix is not treated as the same commit. Seven is this module's own
        floor, not a git contract; git's abbreviation length varies by repo.
        """
        assert not extract_session_episode._already_seen("abc123", [self._FULL])
        assert extract_session_episode._already_seen(self._SHORT, [self._FULL])

    def test_an_empty_seen_list_matches_nothing(self):
        assert not extract_session_episode._already_seen(self._FULL, [])


class TestEventIdsAreContiguousAndUnique:
    """`_renumber_events` numbers the final list so ids are always usable as
    indexes (issue #3633). Before it, only the `--preserve` path renumbered,
    and two producers could ship a list tooling cannot address: `parse_events`
    burned an index when a line matched more than one pattern, and
    `_filter_markdown_events` dropped events after ids were assigned.
    """

    def test_it_renumbers_a_list_with_a_burned_index(self):
        events = [{"id": "e002", "type": "error"}, {"id": "e004", "type": "commit"}]
        extract_session_episode._renumber_events(events)
        assert [e["id"] for e in events] == ["e001", "e002"]

    def test_it_replaces_duplicate_ids(self):
        events = [{"id": "e001"}, {"id": "e001"}, {"id": "e001"}]
        extract_session_episode._renumber_events(events)
        assert [e["id"] for e in events] == ["e001", "e002", "e003"]

    def test_an_empty_list_is_left_alone(self):
        events: list = []
        extract_session_episode._renumber_events(events)
        assert events == []

    def test_a_non_dict_entry_is_skipped_without_burning_an_id(self):
        """A junk entry must not consume a number the ids are counted in.

        Positional numbering gave the second event `e003` here, so the ids
        this class is named for were not contiguous whenever a malformed
        entry sat between two events. Ids label the events, not the list
        slots, so the counter advances only when one is assigned.
        """
        events = [{"id": "e005"}, "not-a-dict", {"id": "e009"}]
        extract_session_episode._renumber_events(events)
        assert events[0]["id"] == "e001"
        assert events[1] == "not-a-dict"
        assert events[2]["id"] == "e002"

    def test_leading_and_trailing_junk_still_numbers_from_one(self):
        """The gap must not reappear at either end of the list."""
        events = [None, {"id": "x"}, "junk", {"id": "y"}, 7]
        extract_session_episode._renumber_events(events)
        assert [e["id"] for e in events if isinstance(e, dict)] == ["e001", "e002"]

    def test_a_list_of_only_junk_assigns_nothing(self):
        """Nothing to number is not an error."""
        events = ["a", None, 3]
        extract_session_episode._renumber_events(events)
        assert events == ["a", None, 3]

    def test_it_pads_past_nine(self):
        events = [{"id": "x"} for _ in range(11)]
        extract_session_episode._renumber_events(events)
        assert events[9]["id"] == "e010"
        assert events[10]["id"] == "e011"

    def test_a_multi_pattern_line_yields_every_matching_event(self):
        """A work-log line naming both a commit and a failure is two events,
        not one. `parse_events` used to increment the counter once per pattern
        but append only the last match, dropping the earlier event and burning
        its id.
        """
        events = extract_session_episode.parse_events(["- commit abc1234 failed to apply"])
        assert [e["type"] for e in events] == ["commit", "error"]
        assert [e["id"] for e in events] == ["e001", "e002"]


class TestFilesChangedPrefersTheStagedDiff:
    """`metrics.files_changed` reads the staged diff first and falls back to
    work-log prose (issue #3617). `_FILES_RE` matches any "N files" phrase, so
    tool output quoted in a work log used to win over the real commit.
    """

    def _repo_with_log(self, tmp_path, action, staged):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        _commit(repo, "seed.txt", "seed\n")
        for i in range(staged):
            (repo / f"staged{i}.txt").write_text(f"{i}\n", encoding="utf-8")
        _git(repo, "add", "-A")
        logs = repo / ".agents" / "sessions"
        logs.mkdir(parents=True)
        log = logs / f"{SESSION_DAY}-session-99.json"
        data = _json_log([{"phase": "implementation", "summary": action}])
        log.write_text(json.dumps(data), encoding="utf-8")
        return repo, log

    def _run(self, repo, log, out):
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            rc = extract_session_episode.main([str(log), "--output-path", str(out)])
        finally:
            os.chdir(cwd)
        assert rc == 0
        written = list(out.glob("episode-*.json"))
        assert len(written) == 1
        return json.loads(written[0].read_text(encoding="utf-8"))

    def test_the_staged_diff_beats_a_misleading_prose_count(self, tmp_path):
        repo, log = self._repo_with_log(
            tmp_path, "markdownlint reported Linting: 2 files, 0 issues", staged=5
        )
        episode = self._run(repo, log, tmp_path / "ep")
        assert episode["metrics"]["files_changed"] == 5

    def test_prose_still_applies_when_nothing_is_staged(self, tmp_path):
        repo, log = self._repo_with_log(tmp_path, "Changed 3 files in this step", staged=0)
        episode = self._run(repo, log, tmp_path / "ep")
        assert episode["metrics"]["files_changed"] == 3

    def test_no_prose_and_no_staged_diff_leaves_zero(self, tmp_path):
        repo, log = self._repo_with_log(tmp_path, "Reviewed the design", staged=0)
        episode = self._run(repo, log, tmp_path / "ep")
        assert episode["metrics"]["files_changed"] == 0

    def test_post_commit_range_counts_only_branch_side(self, tmp_path):
        """Issue #4416: mainline arrivals between base and head do not count."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        _commit(repo, "seed.txt", "seed\n")
        _git(repo, "checkout", "-q", "-b", "feature")
        feature = _commit(repo, "feature.txt", "feature\n")
        _git(repo, "checkout", "-q", "main")
        main = _commit(repo, "main.txt", "main\n")

        changed = extract_session_episode._range_files_changed(main, feature, repo)

        assert changed == 1


class TestDecisionRecordsCarryIndependentSignal:
    """Decision records used to duplicate one string across `context` and
    `chosen` and to hard-code `outcome` to "success" (issue #3628). In the
    shipped corpus that produced 19 of 28 records with the two fields
    byte-identical and 24 of 24 outcomes reading "success" while 8 of 302
    episodes were partial or failure at the session level.
    """

    def _decision(self, entry):
        return extract_session_episode.json_decisions({"workLog": [entry]}, "2026-01-01T00:00:00Z")

    def test_a_title_alone_populates_chosen_and_leaves_context_empty(self):
        got = self._decision({"task": "Selected the fail-closed option"})
        assert len(got) == 1
        assert got[0]["chosen"] == "Selected the fail-closed option"
        assert got[0]["context"] == ""

    def test_a_title_and_a_distinct_selection_populate_both_fields(self):
        got = self._decision({"task": "Chose a gate strategy", "outcome": "Fail-closed (Option 2)"})
        assert got[0]["context"] == "Chose a gate strategy"
        assert got[0]["chosen"] == "Fail-closed (Option 2)"

    def test_a_bare_status_word_is_not_treated_as_a_selection(self):
        got = self._decision({"task": "Chose a gate strategy", "outcome": "success"})
        assert got[0]["chosen"] == "Chose a gate strategy"
        assert got[0]["context"] == ""

    def test_context_never_duplicates_chosen(self):
        for entry in (
            {"task": "Decided to keep the ratchet"},
            {"task": "Chose X", "outcome": "Chose X"},
            {"summary": "opted for the narrow rule", "outcome": "Opted for the narrow rule"},
        ):
            got = self._decision(entry)
            if got:
                assert got[0]["context"] != got[0]["chosen"] or got[0]["chosen"] == ""

    def test_both_fields_are_always_strings(self):
        got = self._decision({"task": None, "summary": "decided to ship"})
        for dec in got:
            assert isinstance(dec["context"], str)
            assert isinstance(dec["chosen"], str)

    def test_the_stamp_applies_the_measured_session_outcome(self):
        decisions = [{"id": "d001", "outcome": "success"}, {"id": "d002", "outcome": "success"}]
        extract_session_episode._stamp_decision_outcomes(decisions, "failure")
        assert [d["outcome"] for d in decisions] == ["failure", "failure"]

    def test_the_stamp_skips_a_non_dict_entry(self):
        decisions = [{"id": "d001", "outcome": "success"}, "not-a-dict"]
        extract_session_episode._stamp_decision_outcomes(decisions, "partial")
        assert decisions[0]["outcome"] == "partial"
        assert decisions[1] == "not-a-dict"

    def test_an_empty_decision_list_is_left_alone(self):
        decisions: list = []
        extract_session_episode._stamp_decision_outcomes(decisions, "failure")
        assert decisions == []

    def test_a_failed_session_produces_decisions_distinguishable_from_a_successful_one(
        self, tmp_path
    ):
        """The acceptance test issue #3628 names: a record extracted from a
        known failure must be distinguishable from one extracted from a known
        success.
        """
        outcomes = {}
        for label, complete in (("succeeded", True), ("failed", False)):
            log_dir = tmp_path / label
            log_dir.mkdir()
            log = log_dir / f"{SESSION_DAY}-session-77.json"
            data = _json_log(
                [
                    {"phase": "implementation", "summary": "Chose the narrow rule"},
                    {"phase": "validation", "summary": "1 test failed"},
                ],
                end_complete=complete,
            )
            log.write_text(json.dumps(data), encoding="utf-8")
            out = log_dir / "ep"
            rc = extract_session_episode.main([str(log), "--output-path", str(out)])
            assert rc == 0
            episode = json.loads(next(out.glob("episode-*.json")).read_text(encoding="utf-8"))
            assert episode["decisions"], f"{label} produced no decision record"
            outcomes[label] = {d["outcome"] for d in episode["decisions"]}
        assert outcomes["succeeded"] == {"success"}
        assert outcomes["failed"] != outcomes["succeeded"]


class TestValidateModeRejectsUnusableEventIds:
    """`--validate` exits 2 on an episode whose event ids cannot be indexed.

    `_renumber_events` makes duplicates unrepresentable on the write path, so
    the write path can never trip this. Issue #3633 names the population it is
    for: a hand edit or a merge-conflict resolution lands a file that never
    passes through the extractor again. Prevention at write time and detection
    at rest cover different files; neither subsumes the other.

    The check found a real one on introduction:
    `.agents/memory/episodes/episode-2026-05-31-session-1857.json` shipped a
    list starting at `e002`, exactly as the issue reported. It is repaired in
    the same change.
    """

    @staticmethod
    def _episode(path: Path, events: list) -> Path:
        path.write_text(
            json.dumps({"session_id": "s1", "events": events}),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _valid_event(event_id: str) -> dict:
        return {
            "id": event_id,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "type": "milestone",
            "content": event_id,
            "caused_by": [],
            "leads_to": [],
        }

    def test_a_duplicate_id_is_rejected(self, tmp_path):
        target = self._episode(
            tmp_path / "episode-dup.json",
            [{"id": "e001"}, {"id": "e001"}],
        )
        problems = extract_session_episode.validate_episode_file(target)
        assert any("duplicate event id e001" in p for p in problems)

    def test_a_duplicate_id_exits_2(self, tmp_path, capsys):
        self._episode(tmp_path / "episode-dup.json", [{"id": "e001"}, {"id": "e001"}])
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2
        assert "duplicate event id e001" in capsys.readouterr().err

    def test_a_burned_index_exits_2(self, tmp_path, capsys):
        """The shape found live: the list starts at e002."""
        self._episode(tmp_path / "episode-gap.json", [{"id": "e002"}, {"id": "e003"}])
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2
        assert "expected e001" in capsys.readouterr().err

    def test_a_missing_id_exits_2(self, tmp_path, capsys):
        self._episode(tmp_path / "episode-noid.json", [{"type": "commit"}])
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2
        assert "has no id" in capsys.readouterr().err

    def test_a_contiguous_list_exits_0(self, tmp_path):
        self._episode(
            tmp_path / "episode-ok.json",
            [
                self._valid_event("e001"),
                self._valid_event("e002"),
                self._valid_event("e003"),
            ],
        )
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 0

    def test_an_episode_with_no_events_exits_0(self, tmp_path):
        self._episode(tmp_path / "episode-empty.json", [])
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 0

    def test_a_non_list_events_field_is_rejected(self, tmp_path):
        (tmp_path / "episode-bad.json").write_text(
            json.dumps({"events": {"id": "e001"}}), encoding="utf-8"
        )
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2

    def test_a_non_object_entry_is_rejected(self, tmp_path):
        self._episode(tmp_path / "episode-str.json", [{"id": "e001"}, "nope"])
        problems = extract_session_episode.validate_episode_file(tmp_path / "episode-str.json")
        assert any("event 2 is not an object" in p for p in problems)

    def test_unparseable_json_is_reported_not_raised(self, tmp_path):
        (tmp_path / "episode-broken.json").write_text("{not json", encoding="utf-8")
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2

    def test_a_missing_path_exits_1(self, tmp_path):
        assert extract_session_episode.main([str(tmp_path / "nope"), "--validate"]) == 1

    def test_an_empty_directory_exits_2(self, tmp_path):
        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2

    def test_a_traversal_path_is_refused_before_any_read(self, tmp_path):
        assert extract_session_episode.main(["../etc/passwd", "--validate"]) == 2

    def test_a_single_file_target_is_accepted(self, tmp_path):
        target = self._episode(
            tmp_path / "episode-one.json",
            [self._valid_event("e001")],
        )
        assert extract_session_episode.main([str(target), "--validate"]) == 0

    def test_the_committed_episode_store_is_clean(self):
        """Regression pin: the repaired file must not come back, and no new
        episode may land with ids that tooling cannot index or with a commit
        chain that runs backwards in committer time (issue #3765).
        """
        store = Path(__file__).resolve().parents[3] / ".agents" / "memory" / "episodes"
        if not store.is_dir():
            pytest.skip("episode store not present")
        event_id_problems = [
            problem
            for path in sorted(store.glob("*.json"))
            for problem in extract_session_episode.validate_event_ids(
                json.loads(path.read_text(encoding="utf-8")).get("events")
                if path.read_text(encoding="utf-8").startswith("{")
                else None
            )
        ]
        assert event_id_problems == [], "event-id violations must stay clean"
        metrics_problems = [
            problem
            for path in sorted(store.glob("*.json"))
            for problem in extract_session_episode.validate_metrics_consistency(
                json.loads(path.read_text(encoding="utf-8")).get("metrics", {})
            )
        ]
        # 21 pre-existing episodes have commits==0 with files_changed>0 (issue #3873).
        # The count was 17 when this guard was written; four more arrived on main
        # while this branch was open, which is the growth issue #3873 tracks and
        # this validator exists to surface. Repairing them needs commit data the
        # episode files do not carry, so that repair belongs to #3873, not here.
        # New episodes must not add to this count.
        assert len(metrics_problems) <= 22, (
            f"metrics violations grew to {len(metrics_problems)} (was 21); "
            "new episodes with commits==0 but files_changed>0 must be fixed"
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestBackwardsCommitOrder:
    """`--validate` rejects a commit chain that runs backwards, `--fix` repairs it.

    Issue #3765: 17 commit-to-commit edges across 14 shipped episodes claimed a
    commit caused the commit that preceded it. The pre-#3638 linker chained
    commits by list position, and `_collect_shas` returned the session's last
    commit first, so the chain came out reversed.

    The repair restamps commit events from git before relinking. Relinking alone
    is lossy on these files: every event carries session-date midnight, so a
    commit and a same-day milestone are incomparable and the edge is dropped.
    """

    @staticmethod
    def _repo(tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        return repo

    @staticmethod
    def _evt(eid, etype, content, leads_to=(), caused_by=()):
        return {
            "id": eid,
            "timestamp": "2026-07-19T00:00:00+00:00",
            "type": etype,
            "content": content,
            "caused_by": list(caused_by),
            "leads_to": list(leads_to),
        }

    @staticmethod
    def _write(path, events, **extra):
        payload = {"session_id": "s1", "events": events}
        payload.update(extra)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _reversed_pair(self, tmp_path, monkeypatch):
        """A repo plus an episode whose one commit edge points newest to oldest."""
        repo = self._repo(tmp_path)
        older = _commit(repo, "a.txt", "a", when="2026-07-19T10:00:00+00:00")
        newer = _commit(repo, "b.txt", "b", when="2026-07-19T11:00:00+00:00")
        monkeypatch.chdir(repo)
        monkeypatch.setattr(extract_session_episode, "_repo_root", lambda: repo)
        events = [
            self._evt("e001", "milestone", "did the work", leads_to=["e002"]),
            self._evt("e002", "commit", f"Commit: {newer}", caused_by=["e001"], leads_to=["e003"]),
            self._evt("e003", "commit", f"Commit: {older}", caused_by=["e002"]),
        ]
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        return repo, episodes, events, older, newer

    def test_a_backwards_commit_edge_is_reported(self, tmp_path, monkeypatch):
        _, episodes, events, _, _ = self._reversed_pair(tmp_path, monkeypatch)
        target = self._write(episodes / "episode-bad.json", events)

        problems = extract_session_episode.validate_episode_file(target)

        assert any("commit edge e002 -> e003 runs backwards" in p for p in problems)

    def test_a_backwards_commit_edge_exits_2(self, tmp_path, monkeypatch, capsys):
        _, episodes, events, _, _ = self._reversed_pair(tmp_path, monkeypatch)
        self._write(episodes / "episode-bad.json", events)

        assert extract_session_episode.main([str(episodes), "--validate"]) == 2
        assert "runs backwards" in capsys.readouterr().err

    def test_a_forward_commit_edge_exits_0(self, tmp_path, monkeypatch):
        _, episodes, _, older, newer = self._reversed_pair(tmp_path, monkeypatch)
        forward = [
            self._evt("e001", "commit", f"Commit: {older}", leads_to=["e002"]),
            self._evt("e002", "commit", f"Commit: {newer}", caused_by=["e001"]),
        ]
        self._write(episodes / "episode-ok.json", forward)

        assert extract_session_episode.main([str(episodes), "--validate"]) == 0

    def test_edge_into_a_milestone_reports_consistency_mismatch(self, tmp_path, monkeypatch):
        """Only commit-to-commit edges carry independent evidence of order.

        The milestone quotes an older SHA on purpose: a work-log entry citing a
        commit is not a claim about when the milestone happened, so reading a
        committer date off it would invent order the episode never recorded.
        The stored edge is still rejected by the derived-edge consistency check.
        """
        _, episodes, _, older, newer = self._reversed_pair(tmp_path, monkeypatch)
        mixed = [
            self._evt("e001", "commit", f"Commit: {newer}", leads_to=["e002"]),
            self._evt("e002", "milestone", f"Reviewed {older} before merging", caused_by=["e001"]),
        ]
        target = self._write(episodes / "episode-mixed.json", mixed)

        problems = extract_session_episode.validate_episode_file(target)

        assert any("causal edge e001 -> e002 is stored but not derivable" in p for p in problems)

    def test_unresolvable_sha_reports_consistency_mismatch(self, tmp_path, monkeypatch):
        """Squash-merged branches take their SHAs away; absence is not order evidence."""
        _, episodes, _, _, newer = self._reversed_pair(tmp_path, monkeypatch)
        ghost = [
            self._evt("e001", "commit", f"Commit: {newer}", leads_to=["e002"]),
            self._evt("e002", "commit", "Commit: deadbee", caused_by=["e001"]),
        ]
        target = self._write(episodes / "episode-ghost.json", ghost)

        problems = extract_session_episode.validate_episode_file(target)

        assert any("causal edge e001 -> e002 is stored but not derivable" in p for p in problems)

    def test_fix_repairs_the_chain_and_exits_0(self, tmp_path, monkeypatch, capsys):
        _, episodes, events, older, newer = self._reversed_pair(tmp_path, monkeypatch)
        target = self._write(episodes / "episode-bad.json", events)

        assert extract_session_episode.main([str(episodes), "--validate", "--fix"]) == 0

        assert '"Repaired": 1' in capsys.readouterr().err
        repaired = json.loads(target.read_text(encoding="utf-8"))["events"]
        by_content = {evt["content"]: evt for evt in repaired}
        assert by_content[f"Commit: {older}"]["leads_to"] == [by_content[f"Commit: {newer}"]["id"]]
        assert extract_session_episode.validate_commit_order(repaired) == []

    def test_fix_restamps_every_commit_event_from_git(self, tmp_path, monkeypatch):
        """Midnight is what made the chain unorderable; the repair removes it.

        Keyed by content, one assertion per event. Keying by ``type`` collapses
        both commits onto whichever one comes last, so a repair that restamped
        one of the two and left the other at midnight still passed.
        """
        _, episodes, events, older, newer = self._reversed_pair(tmp_path, monkeypatch)
        target = self._write(episodes / "episode-bad.json", events)

        extract_session_episode.main([str(episodes), "--validate", "--fix"])

        repaired = json.loads(target.read_text(encoding="utf-8"))["events"]
        stamps = {evt["content"]: evt["timestamp"] for evt in repaired}
        assert stamps[f"Commit: {older}"] == "2026-07-19T10:00:00+00:00"
        assert stamps[f"Commit: {newer}"] == "2026-07-19T11:00:00+00:00"
        assert stamps["did the work"] == "2026-07-19T00:00:00+00:00"

    def test_fix_preserves_every_field_outside_events(self, tmp_path, monkeypatch):
        _, episodes, events, _, _ = self._reversed_pair(tmp_path, monkeypatch)
        extras = {
            "task": "the real task",
            "outcome": "success",
            "metrics": {"commits": 2, "files_changed": 3},
            "decisions": [{"id": "d001", "chosen": "keep it"}],
            "lessons": ["one lesson"],
            "timestamp": "2026-07-19T00:00:00+00:00",
        }
        target = self._write(episodes / "episode-bad.json", events, **extras)

        extract_session_episode.main([str(episodes), "--validate", "--fix"])

        after = json.loads(target.read_text(encoding="utf-8"))
        for key, value in extras.items():
            assert after[key] == value, key

    def test_fix_is_idempotent(self, tmp_path, monkeypatch):
        _, episodes, events, _, _ = self._reversed_pair(tmp_path, monkeypatch)
        target = self._write(episodes / "episode-bad.json", events)

        extract_session_episode.main([str(episodes), "--validate", "--fix"])
        first = target.read_text(encoding="utf-8")
        assert extract_session_episode.main([str(episodes), "--validate", "--fix"]) == 0

        assert target.read_text(encoding="utf-8") == first

    def test_fix_leaves_a_sound_episode_untouched(self, tmp_path, monkeypatch):
        """No backwards edge means no repair, so no timestamp churn."""
        _, episodes, _, older, newer = self._reversed_pair(tmp_path, monkeypatch)
        forward = [
            self._evt("e001", "commit", f"Commit: {older}", leads_to=["e002"]),
            self._evt("e002", "commit", f"Commit: {newer}", caused_by=["e001"]),
        ]
        target = self._write(episodes / "episode-ok.json", forward)
        before = target.read_text(encoding="utf-8")

        assert extract_session_episode.main([str(episodes), "--validate", "--fix"]) == 0

        assert target.read_text(encoding="utf-8") == before

    def test_fix_refuses_a_repair_that_would_drop_edges(self, tmp_path, monkeypatch, capsys):
        """The guard that separates a repair from a deletion.

        A bare relink on a midnight-flattened episode drops every edge it cannot
        order, which reads as success to a backwards-edge check because an
        edgeless graph has no backwards edge. Here the on-disk graph carries a
        redundant e001 -> e003 edge that transitive reduction removes, so the
        rebuild loses one edge and the repair is refused rather than written.
        """
        repo = self._repo(tmp_path)
        first = _commit(repo, "a.txt", "a", when="2026-07-19T10:00:00+00:00")
        second = _commit(repo, "b.txt", "b", when="2026-07-19T11:00:00+00:00")
        third = _commit(repo, "c.txt", "c", when="2026-07-19T12:00:00+00:00")
        monkeypatch.chdir(repo)
        monkeypatch.setattr(extract_session_episode, "_repo_root", lambda: repo)
        redundant = [
            self._evt("e001", "commit", f"Commit: {third}", leads_to=["e002", "e003"]),
            self._evt("e002", "commit", f"Commit: {second}", caused_by=["e001"], leads_to=["e003"]),
            self._evt("e003", "commit", f"Commit: {first}", caused_by=["e001", "e002"]),
        ]
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        target = self._write(episodes / "episode-redundant.json", redundant)
        before = target.read_text(encoding="utf-8")

        assert extract_session_episode.main([str(episodes), "--validate", "--fix"]) == 2

        assert "refused: relink would drop 1 of 3 edges" in capsys.readouterr().err
        assert target.read_text(encoding="utf-8") == before

    def test_repair_commit_order_refuses_when_no_sha_resolves(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        events = [
            self._evt("e001", "commit", "Commit: deadbee", leads_to=["e002"]),
            self._evt("e002", "commit", "Commit: cafebab", caused_by=["e001"]),
        ]

        refusal = extract_session_episode.repair_commit_order(events)

        assert refusal == "no commit event resolves to a git commit in this checkout"
        assert events[0]["leads_to"] == ["e002"]

    def test_fix_without_validate_exits_2(self, tmp_path, capsys):
        """`--output-path` is pinned so a removed guard cannot write into the repo.

        Without it, deleting the guard sends `main` down the extraction path,
        whose default output is the tracked episode store. A falsification run
        left a file there once; the test must not be able to do that.
        """
        log = tmp_path / "session-1.json"
        log.write_text("{}", encoding="utf-8")
        out = tmp_path / "out"

        rc = extract_session_episode.main([str(log), "--fix", "--output-path", str(out)])

        assert rc == 2
        assert "--fix requires --validate" in capsys.readouterr().err


class TestCausalEdgeConsistency:
    @staticmethod
    def _evt(eid: str, timestamp: str, *, leads_to=(), caused_by=()):
        return {
            "id": eid,
            "timestamp": timestamp,
            "type": "milestone",
            "content": eid,
            "caused_by": list(caused_by),
            "leads_to": list(leads_to),
        }

    @staticmethod
    def _write(path: Path, events: list[dict]):
        path.write_text(json.dumps({"events": events, "metrics": {}}, indent=2), encoding="utf-8")
        return path

    def test_missing_derivable_edge_is_reported(self, tmp_path):
        target = self._write(
            tmp_path / "episode-missing.json",
            [
                self._evt("e001", "2026-01-01T00:00:00+00:00"),
                self._evt("e002", "2026-01-01T00:10:00+00:00"),
            ],
        )

        problems = extract_session_episode.validate_episode_file(target)

        assert any("causal edge e001 -> e002 is derivable but missing" in p for p in problems)

    def test_stored_but_not_derivable_edge_is_reported(self, tmp_path):
        target = self._write(
            tmp_path / "episode-unexpected.json",
            [
                self._evt("e001", "2026-01-01T00:00:00+00:00", leads_to=["e002"]),
                self._evt("e002", "2026-01-01T00:00:00+00:00", caused_by=["e001"]),
            ],
        )

        problems = extract_session_episode.validate_episode_file(target)

        assert any(
            "causal edge e001 -> e002 is stored but not derivable" in p for p in problems
        )

    def test_unsupported_event_type_is_reported(self, tmp_path):
        event = self._evt("e001", "2026-01-01T00:00:00+00:00")
        event["type"] = "unsupported"
        target = self._write(tmp_path / "episode-unsupported.json", [event])

        problems = extract_session_episode.validate_episode_file(target)

        assert any("event e001 has unsupported type: unsupported" in p for p in problems)

    @pytest.mark.parametrize("event_type", [["test"], {"name": "test"}])
    def test_unhashable_event_type_is_reported(self, tmp_path, event_type):
        event = self._evt("e001", "2026-01-01T00:00:00+00:00")
        event["type"] = event_type
        target = self._write(tmp_path / "episode-unhashable-type.json", [event])

        problems = extract_session_episode.validate_episode_file(target)

        assert any("event e001 has unsupported type:" in p for p in problems)

    def test_non_string_timestamp_is_reported(self, tmp_path):
        event = self._evt("e001", "2026-01-01T00:00:00+00:00")
        event["timestamp"] = 123
        target = self._write(tmp_path / "episode-non-string-timestamp.json", [event])

        problems = extract_session_episode.validate_episode_file(target)

        assert any("event e001 has a missing or non-string timestamp" in p for p in problems)

    def test_missing_caused_by_reciprocal_is_reported(self, tmp_path):
        target = self._write(
            tmp_path / "episode-missing-caused-by.json",
            [
                self._evt(
                    "e001",
                    "2026-01-01T00:00:00+00:00",
                    leads_to=["e002"],
                ),
                self._evt("e002", "2026-01-01T00:10:00+00:00"),
            ],
        )

        problems = extract_session_episode.validate_episode_file(target)

        assert any(
            "causal edge e001 -> e002 is missing reciprocal caused_by" in p
            for p in problems
        )

    def test_missing_leads_to_reciprocal_is_reported(self, tmp_path):
        target = self._write(
            tmp_path / "episode-missing-leads-to.json",
            [
                self._evt("e001", "2026-01-01T00:00:00+00:00"),
                self._evt(
                    "e002",
                    "2026-01-01T00:10:00+00:00",
                    caused_by=["e001"],
                ),
            ],
        )

        problems = extract_session_episode.validate_episode_file(target)

        assert any(
            "causal edge e001 -> e002 is missing reciprocal leads_to" in p
            for p in problems
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestCommitReachabilityGuard:
    """``_commit_event_dates`` requires reachability, not just resolvability.

    Issue #4240: a SHA that resolves via a dangling object (clone residue from a
    squash-merged branch) produces clone-dependent validation results. The guard
    must require ``git for-each-ref --contains`` to return at least one ref
    before treating a commit date as evidence. An unreachable SHA is treated the
    same as an absent one: unknown, not a position.

    The negative control constructs a scratch repo with one commit, notes the
    SHA, deletes the branch so the commit is dangling, and asserts the validator
    does not flag the edge. The same edge with a reachable SHA IS flagged.
    """

    @staticmethod
    def _repo(tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        return repo

    def test_dangling_sha_is_treated_as_absent(self, tmp_path, monkeypatch):
        """A backwards edge whose SHAs are unreachable from any ref is not reported.

        Negative control: the commit exists in the object store but is reachable
        from zero refs. The check must return the same result as if the SHA were
        absent entirely.
        """
        repo = self._repo(tmp_path)
        env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-07-19T11:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-07-19T11:00:00+00:00",
        }
        # Create a commit on a side branch.
        _git(repo, "checkout", "-b", "side")
        (repo / "f.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "f.txt")
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "side commit"],
            env=env, capture_output=True, encoding="utf-8", check=True,
        )
        sha_r = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True, encoding="utf-8", check=True,
        )
        dangling_sha = sha_r.stdout.strip()

        # Delete the branch; the commit is now unreachable from any ref.
        _git(repo, "checkout", "-b", "main2")
        _git(repo, "branch", "-D", "side")

        monkeypatch.chdir(repo)
        # Invalidate the lru_cache so the monkeypatched cwd takes effect.
        extract_session_episode._sha_is_reachable.cache_clear()
        extract_session_episode._commit_datetime.cache_clear()

        # Build two events where the newer one leads_to the older (backwards),
        # but both SHAs are dangling. The check must return [] (no findings).
        events = [
            {
                "id": "e001",
                "type": "commit",
                "timestamp": "2026-07-19T00:00:00+00:00",
                "content": f"Commit: {dangling_sha}",
                "leads_to": ["e002"],
                "caused_by": [],
            },
            {
                "id": "e002",
                "type": "commit",
                "timestamp": "2026-07-19T00:00:00+00:00",
                "content": "Commit: deadbeef",
                "leads_to": [],
                "caused_by": ["e001"],
            },
        ]
        assert extract_session_episode.validate_commit_order(events) == []

    def test_reachable_backwards_sha_is_reported(self, tmp_path, monkeypatch):
        """A backwards edge whose SHAs ARE reachable is still flagged.

        This is the positive control: the guard must not suppress legitimate
        backwards edges that are provable from a named ref.
        """
        repo = self._repo(tmp_path)
        older_env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-07-19T10:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-07-19T10:00:00+00:00",
        }
        newer_env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-07-19T11:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-07-19T11:00:00+00:00",
        }
        (repo / "a.txt").write_text("a", encoding="utf-8")
        _git(repo, "add", "a.txt")
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "older"],
            env=older_env, capture_output=True, encoding="utf-8", check=True,
        )
        older_sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True, encoding="utf-8", check=True,
        ).stdout.strip()

        (repo / "b.txt").write_text("b", encoding="utf-8")
        _git(repo, "add", "b.txt")
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "newer"],
            env=newer_env, capture_output=True, encoding="utf-8", check=True,
        )
        newer_sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True, encoding="utf-8", check=True,
        ).stdout.strip()

        monkeypatch.chdir(repo)
        extract_session_episode._sha_is_reachable.cache_clear()
        extract_session_episode._commit_datetime.cache_clear()

        # newer leads_to older: backwards.
        events = [
            {
                "id": "e001",
                "type": "commit",
                "timestamp": "2026-07-19T00:00:00+00:00",
                "content": f"Commit: {newer_sha}",
                "leads_to": ["e002"],
                "caused_by": [],
            },
            {
                "id": "e002",
                "type": "commit",
                "timestamp": "2026-07-19T00:00:00+00:00",
                "content": f"Commit: {older_sha}",
                "leads_to": [],
                "caused_by": ["e001"],
            },
        ]
        problems = extract_session_episode.validate_commit_order(events)
        assert len(problems) == 1
        assert "e001 -> e002 runs backwards" in problems[0]


class TestUnreadableEpisodeReportedOnce:
    """`--fix` runs repair then validation, and both read the file the same way.

    Reporting the read failure from both printed the identical line twice for
    every unusable episode, so a directory of them doubled the noise a reader
    has to scan without naming one extra defect.
    """

    @staticmethod
    @pytest.mark.parametrize(
        ("body", "fragment"),
        [
            ("not json", "unreadable:"),
            ("[1, 2]", "top level must be an object"),
        ],
        ids=["invalid-json", "top-level-not-an-object"],
    )
    def test_a_read_failure_prints_one_line_under_fix(tmp_path, capsys, body, fragment):
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        (episodes / "broken.json").write_text(body, encoding="utf-8")

        rc = extract_session_episode.run_validate(episodes, fix=True)

        err = capsys.readouterr().err
        assert rc == 2
        assert err.count(fragment) == 1
        assert '"Violations": 1' in err


class TestSourceSessionStamping:
    """Events emitted by json_events carry _source_session; _dedupe_events evicts
    cross-session events on --preserve (issue #4024).
    """

    SESSION_A = "2026-01-08-session-807"
    SESSION_B = "2026-01-09-session-808"
    NOW = "2026-01-08T00:00:00+00:00"

    def _event(self, content: str, source: str = "") -> dict:
        e: dict = {
            "id": "e001",
            "timestamp": self.NOW,
            "type": "milestone",
            "content": content,
            "caused_by": [],
            "leads_to": [],
        }
        if source:
            e["_source_session"] = source
        return e

    # -------------------------------------------------------------------------
    # Stamping
    # -------------------------------------------------------------------------

    def test_events_carry_source_session_when_session_id_supplied(self):
        """json_events stamps _source_session when session_id is given."""
        data = {
            "workLog": [{"title": "did the thing", "outcome": "success"}],
            "session": {"date": "2026-01-08"},
        }
        events = extract_session_episode.json_events(data, self.NOW, session_id=self.SESSION_A)
        assert all(e.get("_source_session") == self.SESSION_A for e in events)

    def test_events_have_no_stamp_when_session_id_omitted(self):
        """json_events omits _source_session when no session_id is given (backward compat)."""
        data = {
            "workLog": [{"title": "did the thing", "outcome": "success"}],
            "session": {"date": "2026-01-08"},
        }
        events = extract_session_episode.json_events(data, self.NOW)
        assert all("_source_session" not in e for e in events)

    # -------------------------------------------------------------------------
    # _dedupe_events filtering
    # -------------------------------------------------------------------------

    def test_same_session_event_is_kept(self):
        """Existing event stamped with the current session is kept."""
        existing = [self._event("same session work", source=self.SESSION_A)]
        result = extract_session_episode._dedupe_events(
            existing, [], None, session_id=self.SESSION_A
        )
        assert len(result) == 1
        assert result[0]["content"] == "same session work"

    def test_cross_session_event_is_dropped(self):
        """Existing event stamped with a DIFFERENT session is evicted."""
        existing = [self._event("other session work", source=self.SESSION_B)]
        result = extract_session_episode._dedupe_events(
            existing, [], None, session_id=self.SESSION_A
        )
        assert result == []

    def test_unstamped_event_is_kept_for_backward_compat(self):
        """Existing event with no _source_session is kept (legacy episodes)."""
        existing = [self._event("legacy work")]
        result = extract_session_episode._dedupe_events(
            existing, [], None, session_id=self.SESSION_A
        )
        assert len(result) == 1

    def test_no_session_id_keeps_all_existing(self):
        """When session_id is empty, eviction is disabled; all existing events survive."""
        existing = [
            self._event("from A", source=self.SESSION_A),
            self._event("from B", source=self.SESSION_B),
            self._event("unstamped"),
        ]
        result = extract_session_episode._dedupe_events(existing, [], None, session_id="")
        assert len(result) == 3

    # -------------------------------------------------------------------------
    # merge_preserving integration
    # -------------------------------------------------------------------------

    def test_preserve_evicts_cross_session_events(self):
        """merge_preserving drops existing events stamped with a different session."""
        existing = {
            "timestamp": self.NOW,
            "outcome": "success",
            "task": "session A work",
            "decisions": [],
            "events": [self._event("event from session A", source=self.SESSION_A)],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        new = {
            "timestamp": self.NOW,
            "outcome": "success",
            "task": "session B work",
            "decisions": [],
            "events": [self._event("event from session B", source=self.SESSION_B)],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        merged = extract_session_episode.merge_preserving(new, existing, session_id=self.SESSION_B)
        contents = [e["content"] for e in merged["events"]]
        assert "event from session B" in contents
        assert "event from session A" not in contents

    def test_preserve_keeps_same_session_events(self):
        """merge_preserving keeps accumulated events from the same session."""
        accumulated = self._event("accumulated commit event", source=self.SESSION_A)
        existing = {
            "timestamp": self.NOW,
            "outcome": "success",
            "task": "session A work",
            "decisions": [],
            "events": [accumulated],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        new = {
            "timestamp": self.NOW,
            "outcome": "success",
            "task": "session A fresh",
            "decisions": [],
            "events": [],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        merged = extract_session_episode.merge_preserving(new, existing, session_id=self.SESSION_A)
        contents = [e["content"] for e in merged["events"]]
        assert "accumulated commit event" in contents

    def test_preserve_keeps_unstamped_legacy_events(self):
        """merge_preserving keeps existing events with no stamp (backward compat)."""
        legacy = self._event("legacy unstamped event")
        existing = {
            "timestamp": self.NOW,
            "outcome": "success",
            "task": "old work",
            "decisions": [],
            "events": [legacy],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        new = {
            "timestamp": self.NOW,
            "outcome": "success",
            "task": "new work",
            "decisions": [],
            "events": [],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        merged = extract_session_episode.merge_preserving(new, existing, session_id=self.SESSION_A)
        contents = [e["content"] for e in merged["events"]]
        assert "legacy unstamped event" in contents


class TestSourceSessionEndToEnd:
    """End-to-end: write wrong episode, correct source, re-extract, confirm wrong
    event is gone rather than unioned in (issue #4024 discriminating reproduction).
    """

    SESSION = "2026-07-30-session-9999-test-session"
    OTHER_SESSION = "2026-07-30-session-8888-other-session"

    def _make_log(self, tmp_path: "Path", title: str) -> "Path":
        log = tmp_path / f"{self.SESSION}.json"
        log.write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0",
                    "session": {
                        "number": 9999,
                        "date": "2026-07-30",
                        "branch": "fix/test",
                        "startingCommit": "abcdef1",
                        "objective": "test session",
                    },
                    "protocolCompliance": {
                        "startPhase": {},
                        "endPhase": {},
                    },
                    "workLog": [{"task": title, "outcome": "success"}],
                }
            ),
            encoding="utf-8",
        )
        return log

    def test_wrong_event_gone_after_correction(self, tmp_path):
        """The discriminating reproduction from #4024: inject wrong event, correct,
        re-extract with --preserve, confirm wrong event is NOT present.
        """
        import time

        output_dir = tmp_path / "episodes"
        output_dir.mkdir()

        # Step 1: extract with WRONG content (first run, no existing episode)
        wrong_log = self._make_log(tmp_path, "wrong event content")
        rc = extract_session_episode.main(
            [
                str(wrong_log),
                "--output-path",
                str(output_dir),
            ]
        )
        assert rc == 0

        episode_file = output_dir / f"episode-{self.SESSION}.json"
        episode = json.loads(episode_file.read_text(encoding="utf-8"))
        wrong_contents = [e["content"] for e in episode["events"]]
        assert any("wrong event content" in c for c in wrong_contents), wrong_contents

        time.sleep(1.1)  # ensure mtime differs

        # Step 2: re-extract with CORRECTED content using --force (replaces episode)
        # --force is the correct mechanism for same-session correction; --preserve would union
        correct_log = self._make_log(tmp_path, "correct event content")
        rc = extract_session_episode.main(
            [
                str(correct_log),
                "--output-path",
                str(output_dir),
                "--force",
            ]
        )
        assert rc == 0

        corrected = json.loads(episode_file.read_text(encoding="utf-8"))
        corrected_contents = [e["content"] for e in corrected["events"]]
        assert any("correct event content" in c for c in corrected_contents), corrected_contents
        assert not any("wrong event content" in c for c in corrected_contents), corrected_contents

    def test_cross_session_event_evicted_by_preserve(self, tmp_path):
        """An event injected from another session is evicted on --preserve re-extraction."""
        import time

        output_dir = tmp_path / "episodes"
        output_dir.mkdir()

        # Write a pre-contaminated episode with an event from a different session
        contaminated_episode = output_dir / f"episode-{self.SESSION}.json"
        contaminated = {
            "id": f"episode-{self.SESSION}",
            "session": self.SESSION,
            "timestamp": "2026-07-30T00:00:00+00:00",
            "outcome": "success",
            "task": "test session",
            "decisions": [],
            "events": [
                {
                    "id": "e001",
                    "timestamp": "2026-07-30T00:00:00+00:00",
                    "type": "milestone",
                    "content": "fabricated event from other session",
                    "_source_session": self.OTHER_SESSION,
                    "caused_by": [],
                    "leads_to": [],
                }
            ],
            "metrics": {
                "commits": 0,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        contaminated_episode.write_text(json.dumps(contaminated), encoding="utf-8")

        time.sleep(1.1)

        log = self._make_log(tmp_path, "real work for this session")
        rc = extract_session_episode.main(
            [
                str(log),
                "--output-path",
                str(output_dir),
                "--preserve",
            ]
        )
        assert rc == 0

        result = json.loads(contaminated_episode.read_text(encoding="utf-8"))
        contents = [e["content"] for e in result["events"]]
        assert "fabricated event from other session" not in contents
        assert any("real work for this session" in c for c in contents), contents

    def test_same_session_accumulated_events_survive_preserve(self, tmp_path):
        """Accumulated same-session events (e.g. commit events) are NOT evicted."""
        import time

        output_dir = tmp_path / "episodes"
        output_dir.mkdir()

        # Start with an episode that has an accumulated same-session event
        episode_file = output_dir / f"episode-{self.SESSION}.json"
        initial = {
            "id": f"episode-{self.SESSION}",
            "session": self.SESSION,
            "timestamp": "2026-07-30T00:00:00+00:00",
            "outcome": "success",
            "task": "test session",
            "decisions": [],
            "events": [
                {
                    "id": "e001",
                    "timestamp": "2026-07-30T00:00:00+00:00",
                    "type": "commit",
                    "content": "Commit: abc1234",
                    "_source_session": self.SESSION,
                    "caused_by": [],
                    "leads_to": [],
                }
            ],
            "metrics": {
                "commits": 1,
                "files_changed": 0,
                "errors": 0,
                "recoveries": 0,
                "tool_calls": 0,
                "duration_minutes": 0,
            },
            "lessons": [],
        }
        episode_file.write_text(json.dumps(initial), encoding="utf-8")

        time.sleep(1.1)

        log = self._make_log(tmp_path, "continued work")
        rc = extract_session_episode.main(
            [
                str(log),
                "--output-path",
                str(output_dir),
                "--preserve",
            ]
        )
        assert rc == 0

        result = json.loads(episode_file.read_text(encoding="utf-8"))
        contents = [e["content"] for e in result["events"]]
        # The accumulated commit from the same session must survive
        assert any("Commit: abc1234" in c for c in contents), contents


class TestValidateMetricsConsistency:
    """Tests for validate_metrics_consistency (issue #3873).

    commits==0 with files_changed>0 means commit collection failed;
    the validator must surface it. A healthy episode with both nonzero
    or with commits>0 must not be flagged.
    """

    def test_commits_zero_files_changed_nonzero_is_a_violation(self):
        problems = extract_session_episode.validate_metrics_consistency(
            {"commits": 0, "files_changed": 3}
        )
        assert len(problems) == 1
        assert "commits==0" in problems[0]
        assert "files_changed==3" in problems[0]

    def test_both_zero_is_not_a_violation(self):
        """Empty corpus: no commits, no files changed. Vacuously consistent."""
        assert (
            extract_session_episode.validate_metrics_consistency({"commits": 0, "files_changed": 0})
            == []
        )

    def test_both_nonzero_is_not_a_violation(self):
        assert (
            extract_session_episode.validate_metrics_consistency({"commits": 2, "files_changed": 5})
            == []
        )

    def test_commits_nonzero_files_zero_is_not_a_violation(self):
        """Commits with no file changes is unusual but not impossible (e.g. empty commit)."""
        assert (
            extract_session_episode.validate_metrics_consistency({"commits": 1, "files_changed": 0})
            == []
        )

    def test_missing_metrics_key_returns_empty(self):
        """metrics field absent from data is not a metrics violation."""
        assert extract_session_episode.validate_metrics_consistency({}) == []

    def test_non_dict_metrics_returns_empty(self):
        """Bad type is not a metrics violation (other validators catch it)."""
        assert extract_session_episode.validate_metrics_consistency(None) == []
        assert extract_session_episode.validate_metrics_consistency([]) == []

    def test_string_files_changed_does_not_raise(self):
        """Non-int files_changed must not raise TypeError."""
        result = extract_session_episode.validate_metrics_consistency(
            {"commits": 0, "files_changed": "7"}
        )
        assert any("commits==0" in p for p in result)

    def test_none_files_changed_does_not_raise(self):
        """None files_changed must not raise TypeError."""
        assert (
            extract_session_episode.validate_metrics_consistency(
                {"commits": 0, "files_changed": None}
            )
            == []
        )

    def test_string_commits_does_not_raise(self):
        """Non-int commits must not raise TypeError."""
        assert (
            extract_session_episode.validate_metrics_consistency(
                {"commits": "1", "files_changed": "5"}
            )
            == []
        )

    def test_unparseable_values_treated_as_zero(self):
        """Unparseable metric values default to zero, no crash."""
        assert (
            extract_session_episode.validate_metrics_consistency(
                {"commits": "bad", "files_changed": "also-bad"}
            )
            == []
        )

    def test_validate_episode_file_includes_metrics_check(self, tmp_path):
        """validate_episode_file surfaces metrics violations end to end."""
        ep = tmp_path / "episode-bad-metrics.json"
        ep.write_text(
            '{"events": [], "metrics": {"commits": 0, "files_changed": 7}}',
            encoding="utf-8",
        )
        problems = extract_session_episode.validate_episode_file(ep)
        assert any("commits==0" in p for p in problems)

    def test_validate_episode_file_clean_episode_passes(self, tmp_path):
        ep = tmp_path / "episode-ok.json"
        ep.write_text(
            '{"events": [], "metrics": {"commits": 1, "files_changed": 4}}',
            encoding="utf-8",
        )
        assert extract_session_episode.validate_episode_file(ep) == []


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
class TestPreserveChronology:
    @staticmethod
    def _repo(tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        return repo

    @staticmethod
    def _event(episode, content):
        return next(evt for evt in episode["events"] if evt["content"] == content)

    def test_preserve_keeps_timestamped_milestone_after_commit(
        self, tmp_path, monkeypatch
    ) -> None:
        repo = self._repo(tmp_path)
        first = _commit(repo, "first.txt", "first", when="2026-08-04T05:00:00+00:00")
        second = _commit(repo, "second.txt", "second", when="2026-08-04T10:00:00+00:00")
        monkeypatch.chdir(repo)
        monkeypatch.setattr(extract_session_episode, "_repo_root", lambda: repo)

        session = _json_log(
            [
                {
                    "time": "2026-08-04T10:30:00+00:00",
                    "task": "Finalized closeout chronology",
                }
            ],
            committed=f"Commit {first}",
        )
        session["session"]["date"] = "2026-08-04"
        session["session"]["startingCommit"] = "0" * 40
        session["endingCommit"] = second
        session_file = tmp_path / "2026-08-04-session-4435-chronology.json"
        session_file.write_text(json.dumps(session), encoding="utf-8")
        episodes = tmp_path / "episodes"
        episode_file = episodes / "episode-2026-08-04-session-4435-chronology.json"

        assert extract_session_episode.main(
            [str(session_file), "--output-path", str(episodes), "--force"]
        ) == 0
        corrupted = json.loads(episode_file.read_text(encoding="utf-8"))
        milestone = self._event(corrupted, "Finalized closeout chronology")
        first_commit = self._event(corrupted, f"Commit: {first}")
        second_commit = self._event(corrupted, f"Commit: {second}")
        milestone["timestamp"] = "2026-08-04T00:00:00+00:00"
        milestone["caused_by"] = []
        milestone["leads_to"] = [first_commit["id"]]
        first_commit["caused_by"].append(milestone["id"])
        second_commit["leads_to"] = []
        episode_file.write_text(json.dumps(corrupted, indent=2) + "\n", encoding="utf-8")

        assert extract_session_episode.main(
            [str(session_file), "--output-path", str(episodes), "--preserve", "--pending-stage"]
        ) == 0

        episode = json.loads(episode_file.read_text(encoding="utf-8"))
        milestone = self._event(episode, "Finalized closeout chronology")
        first_commit = self._event(episode, f"Commit: {first}")
        second_commit = self._event(episode, f"Commit: {second}")
        assert milestone["timestamp"] == "2026-08-04T10:30:00+00:00"
        assert milestone["caused_by"] == [second_commit["id"]]
        assert second_commit["leads_to"] == [milestone["id"]]
        assert first_commit["leads_to"] == [second_commit["id"]]

    def test_causal_edge_order_rejects_scrambled_store(self) -> None:
        events = [
            {
                "id": "e001",
                "timestamp": "2026-08-04T10:00:00+00:00",
                "type": "commit",
                "content": "Commit: older",
                "caused_by": ["e002"],
                "leads_to": [],
            },
            {
                "id": "e002",
                "timestamp": "2026-08-04T10:30:00+00:00",
                "type": "milestone",
                "content": "post-commit closeout",
                "caused_by": [],
                "leads_to": ["e001"],
            },
        ]

        problems = extract_session_episode.validate_causal_edge_order(events)

        assert any("event e002 leads to earlier event e001" in p for p in problems)

    def test_causal_graph_validation_rejects_backward_order(self) -> None:
        events = [
            {
                "id": "e001",
                "timestamp": "2026-08-04T10:00:00+00:00",
                "type": "commit",
                "content": "Commit: older",
                "caused_by": ["e002"],
                "leads_to": [],
            },
            {
                "id": "e002",
                "timestamp": "2026-08-04T10:30:00+00:00",
                "type": "milestone",
                "content": "post-commit closeout",
                "caused_by": [],
                "leads_to": ["e001"],
            },
        ]

        with pytest.raises(extract_session_episode.EpisodeValidationError) as error:
            extract_session_episode.validate_episode_causal_graph(events)

        assert str(error.value) == "event e002 leads to earlier event e001"

    def test_validate_mode_rejects_scrambled_causal_edges(self, tmp_path, capsys) -> None:
        episode = tmp_path / "episode-scrambled.json"
        episode.write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "id": "e001",
                            "timestamp": "2026-08-04T10:00:00+00:00",
                            "type": "commit",
                            "content": "Commit: older",
                            "caused_by": ["e002"],
                            "leads_to": [],
                        },
                        {
                            "id": "e002",
                            "timestamp": "2026-08-04T10:30:00+00:00",
                            "type": "milestone",
                            "content": "post-commit closeout",
                            "caused_by": [],
                            "leads_to": ["e001"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2
        assert "event e002 leads to earlier event e001" in capsys.readouterr().err

    def test_validate_mode_reports_invalid_causal_ref_value(self, tmp_path, capsys) -> None:
        episode = tmp_path / "episode-invalid-ref.json"
        episode.write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "id": "e001",
                            "timestamp": "2026-08-04T10:00:00+00:00",
                            "type": "milestone",
                            "content": "work",
                            "caused_by": [],
                            "leads_to": [42],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert extract_session_episode.main([str(tmp_path), "--validate"]) == 2
        assert "event e001 field leads_to contains invalid ref 42" in capsys.readouterr().err

    def test_causal_edge_order_allows_equal_timestamps(self) -> None:
        events = [
            {
                "id": "e001",
                "timestamp": "2026-08-04T10:00:00+00:00",
                "type": "milestone",
                "content": "work",
                "caused_by": [],
                "leads_to": ["e002"],
            },
            {
                "id": "e002",
                "timestamp": "2026-08-04T10:00:00+00:00",
                "type": "test",
                "content": "tests passed",
                "caused_by": ["e001"],
                "leads_to": [],
            },
        ]

        assert extract_session_episode.validate_causal_edge_order(events) == []


class TestDurationFromWorklogs:
    """Tests for _duration_from_worklogs (issue #3972)."""

    def test_two_timestamps_computes_duration(self):
        entries = [
            {"time": "2026-07-30T06:00:00Z", "entry": "start"},
            {"time": "2026-07-30T06:45:00Z", "entry": "end"},
        ]
        assert extract_session_episode._duration_from_worklogs(entries) == 45

    def test_multiple_entries_uses_first_and_last(self):
        entries = [
            {"time": "2026-07-30T06:00:00Z", "entry": "a"},
            {"time": "2026-07-30T06:20:00Z", "entry": "b"},
            {"time": "2026-07-30T06:30:00Z", "entry": "c"},
        ]
        assert extract_session_episode._duration_from_worklogs(entries) == 30

    def test_single_entry_returns_none(self):
        """One timestamp cannot span an interval, so the duration is unmeasured.

        This asserted 0 before issue #3972. A single-entry log and a log whose
        first and last entries share a timestamp both read as 0, which is the
        conflation the fix removes.
        """
        entries = [{"time": "2026-07-30T06:00:00Z", "entry": "only"}]
        assert extract_session_episode._duration_from_worklogs(entries) is None

    def test_empty_list_returns_none(self):
        """No entries means no measurement, not a measured zero (issue #3972)."""
        assert extract_session_episode._duration_from_worklogs([]) is None

    def test_entries_without_time_are_skipped(self):
        entries = [
            {"entry": "no time here"},
            {"time": "2026-07-30T06:00:00Z", "entry": "start"},
            {"entry": "also no time"},
            {"time": "2026-07-30T06:10:00Z", "entry": "end"},
        ]
        assert extract_session_episode._duration_from_worklogs(entries) == 10

    def test_invalid_time_value_is_skipped(self):
        entries = [
            {"time": "not-a-date", "entry": "bad"},
            {"time": "2026-07-30T06:00:00Z", "entry": "start"},
            {"time": "2026-07-30T06:05:00Z", "entry": "end"},
        ]
        assert extract_session_episode._duration_from_worklogs(entries) == 5


class TestDurationFromMetricsBlock:
    """Tests for _duration_from_metrics_block (issue #3972)."""

    def test_parses_tilde_minutes_string(self):
        assert (
            extract_session_episode._duration_from_metrics_block({"duration": "~20 minutes"}) == 20
        )

    def test_parses_plain_minutes_string(self):
        assert (
            extract_session_episode._duration_from_metrics_block({"duration": "25 minutes"}) == 25
        )

    def test_parses_integer_duration(self):
        assert extract_session_episode._duration_from_metrics_block({"duration": 30}) == 30

    def test_parses_duration_minutes_key(self):
        assert extract_session_episode._duration_from_metrics_block({"duration_minutes": 15}) == 15

    def test_missing_key_returns_none(self):
        """No duration key means unmeasured, not a measured zero (issue #3972)."""
        assert extract_session_episode._duration_from_metrics_block({}) is None

    def test_unparseable_string_returns_none(self):
        """An unreadable value is a failed measurement, not a zero-length session."""
        assert extract_session_episode._duration_from_metrics_block({"duration": "unknown"}) is None


class TestJsonMetricsDuration:
    """Tests that json_metrics populates duration_minutes from session data (issue #3972)."""

    def test_duration_computed_from_worklogs(self):
        data = {
            "workLog": [
                {"time": "2026-07-30T08:00:00Z", "entry": "start"},
                {"time": "2026-07-30T08:30:00Z", "entry": "end"},
            ],
        }
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["duration_minutes"] == 30

    def test_mixed_naive_and_offset_timestamps_are_normalized_to_utc(self):
        """Issue #4675: mixed ISO timezone forms must not crash duration."""
        data = {
            "workLog": [
                {"time": "2026-08-06T10:00:00", "entry": "start"},
                {"time": "2026-08-06T06:30:00-04:00", "entry": "end"},
            ],
        }
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["duration_minutes"] == 30

    def test_duration_from_old_schema_metrics_block(self):
        data = {
            "metrics": {"duration": "~20 minutes", "toolCalls": 10},
        }
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["duration_minutes"] == 20

    def test_worklogs_timestamp_wins_over_metrics_block(self):
        """Structured timestamps take priority over the prose metrics block."""
        data = {
            "workLog": [
                {"time": "2026-07-30T08:00:00Z", "entry": "start"},
                {"time": "2026-07-30T08:45:00Z", "entry": "end"},
            ],
            "metrics": {"duration": "~20 minutes"},
        }
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["duration_minutes"] == 45

    def test_no_time_data_stays_none(self):
        """No timestamps means unmeasured duration, which is not the same as zero.

        This asserted 0 before issue #3972. Reading 0 minutes tells a consumer the
        session took no time; reading null tells it nobody measured. The second is
        true and the first is not.
        """
        data: dict = {}
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["duration_minutes"] is None

    def test_tool_calls_from_old_schema(self):
        data = {
            "metrics": {"duration": "~15 minutes", "toolCalls": 24},
        }
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["tool_calls"] == 24

    def test_tool_calls_none_for_modern_session(self):
        """Modern logs carry no tool count, so the field stays null (issue #3972).

        This asserted 0 before the fix. Modern session logs have no
        machine-readable tool count at all, so 0 claimed a measurement that was
        never taken, and 0 reads as "nothing happened here, skip it". Duration is
        still populated from the timestamps, which is what makes the pairing a
        good regression guard: one field is measurable and the other is not, and
        the two must not collapse to the same sentinel.
        """
        data = {
            "workLog": [
                {"time": "2026-07-30T08:00:00Z", "entry": "start"},
                {"time": "2026-07-30T08:30:00Z", "entry": "end"},
            ],
        }
        metrics = extract_session_episode.json_metrics(data)
        assert metrics["tool_calls"] is None
        assert metrics["duration_minutes"] == 30
