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
        payload = '{"tool_name": "Bash", "result": "output text"}'
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        name, result = _read_tool_result()
        assert name == "Bash"
        assert result == "output text"

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
    def test_plain_output_generates_nothing(self):
        result = _analyze_tool_result("Bash", "12345")
        assert result == ""

    @pytest.mark.unit
    def test_successful_listing_generates_nothing(self):
        """A directory listing is not a memory. Issue #4011: this fired on
        roughly 40% of ordinary tool calls and injected empty suggestions."""
        listing = "README.md\nsearch.py\nanalyze_pr_failure.py\ntest_error_handling.py"

        result = _analyze_tool_result("Bash", listing)

        assert result == ""

    @pytest.mark.unit
    def test_code_definition_output_generates_nothing(self):
        result = _analyze_tool_result("Read", "def calculate_score():\nclass SearchEngine:")

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


class TestToolResponsePayload:
    """Claude Code sends tool_response, not result (issue #4011)."""

    @staticmethod
    def _stdin(monkeypatch, payload):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    @pytest.mark.unit
    def test_dict_tool_response_yields_error_text(self, monkeypatch):
        self._stdin(monkeypatch, {
            "tool_name": "Bash",
            "tool_response": {
                "stdout": "ERROR: ModuleNotFoundError: No module named foo",
                "stderr": "Traceback (most recent call last):",
            },
        })

        name, result = _read_tool_result()

        assert name == "Bash"
        assert "ModuleNotFoundError" in result
        assert "Traceback" in result

    @pytest.mark.unit
    def test_real_payload_reaches_exit_code_two(self, monkeypatch):
        self._stdin(monkeypatch, {
            "tool_name": "Bash",
            "tool_response": {"stdout": "ERROR: ModuleNotFoundError: No module named foo"},
        })

        assert main() == 2

    @pytest.mark.unit
    def test_result_key_still_wins_for_back_compat(self, monkeypatch):
        self._stdin(monkeypatch, {
            "tool_name": "Bash",
            "result": "legacy text",
            "tool_response": {"stdout": "ignored"},
        })

        _name, result = _read_tool_result()

        assert result == "legacy text"

    @pytest.mark.unit
    def test_empty_tool_response_dict_yields_empty_text(self, monkeypatch):
        self._stdin(monkeypatch, {"tool_name": "Bash", "tool_response": {}})

        _name, result = _read_tool_result()

        assert result == ""

    @pytest.mark.unit
    def test_bare_string_tool_response(self, monkeypatch):
        self._stdin(monkeypatch, {"tool_name": "Read", "tool_response": "plain text"})

        _name, result = _read_tool_result()

        assert result == "plain text"

    @pytest.mark.unit
    def test_list_tool_response_is_joined(self, monkeypatch):
        self._stdin(monkeypatch, {
            "tool_name": "Read",
            "tool_response": [{"content": "first"}, {"content": "second"}],
        })

        _name, result = _read_tool_result()

        assert result == "first\nsecond"

    @pytest.mark.unit
    def test_null_tool_response_yields_empty_text(self, monkeypatch):
        self._stdin(monkeypatch, {"tool_name": "Bash", "tool_response": None})

        _name, result = _read_tool_result()

        assert result == ""

    @pytest.mark.unit
    def test_benign_output_returns_zero(self, monkeypatch):
        self._stdin(monkeypatch, {
            "tool_name": "Bash",
            "tool_response": {"stdout": "ok"},
        })

        assert main() == 0
