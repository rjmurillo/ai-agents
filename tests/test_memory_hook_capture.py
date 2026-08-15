"""Tests for the post_tool_call_memory hook (fact capture)."""

from __future__ import annotations

import io
import json

import pytest

from memory_enhancement.extraction import (
    extract_error_pattern,
    format_suggestion,
    has_error_indicators,
)
from memory_enhancement.hooks.post_tool_call_memory import (
    _analyze_tool_result,
    _read_tool_result,
    main,
)


class TestReadToolResult:
    """Tests for stdin JSON parsing."""

    @pytest.mark.unit
    def test_valid_json(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": "Exit code 1\noutput text",
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        name, result = _read_tool_result()
        assert name == "Bash"
        assert result == "Exit code 1\noutput text"

    @pytest.mark.unit
    def test_success_event_is_ignored(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "error": "Error handling examples",
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))

        name, result = _read_tool_result()

        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_interrupted_failure_is_ignored(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": "Command was interrupted",
                "is_interrupt": True,
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))

        name, result = _read_tool_result()

        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_non_string_error_is_ignored(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": {"message": "bad payload"},
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))

        name, result = _read_tool_result()

        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_missing_fields(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_invalid_json(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_empty_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_non_bool_is_interrupt_is_rejected(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": "real error",
                "is_interrupt": "yes",
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_numeric_tool_name_is_rejected(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": 42,
                "error": "real error",
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_whitespace_only_error_is_rejected(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "Bash",
                "error": "   ",
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""

    @pytest.mark.unit
    def test_whitespace_only_tool_name_is_rejected(self, monkeypatch):
        payload = json.dumps(
            {
                "hook_event_name": "PostToolUseFailure",
                "tool_name": "  ",
                "error": "real error",
            }
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        name, result = _read_tool_result()
        assert name == ""
        assert result == ""


class TestIsErrorResult:
    """Tests for error detection in tool output."""

    @pytest.mark.unit
    def test_detects_error(self):
        assert has_error_indicators("Error: file not found") is True

    @pytest.mark.unit
    def test_detects_traceback(self):
        assert has_error_indicators("Traceback (most recent call last):") is True

    @pytest.mark.unit
    def test_detects_failure(self):
        assert has_error_indicators("Build failed with 3 errors") is True

    @pytest.mark.unit
    def test_clean_output(self):
        assert has_error_indicators("Build succeeded. 0 warnings.") is False

    @pytest.mark.unit
    def test_empty_string(self):
        assert has_error_indicators("") is False


class TestExtractErrorPattern:
    """Tests for error line extraction."""

    @pytest.mark.unit
    def test_extracts_first_error_line(self):
        text = "line 1\nError: something broke\nline 3"
        result = extract_error_pattern("Bash", text)
        assert "Error: something broke" in result["pattern"]

    @pytest.mark.unit
    def test_truncates_long_patterns(self):
        text = "Error: " + "x" * 300
        result = extract_error_pattern("Bash", text)
        assert len(result["suggested_memory"]) <= 300

    @pytest.mark.unit
    def test_returns_dict_with_tool_name(self):
        text = "some output"
        result = extract_error_pattern("Read", text)
        assert result["tool_name"] == "Read"
        assert "pattern" in result


class TestAnalyzeToolResult:
    """Tests for the analysis dispatch logic."""

    @pytest.mark.unit
    def test_error_generates_learning_suggestion(self):
        result = _analyze_tool_result("Bash", "Error: permission denied")
        assert "<memory-suggestion>" in result
        assert "type: learning" in result
        assert "Bash" in result

    @pytest.mark.unit
    def test_failure_without_error_keyword_generates_suggestion(self):
        result = _analyze_tool_result("Bash", "Exit code 1\ncommand output")
        assert "<memory-suggestion>" in result
        assert "Exit code 1" in result

    @pytest.mark.unit
    def test_empty_failure_generates_nothing(self):
        result = _analyze_tool_result("Bash", "")
        assert result == ""


class TestFormatSuggestion:
    """Tests for suggestion formatting via extraction module."""

    @pytest.mark.unit
    def test_error_suggestion_contains_required_fields(self):
        pattern = extract_error_pattern("Bash", "Error: timeout")
        result = format_suggestion(pattern)
        assert "<memory-suggestion>" in result
        assert "</memory-suggestion>" in result
        assert "type: learning" in result
        assert "trigger: Bash failure" in result
        assert "citation: tool_result:Bash" in result

    @pytest.mark.unit
    def test_content_suggestion_contains_required_fields(self):
        pattern = {
            "tool_name": "Read",
            "content": "Found def my_func():",
            "type": "observation",
        }
        result = format_suggestion(pattern)
        assert "<memory-suggestion>" in result
        assert "</memory-suggestion>" in result
        assert "type: observation" in result
        assert "citation: tool_result:Read" in result


class TestPostToolUseFailurePayload:
    """Claude Code sends failures in the top-level error field."""

    @staticmethod
    def _stdin(monkeypatch, payload):
        payload = {"hook_event_name": "PostToolUseFailure", **payload}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    @pytest.mark.unit
    def test_error_field_yields_error_text(self, monkeypatch):
        self._stdin(
            monkeypatch,
            {
                "tool_name": "Bash",
                "error": "Exit code 1\nModuleNotFoundError: No module named foo",
            },
        )

        name, result = _read_tool_result()

        assert name == "Bash"
        assert "ModuleNotFoundError" in result

    @pytest.mark.unit
    def test_real_payload_adds_context_and_returns_zero(self, monkeypatch, capsys):
        self._stdin(
            monkeypatch,
            {
                "tool_name": "Bash",
                "error": "Exit code 1\nModuleNotFoundError: No module named foo",
            },
        )

        assert main() == 0
        output = json.loads(capsys.readouterr().out)
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "<memory-suggestion>" in context

    @pytest.mark.unit
    def test_failure_without_indicator_adds_context(self, monkeypatch, capsys):
        self._stdin(
            monkeypatch,
            {
                "tool_name": "Bash",
                "error": "Exit code 1\ncommand output",
            },
        )

        assert main() == 0
        output = json.loads(capsys.readouterr().out)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "Exit code 1 command output" in context
        assert "\ncommand output" not in context

    @pytest.mark.unit
    def test_missing_error_returns_zero(self, monkeypatch, capsys):
        self._stdin(
            monkeypatch,
            {
                "tool_name": "Bash",
            },
        )

        assert main() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    @pytest.mark.unit
    def test_successful_result_with_failure_text_returns_zero(
        self, monkeypatch, capsys
    ):
        self._stdin(
            monkeypatch,
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "error": '{"Success":true,"Data":{"note":"failure examples documented"}}',
            },
        )

        assert main() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    @pytest.mark.unit
    def test_interrupted_failure_returns_zero_without_output(
        self, monkeypatch, capsys
    ):
        self._stdin(
            monkeypatch,
            {
                "tool_name": "Bash",
                "error": "Command was interrupted",
                "is_interrupt": True,
            },
        )

        assert main() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    @pytest.mark.unit
    def test_missing_event_name_returns_zero(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps(
                    {
                        "tool_name": "Bash",
                        "error": "Error: quoted documentation",
                    }
                )
            ),
        )

        assert main() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
