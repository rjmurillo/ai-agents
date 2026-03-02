#!/usr/bin/env python3
"""Tests for the QA agent validator hook.

Covers: non-QA agent skip, missing transcript, valid transcript with
all sections, missing sections, file errors, invalid JSON.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = str(
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SubagentStop"
)
sys.path.insert(0, HOOK_DIR)

import qa_agent_validator  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for is_qa_agent
# ---------------------------------------------------------------------------


class TestIsQAAgent:
    """Tests for is_qa_agent function."""

    def test_returns_true_for_qa(self):
        assert qa_agent_validator.is_qa_agent({"subagent_type": "qa"})

    def test_returns_false_for_other(self):
        assert not qa_agent_validator.is_qa_agent(
            {"subagent_type": "implementer"}
        )

    def test_returns_false_when_missing(self):
        assert not qa_agent_validator.is_qa_agent({})


# ---------------------------------------------------------------------------
# Unit tests for get_transcript_path
# ---------------------------------------------------------------------------


class TestGetTranscriptPath:
    """Tests for get_transcript_path function."""

    def test_returns_path_when_file_exists(self, tmp_path):
        transcript = tmp_path / "transcript.md"
        transcript.write_text("content")
        result = qa_agent_validator.get_transcript_path(
            {"transcript_path": str(transcript)}
        )
        assert result == str(transcript)

    def test_returns_none_when_file_missing(self):
        result = qa_agent_validator.get_transcript_path(
            {"transcript_path": "/nonexistent/file.md"}
        )
        assert result is None

    def test_returns_none_when_key_missing(self):
        result = qa_agent_validator.get_transcript_path({})
        assert result is None

    def test_returns_none_when_empty_string(self):
        result = qa_agent_validator.get_transcript_path(
            {"transcript_path": ""}
        )
        assert result is None

    def test_returns_none_when_whitespace(self):
        result = qa_agent_validator.get_transcript_path(
            {"transcript_path": "   "}
        )
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for get_missing_qa_sections
# ---------------------------------------------------------------------------


class TestGetMissingQASections:
    """Tests for get_missing_qa_sections function."""

    def test_all_sections_present(self):
        transcript = (
            "# Test Strategy\n\nContent\n\n"
            "## Test Results\n\nContent\n\n"
            "### Coverage\n\nContent\n"
        )
        assert qa_agent_validator.get_missing_qa_sections(transcript) == []

    def test_alternative_names_accepted(self):
        transcript = (
            "# Testing Approach\n\nContent\n\n"
            "## Validation Results\n\nContent\n\n"
            "### Acceptance Criteria\n\nContent\n"
        )
        assert qa_agent_validator.get_missing_qa_sections(transcript) == []

    def test_all_sections_missing(self):
        transcript = "# Introduction\n\nSome content\n"
        missing = qa_agent_validator.get_missing_qa_sections(transcript)
        assert len(missing) == 3

    def test_partial_sections_missing(self):
        transcript = (
            "# Test Strategy\n\nContent\n\n"
            "## Other Section\n\nContent\n"
        )
        missing = qa_agent_validator.get_missing_qa_sections(transcript)
        assert len(missing) == 2

    def test_keyword_in_body_not_matched(self):
        """Keywords in paragraph text do not match (must be section headers)."""
        transcript = (
            "This discusses test strategy.\n"
            "Here are test results.\n"
            "Coverage is 80%.\n"
        )
        missing = qa_agent_validator.get_missing_qa_sections(transcript)
        assert len(missing) == 3

    def test_h3_headers_accepted(self):
        transcript = (
            "### Test Plan\n\nContent\n\n"
            "### Test Execution\n\nContent\n\n"
            "### Test Coverage\n\nContent\n"
        )
        assert qa_agent_validator.get_missing_qa_sections(transcript) == []

    def test_empty_transcript(self):
        missing = qa_agent_validator.get_missing_qa_sections("")
        assert len(missing) == 3


# ---------------------------------------------------------------------------
# Unit tests for log_transcript_issue
# ---------------------------------------------------------------------------


class TestLogTranscriptIssue:
    """Tests for log_transcript_issue function."""

    def test_logs_missing_key(self, capsys):
        qa_agent_validator.log_transcript_issue({})
        captured = capsys.readouterr()
        assert "No transcript_path property" in captured.err

    def test_logs_empty_value(self, capsys):
        qa_agent_validator.log_transcript_issue({"transcript_path": ""})
        captured = capsys.readouterr()
        assert "empty/whitespace" in captured.err

    def test_logs_nonexistent_file(self, capsys):
        qa_agent_validator.log_transcript_issue(
            {"transcript_path": "/nonexistent.md"}
        )
        captured = capsys.readouterr()
        assert "does not exist" in captured.err


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0

    def test_exits_0_on_empty_input(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: ""),
        )
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0

    def test_exits_0_for_non_qa_agent(self, monkeypatch):
        hook_input = json.dumps({"subagent_type": "implementer"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0

    def test_exits_0_for_missing_transcript(self, monkeypatch):
        hook_input = json.dumps({"subagent_type": "qa"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0

    def test_reports_passed_when_complete(self, monkeypatch, tmp_path, capsys):
        transcript = tmp_path / "transcript.md"
        transcript.write_text(
            "# Test Strategy\n\n## Test Results\n\n### Coverage\n"
        )
        hook_input = json.dumps({
            "subagent_type": "qa",
            "transcript_path": str(transcript),
        })
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "PASSED" in captured.out

        # Also check machine-readable JSON output
        lines = captured.out.strip().split("\n")
        json_line = lines[-1]
        data = json.loads(json_line)
        assert data["validation_passed"] is True
        assert data["missing_sections"] == []

    def test_reports_failure_when_incomplete(
        self, monkeypatch, tmp_path, capsys
    ):
        transcript = tmp_path / "transcript.md"
        transcript.write_text("# Some Other Section\n\nContent\n")
        hook_input = json.dumps({
            "subagent_type": "qa",
            "transcript_path": str(transcript),
        })
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "FAILURE" in captured.out

        # Check machine-readable JSON
        lines = captured.out.strip().split("\n")
        json_line = lines[-1]
        data = json.loads(json_line)
        assert data["validation_passed"] is False
        assert len(data["missing_sections"]) == 3

    def test_handles_file_read_error(self, monkeypatch, tmp_path, capsys):
        """Handles OSError when reading transcript."""
        transcript_path = str(tmp_path / "unreadable.md")
        hook_input = json.dumps({
            "subagent_type": "qa",
            "transcript_path": transcript_path,
        })
        # File does not exist, so get_transcript_path returns None
        # We need to simulate a file that exists but is unreadable
        # Use mock to bypass get_transcript_path
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with patch(
            "qa_agent_validator.get_transcript_path",
            return_value=transcript_path,
        ):
            with patch(
                "builtins.open",
                side_effect=PermissionError("Permission denied"),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    qa_agent_validator.main()
                assert exc_info.value.code == 0
                captured = capsys.readouterr()
                assert "ERROR" in captured.out

    def test_handles_unexpected_error(self, monkeypatch, capsys):
        """Handles unexpected exceptions gracefully."""
        def raise_error():
            raise RuntimeError("unexpected")

        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=raise_error),
        )
        with pytest.raises(SystemExit) as exc_info:
            qa_agent_validator.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
