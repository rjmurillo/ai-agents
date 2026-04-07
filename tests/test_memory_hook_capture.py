"""Tests for the post_tool_call_memory hook (fact capture)."""

from __future__ import annotations

import io

import pytest

from memory_enhancement.hooks.post_tool_call_memory import (
    _analyze_tool_result,
    _extract_error_pattern,
    _format_content_suggestion,
    _format_error_suggestion,
    _has_notable_content,
    _is_error_result,
    _read_tool_result,
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
        assert _is_error_result("Error: file not found") is True

    @pytest.mark.unit
    def test_detects_traceback(self):
        assert _is_error_result("Traceback (most recent call last):") is True

    @pytest.mark.unit
    def test_detects_failure(self):
        assert _is_error_result("Build failed with 3 errors") is True

    @pytest.mark.unit
    def test_clean_output(self):
        assert _is_error_result("Build succeeded. 0 warnings.") is False

    @pytest.mark.unit
    def test_empty_string(self):
        assert _is_error_result("") is False


class TestHasNotableContent:
    """Tests for content worth noting."""

    @pytest.mark.unit
    def test_detects_python_file(self):
        assert _has_notable_content("Modified scripts/search.py") is True

    @pytest.mark.unit
    def test_detects_function_def(self):
        assert _has_notable_content("def calculate_score():") is True

    @pytest.mark.unit
    def test_detects_class(self):
        assert _has_notable_content("class SearchEngine:") is True

    @pytest.mark.unit
    def test_plain_text(self):
        assert _has_notable_content("Hello world") is False


class TestExtractErrorPattern:
    """Tests for error line extraction."""

    @pytest.mark.unit
    def test_extracts_first_error_line(self):
        text = "line 1\nError: something broke\nline 3"
        result = _extract_error_pattern(text)
        assert "Error: something broke" in result

    @pytest.mark.unit
    def test_truncates_long_patterns(self):
        text = "Error: " + "x" * 300
        result = _extract_error_pattern(text)
        assert len(result) <= 200

    @pytest.mark.unit
    def test_no_error_line_uses_start(self):
        text = "some output"
        result = _extract_error_pattern(text)
        assert result == "some output"


class TestAnalyzeToolResult:
    """Tests for the analysis dispatch logic."""

    @pytest.mark.unit
    def test_error_generates_learning_suggestion(self):
        result = _analyze_tool_result("Bash", "Error: permission denied")
        assert "<memory-suggestion>" in result
        assert "type: learning" in result
        assert "Bash" in result

    @pytest.mark.unit
    def test_notable_content_generates_observation(self):
        result = _analyze_tool_result("Read", "Content of search.py")
        assert "<memory-suggestion>" in result
        assert "type: observation" in result

    @pytest.mark.unit
    def test_plain_output_generates_nothing(self):
        result = _analyze_tool_result("Bash", "12345")
        assert result == ""


class TestFormatErrorSuggestion:
    """Tests for error suggestion formatting."""

    @pytest.mark.unit
    def test_contains_required_fields(self):
        result = _format_error_suggestion("Bash", "Error: timeout")
        assert "<memory-suggestion>" in result
        assert "</memory-suggestion>" in result
        assert "type: learning" in result
        assert "trigger: Bash failure" in result
        assert "citation: tool_result:Bash" in result


class TestFormatContentSuggestion:
    """Tests for content suggestion formatting."""

    @pytest.mark.unit
    def test_contains_required_fields(self):
        result = _format_content_suggestion("Read", "Found def my_func():")
        assert "<memory-suggestion>" in result
        assert "</memory-suggestion>" in result
        assert "type: observation" in result
        assert "citation: tool_result:Read" in result
