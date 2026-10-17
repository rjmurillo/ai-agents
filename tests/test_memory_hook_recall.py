"""Tests for the user_prompt_submit_memory hook (auto-recall)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_enhancement.hooks.user_prompt_submit_memory import (
    _MIN_RELEVANCE,
    _extract_query,
    _find_repo_root,
    _format_memory_context,
    _read_user_input,
    _search_and_format,
    main,
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

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("prompt", "expected"),
        [
            ("how does pr-autofix work", "pr-autofix work"),
            ("please tell me about the worktree identity guard", "worktree identity guard"),
            ("why did lefthook skip cleanup", "lefthook skip cleanup"),
            ("could you explain or show the design index", "design index"),
            ("can we, should we, would we", ""),
        ],
    )
    def test_drops_question_and_request_filler(self, prompt: str, expected: str):
        assert _extract_query(prompt) == expected


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
        """Verify None is returned when no .git exists in any ancestor."""
        with patch.object(Path, "exists", return_value=False):
            result = _find_repo_root(tmp_path)
            assert result is None


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
            relevance=0.6,
        )
        output = _format_memory_context([result])

        assert "<memory-context>" in output
        assert "</memory-context>" in output
        assert "Test Memory" in output
        assert "confidence: 85%" in output
        assert "relevance: 60%" in output
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


class TestRelevanceFloor:
    """End to end: the hook injects nothing unless a memory matches the prompt."""

    @staticmethod
    def _repo(tmp_path: Path) -> Path:
        memories = tmp_path / ".serena" / "memories"
        memories.mkdir(parents=True)
        (tmp_path / ".git").mkdir()
        for name, body in (
            ("decision-worktree-identity-guard-scope", "Guards a worktree identity."),
            ("skills-design-index", "Index. Mentions hindsight mental model review."),
            ("orchestrator-observations", "Notes on subagents implement series."),
        ):
            (memories / f"{name}.md").write_text(
                f"# {name} (2026-01-01)\n\n{body}\n", encoding="utf-8"
            )
        return tmp_path

    @pytest.mark.unit
    def test_matching_prompt_is_recalled(self, tmp_path: Path):
        repo = self._repo(tmp_path)
        out = _search_and_format("worktree identity guards", repo / ".serena" / "memories", repo)
        assert "<memory-context>" in out
        assert "decision-worktree-identity-guard-scope" in out
        assert "relevance:" in out

    @pytest.mark.unit
    def test_question_phrased_prompt_is_recalled(self, tmp_path: Path):
        repo = self._repo(tmp_path)
        query = _extract_query("how does the worktree identity guard work")
        out = _search_and_format(query, repo / ".serena" / "memories", repo)
        assert "decision-worktree-identity-guard-scope" in out

    @pytest.mark.unit
    def test_unrelated_prompt_injects_nothing_despite_body_hits(self, tmp_path: Path):
        repo = self._repo(tmp_path)
        query = _extract_query("Load hindsight mental model review patterns and identify areas")
        assert _search_and_format(query, repo / ".serena" / "memories", repo) == ""

    @pytest.mark.unit
    def test_unrelated_prompt_main_prints_nothing(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps({"prompt": "in a series of subagents, implement"}))
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        assert main() == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.unit
    @patch("memory_enhancement.search.search_memories")
    def test_floor_is_passed_to_search(self, mock_search, tmp_path: Path):
        mock_search.return_value = []
        _search_and_format("query", tmp_path, tmp_path)
        assert mock_search.call_args.kwargs["min_relevance"] == _MIN_RELEVANCE

    @pytest.mark.unit
    def test_result_exactly_at_floor_is_injected(self, tmp_path: Path):
        repo = self._repo(tmp_path)
        # 1 of 2 terms names the memory: relevance 0.5 == _MIN_RELEVANCE.
        assert _MIN_RELEVANCE == 0.5
        out = _search_and_format("worktree unrelated", repo / ".serena" / "memories", repo)
        assert "decision-worktree-identity-guard-scope" in out
        assert "relevance: 50%" in out

    @pytest.mark.unit
    def test_empty_query_injects_nothing(self, tmp_path: Path):
        repo = self._repo(tmp_path)
        assert _search_and_format("", repo / ".serena" / "memories", repo) == ""


class TestExitContract:
    """UserPromptSubmit exit 2 erases the prompt, so recall must never use it.

    See issue #4011 and the per-event table in .project-toolkit/specs/hook-protocol.md.
    """

    @staticmethod
    def _repo(tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        return tmp_path

    @pytest.mark.unit
    def test_match_writes_stdout_and_returns_zero(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._search_and_format",
            lambda *_args: "<memory-context>hit</memory-context>",
        )

        exit_code = main()

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "<memory-context>" in captured.out
        assert captured.err == ""

    @pytest.mark.unit
    def test_no_match_returns_zero_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._search_and_format",
            lambda *_args: "",
        )

        exit_code = main()

        assert exit_code == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.unit
    def test_missing_memories_dir_returns_zero(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: tmp_path,
        )

        assert main() == 0
