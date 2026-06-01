"""Tests for extract_session_episode.py."""

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import extract_session_episode


class TestGetSessionIdFromPath:
    """Tests for get_session_id_from_path function."""

    def test_full_date_pattern(self):
        result = extract_session_episode.get_session_id_from_path(
            Path("/path/to/2026-01-15-session-42-desc.md")
        )
        assert result == "2026-01-15-session-42"

    def test_session_only_pattern(self):
        result = extract_session_episode.get_session_id_from_path(
            Path("/path/to/session-7.md")
        )
        assert result == "session-7"

    def test_fallback_to_filename(self):
        result = extract_session_episode.get_session_id_from_path(
            Path("/path/to/custom-name.md")
        )
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
        lines = ["Important lesson: always check return codes"]
        result = extract_session_episode.parse_lessons(lines)
        assert len(result) >= 1

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


def _json_log(work_log, end_complete=True):
    gate = _gate(end_complete)
    return {
        "session": {
            "number": 1, "date": "2026-05-31", "branch": "feat/x",
            "startingCommit": "aaaaaaa", "objective": "Do the thing",
        },
        "protocolCompliance": {
            "sessionStart": {},
            "sessionEnd": {
                "checklistComplete": gate, "changesCommitted": gate,
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
        assert extract_session_episode.json_outcome(_json_log([{"task": "t", "outcome": "20 passed"}])) == "success"

    def test_incomplete_gates_is_partial(self):
        assert extract_session_episode.json_outcome(_json_log([{"task": "t", "outcome": "wip"}], end_complete=False)) == "partial"

    def test_counted_failure_incomplete_is_failure(self):
        assert extract_session_episode.json_outcome(_json_log([{"task": "t", "outcome": "3 failed"}], end_complete=False)) == "failure"

    def test_regression_2036_prose_fail_not_failure(self):
        data = _json_log([
            {"action": "compress", "outcome": "compression insufficient; test still fails"},
            {"action": "verify", "outcome": "AGENTS.md 2791 B; markdownlint 0 errors"},
        ])
        assert extract_session_episode.json_outcome(data) == "success"

    def test_milestone_from_task_and_action_and_string(self):
        ev_task = extract_session_episode.json_events(_json_log([{"task": "Build X", "outcome": "done"}]), "2026-05-31T00:00:00+00:00")
        ev_action = extract_session_episode.json_events(_json_log([{"action": "Refactor Y", "outcome": "done"}]), "2026-05-31T00:00:00+00:00")
        ev_string = extract_session_episode.json_events(_json_log(["Reviewed PR 1766"]), "2026-05-31T00:00:00+00:00")
        assert any(e["type"] == "milestone" and e["content"] == "Build X" for e in ev_task)
        assert any(e["type"] == "milestone" and e["content"] == "Refactor Y" for e in ev_action)
        assert any(e["type"] == "milestone" and "Reviewed PR 1766" in e["content"] for e in ev_string)

    def test_no_error_event_from_prose_fail(self):
        events = extract_session_episode.json_events(_json_log([{"action": "x", "outcome": "test still fails; 0 errors"}]), "2026-05-31T00:00:00+00:00")
        assert not any(e["type"] == "error" for e in events)

    def test_error_event_from_counted_failure(self):
        events = extract_session_episode.json_events(_json_log([{"task": "t", "outcome": "2 failed"}]), "2026-05-31T00:00:00+00:00")
        assert any(e["type"] == "error" for e in events)

    def test_string_worklog_does_not_crash(self):
        m = extract_session_episode.json_metrics(_json_log(["touched 3 files", "ran tests"]))
        assert m["files_changed"] == 3

    def test_main_on_json_log_with_prose_fail(self, tmp_path, capsys):
        log = tmp_path / "2026-05-31-session-9001.json"
        log.write_text(json.dumps(_json_log([{"action": "x", "outcome": "test still fails; 0 errors"}])), encoding="utf-8")
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
        assert extract_session_episode._gate_complete(data, "sessionEnd", "checklistComplete") is False

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
        archive.write_text(json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8")

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        data = {"session": {"number": 2, "date": "2026-05-31"}, "workLog": [], "endingCommit": ""}
        bundle = extract_session_episode.extract_from_json(data)
        assert any(e.get("type") == "milestone" for e in bundle["events"])

    def test_metrics_sourced_from_archive(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(json.dumps(_json_log([{"task": "t", "outcome": "3 failed"}])), encoding="utf-8")

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        data = {"session": {"number": 2, "date": "2026-05-31"}, "workLog": [], "endingCommit": ""}
        bundle = extract_session_episode.extract_from_json(data)
        assert bundle["metrics"]["errors"] >= 1

    def test_truthy_empty_worklog_still_uses_archive(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8")

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


class TestArchiveGateAndRoot:
    """Decisions must not block event recovery; repo root resolves via marker (#2036)."""

    def test_decisions_do_not_block_archive_events(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8")

        def fake_find(session_id):
            p = tmp_path / f"{session_id}.json"
            return p if p.is_file() else None

        monkeypatch.setattr(extract_session_episode, "_find_archive_json", fake_find)
        # Primary log: a decision (via evidence prose) but no milestone events.
        data = {
            "session": {"number": 2, "date": "2026-05-31"},
            "workLog": [{"evidence": "chose approach A because it is simpler"}],
            "endingCommit": "",
        }
        bundle = extract_session_episode.extract_from_json(data)
        assert bundle["decisions"], "primary decision should be preserved"
        assert any(e.get("type") == "milestone" for e in bundle["events"]), "archive events should still be recovered"

    def test_repo_root_finds_agents_marker(self):
        root = extract_session_episode._repo_root()
        assert (root / ".agents").is_dir()


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
    """Decision detection covers adopt/prioritize wording (#2036)."""

    def test_adopt_is_a_decision(self):
        data = _json_log([{"evidence": "adopt the streaming parser for large logs"}])
        assert extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00")

    def test_prioritize_is_a_decision(self):
        data = _json_log([{"evidence": "prioritized correctness over throughput"}])
        assert extract_session_episode.json_decisions(data, "2026-05-31T00:00:00+00:00")
