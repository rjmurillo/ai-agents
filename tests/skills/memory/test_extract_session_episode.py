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


class TestJsonLessonsObjectShape:
    """`_json_lessons` flattens the schema object shape (#2170 thread GAzih)."""

    def test_object_patterns_and_avoidances(self):
        data = {"learnings": {
            "patterns": [
                {"pattern": "Save pending state before reset",
                 "context": "lost data at boundaries",
                 "application": "Always checkpoint first"},
            ],
            "avoidances": [
                {"antipattern": "Resetting mid-loop",
                 "consequence": "dropped items",
                 "correction": "Defer the reset"},
            ],
        }}
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
    """`json_metrics["commits"]` counts every distinct documented commit (#2170)."""

    def test_counts_ending_and_worklog_shas(self):
        data = _json_log([
            {"task": "Commit A", "outcome": "1234abc. Added parser"},
            {"task": "Commit B", "outcome": "5678def0. Fixed lint"},
        ])
        # endingCommit bbbbbbb1234 + two work-log SHAs = 3 distinct.
        assert extract_session_episode.json_metrics(data)["commits"] == 3

    def test_dedupes_repeated_sha(self):
        data = _json_log([
            {"task": "Commit A", "outcome": "1234abc. Added parser"},
            {"task": "Re-reference", "evidence": "see 1234abc for details"},
        ])
        # endingCommit + one distinct work-log SHA (1234abc counted once) = 2.
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


class TestArchiveGateAndRoot:
    """Decisions must not block event recovery; repo root resolves via marker (#2036)."""

    def test_decisions_do_not_block_archive_events(self, tmp_path, monkeypatch):
        archive = tmp_path / "2026-05-31-session-2.json"
        archive.write_text(json.dumps(_json_log([{"task": "archived", "outcome": "5 passed"}])), encoding="utf-8")

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
        assert any(e.get("type") == "milestone" for e in bundle["events"]), "archive events should still be recovered"

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
        assert not any(
            e.get("type") == "milestone" for e in bundle["events"]
        ), "archive events must not replace the session's own commit event"
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

    def test_defect_inventory_not_counted(self):
        """"N errors" describing a pre-existing/baseline backlog is defect
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
        data = _json_log([
            {"action": "lint", "outcome": "23 errors in pre-existing files"},
            {"action": "ci", "outcome": "3 failed"},
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
