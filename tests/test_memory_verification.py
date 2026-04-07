"""Tests for citation verification strategies."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_enhancement.models import (
    Citation,
    CitationStatus,
    MemoryWithCitations,
    SourceType,
)
from memory_enhancement.verification import (
    find_stale_citations,
    verify_all_citations,
    verify_citation,
)


class TestVerifyFileCitation:
    """File citation verification: file existence and line count."""

    @pytest.mark.unit
    def test_valid_file(self, tmp_path):
        (tmp_path / "exists.py").write_text("line1\nline2\n")
        c = Citation(source_type=SourceType.FILE, target="exists.py", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_missing_file(self, tmp_path):
        c = Citation(source_type=SourceType.FILE, target="missing.py", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "not found" in result.reason.lower()

    @pytest.mark.unit
    def test_valid_file_with_line(self, tmp_path):
        (tmp_path / "lines.py").write_text("a\nb\nc\n")
        c = Citation(source_type=SourceType.FILE, target="lines.py:2", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_file_line_exceeds_length(self, tmp_path):
        (tmp_path / "short.py").write_text("only one line\n")
        c = Citation(source_type=SourceType.FILE, target="short.py:99", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "exceeds" in result.reason.lower()

    @pytest.mark.unit
    def test_file_line_zero_rejected(self, tmp_path):
        """Line number 0 is invalid (1-indexed); must be rejected."""
        (tmp_path / "file.py").write_text("line1\nline2\n")
        c = Citation(source_type=SourceType.FILE, target="file.py:0", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "1" in result.reason

    @pytest.mark.unit
    def test_invalid_file_format(self, tmp_path):
        """Empty target now raises ValueError at Citation construction."""
        with pytest.raises(ValueError, match="non-empty"):
            Citation(source_type=SourceType.FILE, target="", context="")

    @pytest.mark.unit
    def test_path_traversal_blocked(self, tmp_path):
        """CWE-22: paths that escape repo_root must be rejected."""
        c = Citation(source_type=SourceType.FILE, target="../../etc/passwd", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "traversal" in result.reason.lower()

    @pytest.mark.unit
    def test_function_path_traversal_blocked(self, tmp_path):
        """CWE-22: function citations with traversal paths must be rejected."""
        c = Citation(source_type=SourceType.FUNCTION, target="../../etc/passwd::func", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "traversal" in result.reason.lower()


    @pytest.mark.unit
    def test_verify_file_line_oserror(self, tmp_path, monkeypatch):
        target = tmp_path / "unreadable.py"
        target.write_text("line1\nline2\n")
        c = Citation(
            source_type=SourceType.FILE, target="unreadable.py:1", context=""
        )

        def _raise_oserror(*_a, **_kw):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "open", _raise_oserror)
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "cannot read" in result.reason.lower()


class TestVerifyFunctionCitation:
    """Function citation verification: file exists and function defined."""

    @pytest.mark.unit
    def test_valid_function(self, tmp_path):
        (tmp_path / "module.py").write_text("def my_func():\n    pass\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::my_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_missing_function(self, tmp_path):
        (tmp_path / "module.py").write_text("def other():\n    pass\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::missing_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_invalid_function_format(self, tmp_path):
        c = Citation(
            source_type=SourceType.FUNCTION, target="no_separator", context=""
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_function_file_missing(self, tmp_path):
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="missing.py::func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False


    @pytest.mark.unit
    def test_search_function_oserror(self, tmp_path, monkeypatch):
        target = tmp_path / "module.py"
        target.write_text("def my_func():\n    pass\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::my_func",
            context="",
        )

        def _raise_oserror(*_a, **_kw):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", _raise_oserror)
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "cannot read" in result.reason.lower()


class TestVerifyIssuePrCitation:
    """Issue and PR citation format validation."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "source_type", [SourceType.ISSUE, SourceType.PR]
    )
    def test_valid_format_hash_prefix(self, tmp_path, source_type):
        c = Citation(source_type=source_type, target="#123", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_valid_format_bare_number(self, tmp_path):
        c = Citation(source_type=SourceType.ISSUE, target="456", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_invalid_format(self, tmp_path):
        c = Citation(source_type=SourceType.ISSUE, target="not-a-number", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False


class TestVerifyMemoryCitation:
    """Memory citation verification against .serena/memories/ directory."""

    @pytest.mark.unit
    def test_valid_memory(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "target-memory.md").write_text("# Target\n")
        c = Citation(
            source_type=SourceType.MEMORY, target="target-memory", context=""
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_missing_memory(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        c = Citation(
            source_type=SourceType.MEMORY, target="nonexistent", context=""
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_memory_path_traversal_blocked(self, tmp_path):
        """CWE-22: memory citations with traversal paths must be rejected."""
        c = Citation(
            source_type=SourceType.MEMORY,
            target="../../etc/passwd",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "traversal" in result.reason.lower()


class TestVerifyAdrCitation:
    """ADR citation verification against .agents/architecture/ directory."""

    @pytest.mark.unit
    def test_valid_adr(self, tmp_path):
        adr_dir = tmp_path / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-007.md").write_text("# ADR 007\n")
        c = Citation(source_type=SourceType.ADR, target="ADR-007", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_missing_adr(self, tmp_path):
        adr_dir = tmp_path / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        c = Citation(source_type=SourceType.ADR, target="ADR-999", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_adr_path_traversal_blocked(self, tmp_path):
        """CWE-22: ADR citations with traversal paths must be rejected."""
        c = Citation(
            source_type=SourceType.ADR,
            target="../../etc/passwd",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "traversal" in result.reason.lower()


class TestVerifyUrlCitation:
    """URL citation format validation."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "url",
        ["https://example.com", "http://localhost:8080"],
    )
    def test_valid_url(self, tmp_path, url):
        c = Citation(source_type=SourceType.URL, target=url, context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_invalid_url(self, tmp_path):
        c = Citation(source_type=SourceType.URL, target="not-a-url", context="")
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False


class TestVerifyAllCitations:
    """Bulk verification of all citations in a memory."""

    @pytest.mark.unit
    def test_verify_all(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")
        memory = MemoryWithCitations(
            memory_id="test",
            title="Test",
            content="body",
            citations=[
                Citation(source_type=SourceType.FILE, target="exists.py", context=""),
                Citation(source_type=SourceType.FILE, target="missing.py", context=""),
            ],
        )
        results = verify_all_citations(memory, tmp_path)
        assert len(results) == 2
        assert results[0].is_valid is True
        assert results[1].is_valid is False


class TestFindStaleCitations:
    """Find stale/broken citations across multiple memories."""

    @pytest.mark.unit
    def test_finds_broken_citations(self, tmp_path):
        memories = [
            MemoryWithCitations(
                memory_id="m1",
                title="M1",
                content="",
                citations=[
                    Citation(
                        source_type=SourceType.FILE,
                        target="missing.py",
                        context="",
                    )
                ],
            )
        ]
        stale = find_stale_citations(memories, tmp_path)
        assert len(stale) == 1
        assert stale[0][0] == "m1"

    @pytest.mark.unit
    def test_find_stale_citations_empty_list(self, tmp_path):
        result = find_stale_citations([], tmp_path)
        assert result == []

    @pytest.mark.unit
    def test_no_stale_when_all_valid(self, tmp_path):
        (tmp_path / "exists.py").write_text("ok\n")
        memories = [
            MemoryWithCitations(
                memory_id="m1",
                title="M1",
                content="",
                citations=[
                    Citation(
                        source_type=SourceType.FILE,
                        target="exists.py",
                        context="",
                    )
                ],
            )
        ]
        stale = find_stale_citations(memories, tmp_path)
        assert len(stale) == 0
