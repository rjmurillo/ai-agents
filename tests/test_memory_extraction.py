"""Tests for the extraction module."""

from __future__ import annotations

import pytest

from memory_enhancement.extraction import (
    extract_error_pattern,
    extract_facts,
    format_suggestion,
    has_error_indicators,
    has_notable_content,
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


class TestHasNotableContent:
    """Tests for notable content detection."""

    @pytest.mark.unit
    def test_detects_python_file(self):
        assert has_notable_content("Modified scripts/main.py") is True

    @pytest.mark.unit
    def test_detects_class_keyword(self):
        assert has_notable_content("class MyService:") is True

    @pytest.mark.unit
    def test_no_notable_content(self):
        assert has_notable_content("just plain text nothing special") is False

    @pytest.mark.unit
    def test_detects_function_keyword(self):
        assert has_notable_content("function handleRequest()") is True


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
    def test_truncates_long_pattern(self):
        long_error = "error: " + "x" * 500
        result = extract_error_pattern("tool", long_error)
        assert len(result["pattern"]) <= 200


class TestExtractFacts:
    """Tests for fact extraction from tool output."""

    @pytest.mark.unit
    def test_extracts_file_references(self):
        text = "Created file: src/main.py\nDone."
        facts = extract_facts("editor", text)
        assert len(facts) == 1
        assert facts[0]["tool_name"] == "editor"
        assert "main.py" in facts[0]["content"]
        assert facts[0]["type"] == "observation"

    @pytest.mark.unit
    def test_extracts_multiple_facts(self):
        text = "def foo():\nclass Bar:\nplain line"
        facts = extract_facts("reader", text)
        assert len(facts) == 2

    @pytest.mark.unit
    def test_empty_output_returns_empty(self):
        assert extract_facts("tool", "") == []

    @pytest.mark.unit
    def test_no_notable_lines_returns_empty(self):
        assert extract_facts("tool", "just text\nnothing here") == []

    @pytest.mark.unit
    def test_truncates_long_content(self):
        line = "def " + "x" * 500
        facts = extract_facts("tool", line)
        assert len(facts) == 1
        assert len(facts[0]["content"]) <= 300


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
    def test_formats_fact(self):
        facts = extract_facts("reader", "class MyClass:")
        output = format_suggestion(facts[0])
        assert "<memory-suggestion>" in output
        assert "type: observation" in output
        assert "reader output" in output

    @pytest.mark.unit
    def test_includes_citation(self):
        pattern = {"tool_name": "test", "type": "learning", "pattern": "err"}
        output = format_suggestion(pattern)
        assert "citation: tool_result:test" in output
