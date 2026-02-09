"""Tests for memory_enhancement.citations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from memory_enhancement.citations import (
    VerificationResult,
    verify_all_memories,
    verify_citation,
    verify_memory,
)
from memory_enhancement.models import Citation, Memory


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    @pytest.mark.unit
    def test_creation(self) -> None:
        r = VerificationResult(
            memory_id="test",
            valid=True,
            total_citations=3,
            valid_count=3,
            stale_citations=[],
            confidence=1.0,
        )
        assert r.memory_id == "test"
        assert r.valid is True
        assert r.total_citations == 3
        assert r.valid_count == 3
        assert r.stale_citations == []
        assert r.confidence == 1.0


class TestVerifyCitation:
    """Tests for verify_citation function."""

    @pytest.mark.unit
    def test_existing_file_no_line(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py")
        result = verify_citation(c, repo_root)
        assert result.valid is True
        assert result.mismatch_reason is None
        assert result is c

    @pytest.mark.unit
    def test_missing_file(self, repo_root: Path) -> None:
        c = Citation(path="src/nonexistent.py")
        verify_citation(c, repo_root)
        assert c.valid is False
        assert "File not found" in c.mismatch_reason

    @pytest.mark.unit
    def test_valid_line_number(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=2)
        verify_citation(c, repo_root)
        assert c.valid is True

    @pytest.mark.unit
    def test_line_out_of_range(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=999)
        verify_citation(c, repo_root)
        assert c.valid is False
        assert "exceeds file length" in c.mismatch_reason

    @pytest.mark.unit
    def test_invalid_line_number_zero(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=0)
        verify_citation(c, repo_root)
        assert c.valid is False
        assert "must be >= 1" in c.mismatch_reason

    @pytest.mark.unit
    def test_invalid_line_number_negative(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=-1)
        verify_citation(c, repo_root)
        assert c.valid is False
        assert "must be >= 1" in c.mismatch_reason

    @pytest.mark.unit
    def test_matching_snippet(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=2, snippet="def hello")
        verify_citation(c, repo_root)
        assert c.valid is True

    @pytest.mark.unit
    def test_mismatched_snippet(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=2, snippet="def wrong_name")
        verify_citation(c, repo_root)
        assert c.valid is False
        assert "Snippet mismatch" in c.mismatch_reason

    @pytest.mark.unit
    def test_path_traversal_blocked(self, repo_root: Path) -> None:
        c = Citation(path="../../../etc/passwd")
        verify_citation(c, repo_root)
        assert c.valid is False
        assert "Path traversal blocked" in c.mismatch_reason

    @pytest.mark.unit
    def test_unreadable_file(self, repo_root: Path) -> None:
        target = repo_root / "src" / "unreadable.py"
        target.write_text("line1\nline2\n", encoding="utf-8")

        c = Citation(path="src/unreadable.py", line=1)
        with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
            verify_citation(c, repo_root)
        assert c.valid is False
        assert "Cannot read file" in c.mismatch_reason

    @pytest.mark.unit
    def test_snippet_none_with_valid_line(self, repo_root: Path) -> None:
        c = Citation(path="src/example.py", line=1, snippet=None)
        verify_citation(c, repo_root)
        assert c.valid is True


class TestVerifyMemory:
    """Tests for verify_memory function."""

    @pytest.mark.unit
    def test_all_valid_citations(self, repo_root: Path) -> None:
        m = Memory(
            id="good",
            subject="Good",
            path=Path("x.md"),
            content="",
            citations=[
                Citation(path="src/example.py", line=2, snippet="def hello"),
                Citation(path="src/example.py", line=5, snippet="def goodbye"),
            ],
        )
        result = verify_memory(m, repo_root)
        assert result.valid is True
        assert result.total_citations == 2
        assert result.valid_count == 2
        assert result.stale_citations == []
        assert result.confidence == 1.0

    @pytest.mark.unit
    def test_some_stale_citations(self, repo_root: Path) -> None:
        m = Memory(
            id="mixed",
            subject="Mixed",
            path=Path("x.md"),
            content="",
            citations=[
                Citation(path="src/example.py", line=2, snippet="def hello"),
                Citation(path="src/nonexistent.py"),
            ],
        )
        result = verify_memory(m, repo_root)
        assert result.valid is False
        assert result.total_citations == 2
        assert result.valid_count == 1
        assert len(result.stale_citations) == 1
        assert result.confidence == 0.5

    @pytest.mark.unit
    def test_no_citations_uses_memory_confidence(self, repo_root: Path) -> None:
        m = Memory(
            id="no-cite",
            subject="No Cite",
            path=Path("x.md"),
            content="",
            confidence=0.75,
        )
        result = verify_memory(m, repo_root)
        assert result.valid is True
        assert result.total_citations == 0
        assert result.confidence == 0.75

    @pytest.mark.unit
    def test_memory_id_propagated(self, repo_root: Path) -> None:
        m = Memory(
            id="specific-id",
            subject="S",
            path=Path("x.md"),
            content="",
        )
        result = verify_memory(m, repo_root)
        assert result.memory_id == "specific-id"


class TestVerifyAllMemories:
    """Tests for verify_all_memories function."""

    @pytest.mark.unit
    def test_mixed_valid_and_stale(
        self, repo_root: Path, memories_dir: Path
    ) -> None:
        (memories_dir / "good.md").write_text(
            "---\n"
            "id: good\n"
            "subject: Good\n"
            "citations:\n"
            "  - path: src/example.py\n"
            "    line: 2\n"
            '    snippet: "def hello"\n'
            "---\n"
            "Good memory.\n",
            encoding="utf-8",
        )
        (memories_dir / "stale.md").write_text(
            "---\n"
            "id: stale\n"
            "subject: Stale\n"
            "citations:\n"
            "  - path: src/gone.py\n"
            "---\n"
            "Stale memory.\n",
            encoding="utf-8",
        )
        results = verify_all_memories(memories_dir, repo_root)
        assert len(results) == 2
        ids = {r.memory_id for r in results}
        assert "good" in ids
        assert "stale" in ids
        good_result = next(r for r in results if r.memory_id == "good")
        stale_result = next(r for r in results if r.memory_id == "stale")
        assert good_result.valid is True
        assert stale_result.valid is False

    @pytest.mark.unit
    def test_skips_memories_without_citations(
        self, repo_root: Path, memories_dir: Path
    ) -> None:
        (memories_dir / "no-cite.md").write_text(
            "---\nid: no-cite\nsubject: No Cite\n---\nBody.\n",
            encoding="utf-8",
        )
        results = verify_all_memories(memories_dir, repo_root)
        assert len(results) == 0

    @pytest.mark.unit
    def test_malformed_yaml_skipped(
        self, repo_root: Path, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (memories_dir / "bad.md").write_text(
            "---\n: invalid: yaml: [[[\n---\nBody.\n",
            encoding="utf-8",
        )
        results = verify_all_memories(memories_dir, repo_root)
        assert len(results) == 0
        captured = capsys.readouterr()
        assert "Warning" in captured.err or "Failed to parse" in captured.err

    @pytest.mark.unit
    def test_empty_directory(self, repo_root: Path, memories_dir: Path) -> None:
        results = verify_all_memories(memories_dir, repo_root)
        assert results == []
