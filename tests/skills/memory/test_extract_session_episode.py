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
        # Below git's 7-char minimum abbreviation, do not treat as a match.
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

    def test_event_timestamps_normalized_to_session_midnight(self):
        merged = extract_session_episode.merge_preserving(
            self._stub(), self._rich(), session_id="2026-01-08-session-807"
        )
        assert merged["events"][0]["timestamp"] == "2026-01-08T00:00:00+00:00"

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


class TestPreserveCli:
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
    """Episode events form a lifecycle-ordered causal chain, not a flat graph.

    ADR-038 defines ``caused_by``/``leads_to`` as first-class fields (#3245); the
    extractor links events so reflexion retrieval can walk the graph. The chain
    follows the session lifecycle (a commit is a cause; tests, errors, and review
    milestones are effects), not physical append order, so a commit that
    ``json_events`` appends last is never ``caused_by`` a later milestone (#3260).
    Linking runs on final ids (after ``_dedupe_events`` reassignment) so
    references never dangle. Ordering keys on ``(timestamp, lifecycle rank,
    original position)`` so genuine time order still dominates and rank only
    breaks ties within a shared timestamp.
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

    def test_multi_event_chain(self):
        # Physical order is milestone, test, commit; the causal chain reorders by
        # lifecycle (commit first) without touching the physical list order.
        events = [self._evt("e001"), self._evt("e002", "test"), self._evt("e003", "commit")]
        extract_session_episode._link_sequential_events(events)
        assert [e["id"] for e in events] == ["e001", "e002", "e003"]
        # commit (e003) is the root cause; test (e002) then milestone (e001) follow.
        assert events[2]["caused_by"] == [] and events[2]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e003"] and events[1]["leads_to"] == ["e001"]
        assert events[0]["caused_by"] == ["e002"] and events[0]["leads_to"] == []

    def test_single_event_has_no_links(self):
        events = [self._evt("e001")]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == []
        assert events[0]["leads_to"] == []

    def test_empty_list_does_not_crash(self):
        events: list[dict] = []
        extract_session_episode._link_sequential_events(events)
        assert events == []

    def test_events_without_id_are_skipped(self):
        # Defensive: a malformed entry with no id must not enter the chain or crash.
        malformed = {"type": "milestone", "content": "no id"}
        events = [self._evt("e001"), malformed, self._evt("e002", "commit")]
        extract_session_episode._link_sequential_events(events)
        # commit (e002) is the cause of milestone (e001); malformed is untouched.
        assert events[2]["caused_by"] == [] and events[2]["leads_to"] == ["e001"]
        assert events[0]["caused_by"] == ["e002"] and events[0]["leads_to"] == []
        assert "caused_by" not in malformed

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

    def test_same_rank_events_keep_original_order(self):
        # Same lifecycle rank and timestamp must preserve append order (stable sort).
        events = [self._evt(f"e{n:03d}") for n in range(1, 4)]  # three milestones
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e001"] and events[1]["leads_to"] == ["e003"]
        assert events[2]["caused_by"] == ["e002"] and events[2]["leads_to"] == []

    def test_unknown_type_sorts_at_default_rank(self):
        # An unknown type ranks with tests (default), between commit and error.
        events = [
            self._evt("e001", "error", "boom"),
            self._evt("e002", "mystery", "?"),
            self._evt("e003", "commit", "Commit: abc"),
        ]
        extract_session_episode._link_sequential_events(events)
        by_id = {e["id"]: e for e in events}
        assert by_id["e003"]["caused_by"] == [] and by_id["e003"]["leads_to"] == ["e002"]
        assert by_id["e002"]["caused_by"] == ["e003"] and by_id["e002"]["leads_to"] == ["e001"]
        assert by_id["e001"]["caused_by"] == ["e002"] and by_id["e001"]["leads_to"] == []

    def test_timestamp_dominates_lifecycle_rank(self):
        # A commit with a later timestamp must not be reordered before an earlier
        # milestone; lifecycle rank only breaks ties within one timestamp.
        early = self._evt("e001", "milestone", "early")
        late = self._evt("e002", "commit", "late")
        late["timestamp"] = "2026-07-19T09:00:00+00:00"  # after the milestone
        events = [early, late]
        extract_session_episode._link_sequential_events(events)
        assert events[0]["caused_by"] == [] and events[0]["leads_to"] == ["e002"]
        assert events[1]["caused_by"] == ["e001"] and events[1]["leads_to"] == []

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
        # Acceptance (#3245 + #3260): a generated multi-event episode is a single
        # connected chain whose root cause is the commit, not a milestone.
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

        # Exactly one root (no cause) and one tail (no effect); all links resolve.
        roots = [e for e in events if not e["caused_by"]]
        tails = [e for e in events if not e["leads_to"]]
        assert len(roots) == 1 and len(tails) == 1
        for e in events:
            for ref in e["caused_by"] + e["leads_to"]:
                assert ref in ids, f"dangling reference {ref}"

        # #3260: the root cause is the commit and no commit is caused_by a milestone.
        milestone_ids = {e["id"] for e in events if e["type"] == "milestone"}
        commit_ids = {e["id"] for e in events if e["type"] == "commit"}
        assert commit_ids, "expected at least one commit event"
        assert roots[0]["type"] == "commit"
        for cid in commit_ids:
            assert not (set(by_id[cid]["caused_by"]) & milestone_ids)

        # The chain is a single connected path visiting every event once.
        walked: list[str] = []
        seen: set[str] = set()
        cur = roots[0]
        while cur is not None:
            assert cur["id"] not in seen, "cycle in causal chain"
            seen.add(cur["id"])
            walked.append(cur["id"])
            nxt = cur["leads_to"]
            cur = by_id[nxt[0]] if nxt else None
        assert len(walked) == len(events)

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
        # json_events and json_metrics must agree, or the causal graph carries a
        # commit node the metric does not (issue #3328 provenance consistency).
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
    Counting those inflated metrics.commits and seeded causal-graph commit
    nodes for work the session never did, while the session's own commits,
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
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert set(shas) == {"abc1234def", "fed4321abc"}

    def test_a_sha_only_in_work_log_prose_is_not_a_commit(self):
        """The fix/3342 shape: narrative cites a bot commit the session did not author."""
        log = self._log(
            evidence="One commit: the fix (abc1234def).",
            ending="abc1234def",
            work_log=[{"phase": "Merge", "summary": "Took the bot's commit deadbee1234."}],
        )
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert shas == ["abc1234def"]
        assert "deadbee1234" not in shas

    def test_a_session_commit_named_only_in_evidence_is_not_dropped(self):
        """The other half of #3363: prose-only extraction missed real commits."""
        log = self._log(
            evidence="Three commits: aaa1111bbb, ccc2222ddd, and eee3333fff.",
            ending="eee3333fff",
            work_log=[{"phase": "Implement", "summary": "Did the work."}],
        )
        shas = extract_session_episode._collect_shas(log, include_starting=False)
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
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert shas == ["abc1234def"]

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
        shas = extract_session_episode._collect_shas(log, include_starting=False)
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
        shas = extract_session_episode._collect_shas(log, include_starting=False)
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
        shas = extract_session_episode._collect_shas(log, include_starting=False)
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
        assert extract_session_episode._collect_shas(log, include_starting=False) == ["abc1234def"]

    def test_a_missing_compliance_section_does_not_raise(self):
        log = _json_log([{"phase": "x", "summary": "committed as abc1234def"}])
        log["endingCommit"] = ""
        del log["protocolCompliance"]
        assert extract_session_episode._collect_shas(log, include_starting=False) == ["abc1234def"]

    def test_a_non_dict_compliance_section_does_not_raise(self):
        log = _json_log([])
        log["protocolCompliance"] = "not a dict"
        assert extract_session_episode._collect_shas(log, include_starting=False) == ["bbbbbbb1234"]


