"""Tests for the memory search engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory_enhancement.search import (
    SearchResult,
    _determine_citation_status,
    _parse_file_list,
    _search_with_grep,
    _search_with_ripgrep,
    rank_results,
    search_memories,
)


def _write_memory(tmp_path: Path, name: str, content: str = "Test content") -> Path:
    """Write a minimal memory file and return its path."""
    file_path = tmp_path / f"{name}.md"
    file_path.write_text(f"# {name} (2026-01-01)\n\n{content}\n")
    return file_path


class TestSearchMemories:
    """Integration tests for the top-level search function."""

    @pytest.mark.unit
    def test_empty_query_returns_empty(self, tmp_path: Path):
        assert search_memories("", tmp_path) == []

    @pytest.mark.unit
    def test_whitespace_query_returns_empty(self, tmp_path: Path):
        assert search_memories("   ", tmp_path) == []

    @pytest.mark.unit
    def test_nonexistent_directory_returns_empty(self, tmp_path: Path):
        assert search_memories("test", tmp_path / "no_such_dir") == []

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep", return_value=None)
    @patch("memory_enhancement.search._search_with_grep", return_value=None)
    def test_both_tools_fail_returns_empty(self, mock_grep, mock_rg, tmp_path: Path):
        _write_memory(tmp_path, "a")
        assert search_memories("test", tmp_path) == []

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep")
    def test_ripgrep_results_ranked(self, mock_rg, tmp_path: Path):
        f1 = _write_memory(tmp_path, "alpha", "Alpha memory content")
        f2 = _write_memory(tmp_path, "beta", "Beta memory content")
        mock_rg.return_value = [f1, f2]

        results = search_memories("memory", tmp_path, max_results=5, repo_root=tmp_path)
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    @pytest.mark.unit
    @patch("memory_enhancement.search._search_with_ripgrep", return_value=None)
    @patch("memory_enhancement.search._search_with_grep")
    def test_grep_fallback(self, mock_grep, mock_rg, tmp_path: Path):
        f1 = _write_memory(tmp_path, "gamma", "Gamma content")
        mock_grep.return_value = [f1]

        results = search_memories("content", tmp_path, repo_root=tmp_path)
        assert len(results) == 1
        assert results[0].memory_id == "gamma"


class TestSearchWithRipgrep:
    """Unit tests for ripgrep subprocess integration."""

    @pytest.mark.unit
    @patch("memory_enhancement.search.shutil.which", return_value=None)
    def test_rg_not_installed(self, mock_which, tmp_path: Path):
        assert _search_with_ripgrep("query", tmp_path) is None

    @pytest.mark.unit
    @patch("memory_enhancement.search.subprocess.run")
    @patch("memory_enhancement.search.shutil.which", return_value="/usr/bin/rg")
    def test_rg_returns_paths(self, mock_which, mock_run, tmp_path: Path):
        f1 = _write_memory(tmp_path, "one")
        mock_run.return_value = MagicMock(
            returncode=0, stdout=f"{f1}\n"
        )
        result = _search_with_ripgrep("test", tmp_path)
        assert result == [f1]

    @pytest.mark.unit
    @patch("memory_enhancement.search.subprocess.run")
    @patch("memory_enhancement.search.shutil.which", return_value="/usr/bin/rg")
    def test_rg_no_matches(self, mock_which, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = _search_with_ripgrep("nonexistent", tmp_path)
        assert result == []

    @pytest.mark.unit
    @patch("memory_enhancement.search.subprocess.run", side_effect=OSError("fail"))
    @patch("memory_enhancement.search.shutil.which", return_value="/usr/bin/rg")
    def test_rg_os_error(self, mock_which, mock_run, tmp_path: Path):
        assert _search_with_ripgrep("query", tmp_path) is None

    @pytest.mark.unit
    @patch("memory_enhancement.search.subprocess.run")
    @patch("memory_enhancement.search.shutil.which", return_value="/usr/bin/rg")
    def test_rg_bad_exit_code(self, mock_which, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=2, stdout="")
        assert _search_with_ripgrep("query", tmp_path) is None


class TestSearchWithGrep:
    """Unit tests for grep subprocess fallback."""

    @pytest.mark.unit
    @patch("memory_enhancement.search.shutil.which", return_value=None)
    def test_grep_not_installed(self, mock_which, tmp_path: Path):
        assert _search_with_grep("query", tmp_path) is None

    @pytest.mark.unit
    @patch("memory_enhancement.search.subprocess.run")
    @patch("memory_enhancement.search.shutil.which", return_value="/usr/bin/grep")
    def test_grep_returns_paths(self, mock_which, mock_run, tmp_path: Path):
        f1 = _write_memory(tmp_path, "found")
        mock_run.return_value = MagicMock(returncode=0, stdout=f"{f1}\n")
        result = _search_with_grep("test", tmp_path)
        assert result == [f1]


class TestRankResults:
    """Tests for result ranking by confidence."""

    @pytest.mark.unit
    def test_rank_empty_paths(self, tmp_path: Path):
        assert rank_results([], tmp_path) == []

    @pytest.mark.unit
    def test_rank_nonexistent_files_skipped(self, tmp_path: Path):
        bad_file = tmp_path / "nonexistent.md"
        assert rank_results([bad_file], tmp_path) == []

    @pytest.mark.unit
    def test_rank_limits_results(self, tmp_path: Path):
        paths = []
        for i in range(10):
            paths.append(_write_memory(tmp_path, f"mem{i}", f"Content {i}"))

        results = rank_results(paths, tmp_path, max_results=3)
        assert len(results) <= 3

    @pytest.mark.unit
    def test_rank_sorted_by_confidence(self, tmp_path: Path):
        paths = []
        for i in range(3):
            paths.append(_write_memory(tmp_path, f"item{i}"))

        results = rank_results(paths, tmp_path)
        confidences = [r.confidence for r in results]
        assert confidences == sorted(confidences, reverse=True)


class TestParseFileList:
    """Tests for stdout line parsing."""

    @pytest.mark.unit
    def test_empty_string(self, tmp_path):
        assert _parse_file_list("", tmp_path) == []

    @pytest.mark.unit
    def test_single_path(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("test")
        result = _parse_file_list(f"{f}\n", tmp_path)
        assert result == [f.resolve()]

    @pytest.mark.unit
    def test_multiple_paths(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("test")
        b.write_text("test")
        result = _parse_file_list(f"{a}\n{b}\n", tmp_path)
        assert result == [a.resolve(), b.resolve()]

    @pytest.mark.unit
    def test_blank_lines_ignored(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("test")
        result = _parse_file_list(f"\n{f}\n\n", tmp_path)
        assert result == [f.resolve()]


class TestDetermineCitationStatus:
    """Tests for citation status classification."""

    @pytest.mark.unit
    def test_no_results(self):
        assert _determine_citation_status([]) == "unverified"

    @pytest.mark.unit
    def test_all_valid(self):
        from memory_enhancement.models import Citation, SourceType, VerificationResult

        c = Citation(source_type=SourceType.FILE, target="x.py", context="")
        results = [VerificationResult(citation=c, is_valid=True, reason="ok")]
        assert _determine_citation_status(results) == "verified"

    @pytest.mark.unit
    def test_mixed_valid_invalid(self):
        from memory_enhancement.models import Citation, SourceType, VerificationResult

        c = Citation(source_type=SourceType.FILE, target="x.py", context="")
        results = [
            VerificationResult(citation=c, is_valid=True, reason="ok"),
            VerificationResult(citation=c, is_valid=False, reason="gone"),
        ]
        assert _determine_citation_status(results) == "stale"

    @pytest.mark.unit
    def test_all_invalid(self):
        from memory_enhancement.models import Citation, SourceType, VerificationResult

        c = Citation(source_type=SourceType.FILE, target="x.py", context="")
        results = [VerificationResult(citation=c, is_valid=False, reason="gone")]
        assert _determine_citation_status(results) == "broken"
