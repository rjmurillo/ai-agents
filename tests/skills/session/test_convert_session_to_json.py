"""Tests for convert_session_to_json.py markdown migration script."""

import sys
from pathlib import Path

SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "session-migration" / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import convert_session_to_json


class TestFindChecklistItem:
    """Tests for _find_checklist_item function."""

    def test_finds_checked_item(self):
        content = (
            "| Level | Check | Status | Evidence |\n"
            "|-------|-------|--------|----------|\n"
            "| MUST | activate_project | [x] | Tool called |\n"
        )
        result = convert_session_to_json._find_checklist_item(content, "activate_project")
        assert result["Complete"] is True
        assert "Tool called" in result["Evidence"]

    def test_not_found(self):
        content = (
            "| Level | Check | Status | Evidence |\n"
            "|-------|-------|--------|----------|\n"
            "| MUST | something_else | [x] | Done |\n"
        )
        result = convert_session_to_json._find_checklist_item(content, "activate_project")
        assert result["Complete"] is False

    def test_unchecked_item(self):
        content = (
            "| Level | Check | Status | Evidence |\n"
            "|-------|-------|--------|----------|\n"
            "| MUST | activate_project | [ ] |  |\n"
        )
        result = convert_session_to_json._find_checklist_item(content, "activate_project")
        assert result["Complete"] is False


class TestParseWorkLog:
    """Tests for _parse_work_log function."""

    def test_extracts_work_log_entries(self):
        content = (
            "## Work Log\n\n"
            "### Task One\n\n"
            "Did some work on the feature and it went well with good results.\n"
            "Modified `script.ps1` and tested.\n\n"
            "### Task Two\n\n"
            "Fixed a bug in the validation logic that was causing failures.\n\n"
            "## Next Steps\n"
        )
        entries = convert_session_to_json._parse_work_log(content)
        assert len(entries) >= 1

    def test_extracts_files_from_work_log(self):
        content = (
            "## Work Log\n\n"
            "### Updated Scripts\n\n"
            "Modified `test-script.ps1` and `config.json` for the new feature.\n\n"
            "## End\n"
        )
        entries = convert_session_to_json._parse_work_log(content)
        has_files = any("files" in e for e in entries)
        assert has_files

    def test_empty_work_log(self):
        content = "## Work Log\n\n### [Task/Topic]\n\n## End\n"
        entries = convert_session_to_json._parse_work_log(content)
        assert len(entries) == 0

    def test_alternative_headings(self):
        content = (
            "## Changes Made\n\n"
            "### Refactored Module\n\n"
            "Improved the module structure to reduce coupling"
            " and improve testability significantly.\n\n"
            "## End\n"
        )
        entries = convert_session_to_json._parse_work_log(content)
        assert len(entries) >= 1


class TestConvertMarkdownSession:
    """Tests for _convert_markdown_session function."""

    def test_extracts_session_number(self):
        result = convert_session_to_json._convert_markdown_session(
            "# Session 5", "2026-01-01-session-5-test.md"
        )
        assert result["session"]["number"] == 5

    def test_extracts_date(self):
        result = convert_session_to_json._convert_markdown_session(
            "# Test", "2026-03-15-session-1.md"
        )
        assert result["session"]["date"] == "2026-03-15"

    def test_extracts_branch(self):
        content = "**Branch**: `feat/test-feature`"
        result = convert_session_to_json._convert_markdown_session(
            content, "2026-01-01-session-1.md"
        )
        assert result["session"]["branch"] == "feat/test-feature"

    def test_extracts_commit(self):
        content = "**Starting Commit**: `abc1234`"
        result = convert_session_to_json._convert_markdown_session(
            content, "2026-01-01-session-1.md"
        )
        assert result["session"]["startingCommit"] == "abc1234"

    def test_extracts_objective(self):
        content = "## Objective\n\nImplement the new feature"
        result = convert_session_to_json._convert_markdown_session(
            content, "2026-01-01-session-1.md"
        )
        assert result["session"]["objective"] == "Implement the new feature"

    def test_default_objective(self):
        result = convert_session_to_json._convert_markdown_session(
            "# Test", "session-1.md"
        )
        assert "[Migrated from markdown]" in result["session"]["objective"]

    def test_protocol_compliance_structure(self):
        result = convert_session_to_json._convert_markdown_session(
            "# Test", "2026-01-01-session-1.md"
        )
        assert "protocolCompliance" in result
        assert "sessionStart" in result["protocolCompliance"]
        assert "sessionEnd" in result["protocolCompliance"]

    def test_must_levels_assigned(self):
        result = convert_session_to_json._convert_markdown_session(
            "# Test", "2026-01-01-session-1.md"
        )
        start = result["protocolCompliance"]["sessionStart"]
        assert start["serenaActivated"]["level"] == "MUST"
        assert start["gitStatusVerified"]["level"] == "SHOULD"
