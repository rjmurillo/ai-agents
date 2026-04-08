"""Tests for the post_tool_call_memory hook (fact capture)."""

from __future__ import annotations

import io

import pytest

from memory_enhancement.extraction import (
    extract_error_pattern,
    format_suggestion,
    has_error_indicators,
    has_notable_content,
)
from memory_enhancement.hooks.post_tool_call_memory import (
    _analyze_tool_result,
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


class TestHasNotableContent:
    """Tests for content worth noting."""

    @pytest.mark.unit
    def test_detects_python_file(self):
        assert has_notable_content("Modified scripts/search.py") is True

    @pytest.mark.unit
    def test_detects_function_def(self):
        assert has_notable_content("def calculate_score():") is True

    @pytest.mark.unit
    def test_detects_class(self):
        assert has_notable_content("class SearchEngine:") is True

    @pytest.mark.unit
    def test_plain_text(self):
        assert has_notable_content("Hello world") is False


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
    def test_notable_content_generates_observation(self):
        result = _analyze_tool_result("Read", "Content of search.py")
        assert "<memory-suggestion>" in result
        assert "type: observation" in result

    @pytest.mark.unit
    def test_plain_output_generates_nothing(self):
        result = _analyze_tool_result("Bash", "12345")
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
