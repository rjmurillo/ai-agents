"""Tests for the user_prompt_submit_memory hook (auto-recall)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from memory_enhancement.hooks.user_prompt_submit_memory import (
    _extract_query,
    _find_repo_root,
    _format_memory_context,
    _read_user_input,
    _search_and_format,
)
from memory_enhancement.search import SearchResult


class TestExtractQuery:
    """Tests for stop word filtering and term extraction."""

    @pytest.mark.unit
    def test_filters_stop_words(self):
        result = _extract_query("the quick brown fox is running")
        assert "the" not in result
        assert "is" not in result
        assert "quick" in result

    @pytest.mark.unit
    def test_filters_short_tokens(self):
        result = _extract_query("a b cd efg hij")
        assert "a" not in result.split()
        assert "b" not in result.split()
        assert "cd" not in result.split()

    @pytest.mark.unit
    def test_takes_top_5_terms(self):
        result = _extract_query("alpha beta gamma delta epsilon zeta eta")
        terms = result.split()
        assert len(terms) <= 5

    @pytest.mark.unit
    def test_empty_input_returns_empty(self):
        assert _extract_query("") == ""

    @pytest.mark.unit
    def test_only_stop_words_returns_empty(self):
        assert _extract_query("the and is for") == ""

    @pytest.mark.unit
    def test_lowercases_input(self):
        result = _extract_query("MEMORY Enhancement Layer")
        assert "memory" in result
        assert "enhancement" in result


class TestReadUserInput:
    """Tests for stdin parsing."""

    @pytest.mark.unit
    def test_json_with_query_field(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO('{"query": "test search"}'))
        result = _read_user_input()
        assert result == "test search"

    @pytest.mark.unit
    def test_json_with_prompt_field(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hello world"}'))
        result = _read_user_input()
        assert result == "hello world"

    @pytest.mark.unit
    def test_plain_text_input(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("plain text query"))
        result = _read_user_input()
        assert result == "plain text query"

    @pytest.mark.unit
    def test_empty_stdin(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        result = _read_user_input()
        assert result == ""


class TestFindRepoRoot:
    """Tests for repository root detection."""

    @pytest.mark.unit
    def test_finds_git_directory(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        result = _find_repo_root(sub)
        assert result == tmp_path

    @pytest.mark.unit
    def test_returns_none_when_no_git(self, tmp_path: Path):
        result = _find_repo_root(tmp_path)
        # tmp_path may be inside the actual repo, so check isolation
        # by checking that the function does walk upward
        assert result is None or (result / ".git").exists()


class TestFormatMemoryContext:
    """Tests for the stderr output format."""

    @pytest.mark.unit
    def test_format_single_result(self):
        result = SearchResult(
            memory_id="test-mem",
            file_path=Path("/tmp/test-mem.md"),
            confidence=0.85,
            title="Test Memory",
            snippet="This is a test snippet",
            citation_status="verified",
        )
        output = _format_memory_context([result])

        assert "<memory-context>" in output
        assert "</memory-context>" in output
        assert "Test Memory" in output
        assert "85%" in output
        assert "verified" in output
        assert "test-mem.md" in output

    @pytest.mark.unit
    def test_format_multiple_results(self):
        results = [
            SearchResult(
                memory_id=f"mem-{i}",
                file_path=Path(f"/tmp/mem-{i}.md"),
                confidence=0.5 + i * 0.1,
                title=f"Memory {i}",
                snippet=f"Snippet {i}",
                citation_status="unverified",
            )
            for i in range(3)
        ]
        output = _format_memory_context(results)
        assert output.count("###") == 3

    @pytest.mark.unit
    def test_format_empty_results(self):
        output = _format_memory_context([])
        assert "<memory-context>" in output
        assert "###" not in output


class TestSearchAndFormat:
    """Tests for the search-then-format pipeline."""

    @pytest.mark.unit
    @patch("memory_enhancement.search.search_memories")
    def test_returns_empty_when_no_results(self, mock_search, tmp_path: Path):
        mock_search.return_value = []
        result = _search_and_format("query", tmp_path, tmp_path)
        assert result == ""

    @pytest.mark.unit
    @patch("memory_enhancement.search.search_memories")
    def test_returns_formatted_when_results_found(self, mock_search, tmp_path: Path):
        mock_search.return_value = [
            SearchResult(
                memory_id="found",
                file_path=Path("/tmp/found.md"),
                confidence=0.9,
                title="Found Memory",
                snippet="A snippet",
                citation_status="verified",
            )
        ]
        result = _search_and_format("query", tmp_path, tmp_path)
        assert "<memory-context>" in result
        assert "Found Memory" in result
