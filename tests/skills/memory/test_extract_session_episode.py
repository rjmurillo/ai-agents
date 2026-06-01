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

    def test_numeric_step_prefers_summary_for_title(self):
        title = extract_session_episode._entry_title({"step": 1, "summary": "Authored REQ-005"})
        assert title == "Authored REQ-005"

    def test_numeric_step_summary_becomes_milestone(self):
        data = _json_log([{"step": 1, "summary": "Authored REQ-005"}])
        events = extract_session_episode.json_events(data, "2026-05-31T00:00:00+00:00")
        assert any(
            e["type"] == "milestone" and e["content"] == "Authored REQ-005" for e in events
        )
        assert not any(e["type"] == "milestone" and e["content"] == "1" for e in events)

    def test_summary_included_in_entry_text(self):
        text = extract_session_episode._entry_text({"step": 2, "summary": "Ran 3 failed checks"})
        assert "Ran 3 failed checks" in text


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
            "metrics": {"duration_minutes": 0, "tool_calls": 0, "errors": 0,
                        "recoveries": 0, "commits": 0, "files_changed": 0},
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
            "decisions": [{"id": "d001", "type": "tradeoff", "context": "parser",
                           "chosen": "streaming", "rationale": "memory", "outcome": "success", "effects": []}],
            "events": [{"id": "e001", "timestamp": "2026-01-08T12:20:10.93-06:00",
                        "type": "milestone", "content": "did the thing", "caused_by": [], "leads_to": []}],
            "metrics": {"duration_minutes": 0, "tool_calls": 0, "errors": 3,
                        "recoveries": 0, "commits": 0, "files_changed": 7},
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

    def test_idempotent_second_merge_is_noop(self):
        sid = "2026-01-08-session-807"
        once = extract_session_episode.merge_preserving(self._stub(), self._rich(), session_id=sid)
        twice = extract_session_episode.merge_preserving(self._stub(), once, session_id=sid)
        assert twice == once
        assert json.dumps(twice) == json.dumps(once)

    def test_no_wallclock_when_no_deterministic_date(self):
        new = {"timestamp": "", "events": [], "decisions": [], "lessons": [], "metrics": {}}
        existing = {"timestamp": "", "events": [
            {"id": "e001", "timestamp": "garbage", "type": "milestone", "content": "x",
             "caused_by": [], "leads_to": []}], "decisions": [], "lessons": [], "metrics": {}}
        merged = extract_session_episode.merge_preserving(new, existing, session_id="")
        assert merged["events"][0]["timestamp"] == "garbage"


class TestPreserveCli:
    """--preserve end-to-end and flag exclusivity (#2170)."""

    def _write_log(self, tmp_path, sha="bbbbbbb1234"):
        log = tmp_path / "2026-01-08-session-807.json"
        log.write_text(json.dumps({
            "session": {"date": "2026-01-08"},
            "workLog": [{"task": "fresh extraction milestone"}],
            "endingCommit": sha,
        }), encoding="utf-8")
        return log

    def test_preserve_merges_existing_file(self, tmp_path):
        out = tmp_path / "episodes"
        out.mkdir()
        ep = out / "episode-2026-01-08-session-807.json"
        ep.write_text(json.dumps({
            "id": "episode-2026-01-08-session-807",
            "session": "2026-01-08-session-807",
            "timestamp": "2026-01-08T00:00:00+00:00",
            "outcome": "success", "task": "old curated task",
            "decisions": [], "events": [], "lessons": ["keep me"],
            "metrics": {"errors": 5},
        }), encoding="utf-8")
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
        data = _json_log([
            {"action": "ci", "outcome": "3 failed"},
            {"action": "http", "outcome": "saw 404 errors from upstream"},
            {"action": "ref", "outcome": "closed #760 failures backlog"},
        ])
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
