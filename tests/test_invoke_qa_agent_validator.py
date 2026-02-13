#!/usr/bin/env python3
"""Tests for SubagentStop/invoke_qa_agent_validator.py."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "SubagentStop"),
)

import invoke_qa_agent_validator as hook


class TestIsQAAgent:
    """Tests for is_qa_agent()."""

    def test_qa_agent_returns_true(self) -> None:
        assert hook.is_qa_agent({"subagent_type": "qa"}) is True

    def test_other_agent_returns_false(self) -> None:
        assert hook.is_qa_agent({"subagent_type": "implementer"}) is False

    def test_missing_key_returns_false(self) -> None:
        assert hook.is_qa_agent({}) is False


class TestGetTranscriptPath:
    """Tests for get_transcript_path()."""

    def test_returns_valid_path(self, tmp_path: Path) -> None:
        transcript = tmp_path / "transcript.md"
        transcript.write_text("content", encoding="utf-8")
        result = hook.get_transcript_path({"transcript_path": str(transcript)})
        assert result == str(transcript)

    def test_returns_none_for_missing_file(self) -> None:
        result = hook.get_transcript_path({"transcript_path": "/nonexistent/path.md"})
        assert result is None

    def test_returns_none_for_empty_string(self) -> None:
        result = hook.get_transcript_path({"transcript_path": ""})
        assert result is None

    def test_returns_none_for_missing_key(self) -> None:
        result = hook.get_transcript_path({})
        assert result is None


class TestGetMissingQASections:
    """Tests for get_missing_qa_sections()."""

    def test_all_sections_present(self) -> None:
        transcript = (
            "# Test Strategy\nStrategy here\n"
            "# Test Results\nResults here\n"
            "# Coverage\nCoverage here\n"
        )
        assert hook.get_missing_qa_sections(transcript) == []

    def test_alternative_headers_accepted(self) -> None:
        transcript = (
            "## Testing Approach\nApproach\n"
            "## Validation Results\nResults\n"
            "## Acceptance Criteria\nCriteria\n"
        )
        assert hook.get_missing_qa_sections(transcript) == []

    def test_h3_headers_accepted(self) -> None:
        transcript = (
            "### Test Plan\nPlan\n### Test Execution\nExecution\n### Test Coverage\nCoverage\n"
        )
        assert hook.get_missing_qa_sections(transcript) == []

    def test_detects_missing_strategy(self) -> None:
        transcript = "## Test Results\nResults\n## Coverage\nCoverage\n"
        missing = hook.get_missing_qa_sections(transcript)
        assert len(missing) == 1
        assert "Test Strategy" in missing[0]

    def test_detects_all_missing(self) -> None:
        transcript = "Just some random text without any section headers."
        missing = hook.get_missing_qa_sections(transcript)
        assert len(missing) == 3

    def test_no_false_positive_from_body_text(self) -> None:
        """Section keywords in body text should not count as headers."""
        transcript = (
            "This paragraph discusses Test Strategy approaches.\n"
            "It also talks about Test Results and Coverage.\n"
        )
        missing = hook.get_missing_qa_sections(transcript)
        assert len(missing) == 3  # None are actual headers


class TestMain:
    """Tests for main() entry point."""

    def test_exits_zero_on_tty(self) -> None:
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            assert hook.main() == 0

    def test_exits_zero_on_empty_input(self) -> None:
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            assert hook.main() == 0

    def test_exits_zero_for_non_qa_agent(self) -> None:
        input_data = json.dumps({"subagent_type": "implementer"})
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            assert hook.main() == 0

    def test_exits_zero_with_no_transcript(self, capsys: pytest.CaptureFixture[str]) -> None:
        input_data = json.dumps({"subagent_type": "qa"})
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "No transcript_path" in captured.err

    def test_reports_missing_sections(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        transcript = tmp_path / "transcript.md"
        transcript.write_text("# Some Content\nNo QA sections here.", encoding="utf-8")

        input_data = json.dumps(
            {
                "subagent_type": "qa",
                "transcript_path": str(transcript),
            }
        )
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "QA VALIDATION FAILURE" in captured.out
        assert "Missing required sections" in captured.out

        # Also verify JSON output
        lines = captured.out.strip().split("\n")
        json_line = lines[-1]
        validation = json.loads(json_line)
        assert validation["validation_passed"] is False
        assert len(validation["missing_sections"]) == 3

    def test_reports_pass_when_complete(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        transcript = tmp_path / "transcript.md"
        transcript.write_text(
            "# Test Strategy\nStrategy\n# Test Results\nResults\n# Coverage\nCoverage\n",
            encoding="utf-8",
        )

        input_data = json.dumps(
            {
                "subagent_type": "qa",
                "transcript_path": str(transcript),
            }
        )
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "QA Validation PASSED" in captured.out

        # Verify JSON output
        lines = captured.out.strip().split("\n")
        json_line = lines[-1]
        validation = json.loads(json_line)
        assert validation["validation_passed"] is True

    def test_handles_file_error_gracefully(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        transcript = tmp_path / "transcript.md"
        transcript.write_text("content", encoding="utf-8")

        input_data = json.dumps(
            {
                "subagent_type": "qa",
                "transcript_path": str(transcript),
            }
        )
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]

        with (
            patch("sys.stdin", mock_stdin),
            patch("invoke_qa_agent_validator.Path.read_text", side_effect=OSError("locked")),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "QA Validation ERROR" in captured.out