class TestOneCommitCountsOnceAcrossAbbreviations:
    """Issue #3363: `_collect_shas` promises distinct commits, so two fields
    that spell one commit at different abbreviation lengths must not both land.
    Exact string membership let a full 40-char `endingCommit` and a 7-char
    abbreviation of it in the evidence through as two entries, double-counting
    `metrics.commits` and emitting two causal-graph nodes for one commit.
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
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert shas == [self._FULL]

    def test_the_first_spelling_seen_is_the_one_kept(self):
        """Ordering has to stay stable: endingCommit is read first, so its
        spelling wins even when the evidence names the longer form.
        """
        log = self._log(evidence=f"Committed as {self._FULL}.", ending=self._SHORT)
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert shas == [self._SHORT]

    def test_two_genuinely_different_commits_both_survive(self):
        """Negative control: the de-duplication must not collapse distinct
        commits that merely share a short prefix below git's 7-char minimum.
        """
        other = "abfeed09876543210fedcba9876543210fedcba9"
        log = self._log(evidence=f"Two commits: {self._FULL} and {other}.", ending="")
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert shas == [self._FULL, other]

    def test_a_prose_fallback_sha_matching_a_structured_one_is_not_added_twice(self):
        log = _json_log(
            [{"phase": "implementation", "summary": f"Committed {self._SHORT}."}]
        )
        log["endingCommit"] = self._FULL
        shas = extract_session_episode._collect_shas(log, include_starting=False)
        assert shas == [self._FULL]

    def test_already_seen_needs_seven_shared_characters(self):
        """`_same_commit` requires git's minimum unambiguous length, so a
        six-character prefix is not treated as the same commit.
        """
        assert not extract_session_episode._already_seen("abc123", [self._FULL])
        assert extract_session_episode._already_seen(self._SHORT, [self._FULL])

    def test_an_empty_seen_list_matches_nothing(self):
        assert not extract_session_episode._already_seen(self._FULL, [])
