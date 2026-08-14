"""Tests for the extraction module."""

from __future__ import annotations

import pytest

from memory_enhancement.extraction import (
    extract_error_pattern,
    format_suggestion,
    has_error_indicators,
)


class TestHasErrorIndicators:
    """Tests for error indicator detection."""

    @pytest.mark.unit
    def test_detects_error_keyword(self):
        assert has_error_indicators("Something went Error here") is True

    @pytest.mark.unit
    def test_detects_traceback(self):
        assert has_error_indicators("Traceback (most recent call last):") is True

    @pytest.mark.unit
    def test_no_error_in_clean_output(self):
        assert has_error_indicators("All good, operation succeeded") is False

    @pytest.mark.unit
    def test_empty_string(self):
        assert has_error_indicators("") is False

    @pytest.mark.unit
    def test_case_insensitive(self):
        assert has_error_indicators("PERMISSION DENIED") is True

    @pytest.mark.unit
    def test_ignores_an_indicator_inside_an_identifier(self):
        assert has_error_indicators("analyze_pr_failure.py\ntest_error_handling.py") is False

    @pytest.mark.unit
    def test_still_detects_an_indicator_inside_an_exception_name(self):
        assert has_error_indicators("ValueError: bad value") is True

    @pytest.mark.unit
    def test_still_detects_a_plural_indicator(self):
        assert has_error_indicators("Found 3 errors") is True


class TestExtractErrorPattern:
    """Tests for error pattern extraction."""

    @pytest.mark.unit
    def test_extracts_error_line(self):
        error_text = "line 1 ok\nValueError: bad value\nline 3"
        result = extract_error_pattern("test_tool", error_text)
        assert result["tool_name"] == "test_tool"
        assert "bad value" in result["pattern"]
        assert "test_tool" in result["suggested_memory"]

    @pytest.mark.unit
    def test_falls_back_to_truncated_text(self):
        result = extract_error_pattern("tool", "no errors here")
        assert result["pattern"] == "no errors here"

    @pytest.mark.unit
    def test_flattens_multiline_fallback(self):
        result = extract_error_pattern("tool", "Exit code 1\nplain failing output")
        assert result["pattern"] == "Exit code 1 plain failing output"

    @pytest.mark.unit
    def test_truncates_long_pattern(self):
        long_error = "error: " + "x" * 500
        result = extract_error_pattern("tool", long_error)
        assert len(result["pattern"]) <= 200


class TestFormatSuggestion:
    """Tests for suggestion formatting."""

    @pytest.mark.unit
    def test_formats_error_pattern(self):
        pattern = extract_error_pattern("grep", "Error: file not found")
        output = format_suggestion(pattern)
        assert "<memory-suggestion>" in output
        assert "</memory-suggestion>" in output
        assert "grep failure" in output
        assert "pattern:" in output

    @pytest.mark.unit
    def test_formats_observation_dict(self):
        output = format_suggestion(
            {"tool_name": "reader", "type": "observation", "content": "class MyClass:"}
        )
        assert "<memory-suggestion>" in output
        assert "type: observation" in output
        assert "reader output" in output

    @pytest.mark.unit
    def test_includes_citation(self):
        pattern = {"tool_name": "test", "type": "learning", "pattern": "err"}
        output = format_suggestion(pattern)
        assert "citation: tool_result:test" in output
