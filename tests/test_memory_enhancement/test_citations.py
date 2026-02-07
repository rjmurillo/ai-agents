"""Tests for memory_enhancement.citations."""

import os

from memory_enhancement.citations import (
    verify_all_memories,
    verify_citation,
    verify_memory,
)
from memory_enhancement.models import Citation, Memory


class TestVerifyCitation:
    """Tests for verify_citation."""

    def test_file_not_found(self, tmp_path):
        citation = Citation(path="nonexistent.py")
        result = verify_citation(citation, tmp_path)

        assert result.valid is False
        assert "File not found" in result.mismatch_reason

    def test_file_exists_no_line(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")
        citation = Citation(path="exists.py")
        result = verify_citation(citation, tmp_path)

        assert result.valid is True

    def test_valid_line_no_snippet(self, tmp_path):
        (tmp_path / "code.py").write_text("line1\nline2\nline3\n")
        citation = Citation(path="code.py", line=2)
        result = verify_citation(citation, tmp_path)

        assert result.valid is True

    def test_valid_line_with_matching_snippet(self, tmp_path):
        (tmp_path / "code.py").write_text("import os\ndef main():\n    pass\n")
        citation = Citation(path="code.py", line=2, snippet="def main():")
        result = verify_citation(citation, tmp_path)

        assert result.valid is True

    def test_snippet_mismatch(self, tmp_path):
        (tmp_path / "code.py").write_text("import os\ndef other():\n    pass\n")
        citation = Citation(path="code.py", line=2, snippet="def main():")
        result = verify_citation(citation, tmp_path)

        assert result.valid is False
        assert "Snippet mismatch" in result.mismatch_reason

    def test_line_exceeds_file_length(self, tmp_path):
        (tmp_path / "short.py").write_text("line1\nline2\n")
        citation = Citation(path="short.py", line=10)
        result = verify_citation(citation, tmp_path)

        assert result.valid is False
        assert "exceeds file length" in result.mismatch_reason

    def test_invalid_line_number_zero(self, tmp_path):
        (tmp_path / "code.py").write_text("content\n")
        citation = Citation(path="code.py", line=0)
        result = verify_citation(citation, tmp_path)

        assert result.valid is False
        assert "must be >= 1" in result.mismatch_reason

    def test_invalid_line_number_negative(self, tmp_path):
        (tmp_path / "code.py").write_text("content\n")
        citation = Citation(path="code.py", line=-1)
        result = verify_citation(citation, tmp_path)

        assert result.valid is False

    def test_snippet_substring_match(self, tmp_path):
        (tmp_path / "code.py").write_text("    API_VERSION = 'v2'  # constant\n")
        citation = Citation(path="code.py", line=1, snippet="API_VERSION")
        result = verify_citation(citation, tmp_path)

        assert result.valid is True

    def test_nested_path(self, tmp_path):
        nested = tmp_path / "src" / "lib"
        nested.mkdir(parents=True)
        (nested / "util.py").write_text("helper\n")
        citation = Citation(path="src/lib/util.py", line=1)
        result = verify_citation(citation, tmp_path)

        assert result.valid is True

    def test_success_clears_mismatch_reason(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")
        citation = Citation(path="exists.py")
        result = verify_citation(citation, tmp_path)

        assert result.valid is True
        assert result.mismatch_reason is None

    def test_reverification_clears_stale_mismatch_reason(self, tmp_path):
        citation = Citation(path="target.py")
        # First call: file missing
        verify_citation(citation, tmp_path)
        assert citation.valid is False
        assert citation.mismatch_reason is not None

        # Create the file, re-verify
        (tmp_path / "target.py").write_text("content\n")
        verify_citation(citation, tmp_path)
        assert citation.valid is True
        assert citation.mismatch_reason is None

    def test_oserror_on_unreadable_file(self, tmp_path):
        target = tmp_path / "locked.py"
        target.write_text("content\n")
        os.chmod(target, 0o000)
        try:
            citation = Citation(path="locked.py", line=1)
            result = verify_citation(citation, tmp_path)

            assert result.valid is False
            assert "Cannot read file" in result.mismatch_reason
        finally:
            os.chmod(target, 0o644)

    def test_success_path_with_line_has_none_mismatch_reason(self, tmp_path):
        (tmp_path / "code.py").write_text("import os\ndef main():\n    pass\n")
        citation = Citation(path="code.py", line=2, snippet="def main():")
        result = verify_citation(citation, tmp_path)

        assert result.valid is True
        assert result.mismatch_reason is None


class TestVerifyMemory:
    """Tests for verify_memory."""

    def test_memory_with_no_citations(self, tmp_path):
        memory = Memory(
            id="no-cite",
            subject="test",
            path=tmp_path / "test.md",
            content="",
            confidence=0.7,
        )
        result = verify_memory(memory, tmp_path)

        assert result.valid is True
        assert result.total_citations == 0
        assert result.confidence == 0.7

    def test_memory_all_valid(self, tmp_path):
        (tmp_path / "a.py").write_text("line1\nline2\n")
        (tmp_path / "b.py").write_text("hello\n")

        memory = Memory(
            id="all-valid",
            subject="test",
            path=tmp_path / "test.md",
            content="",
            citations=[
                Citation(path="a.py", line=1),
                Citation(path="b.py"),
            ],
        )
        result = verify_memory(memory, tmp_path)

        assert result.valid is True
        assert result.total_citations == 2
        assert result.valid_count == 2
        assert result.confidence == 1.0
        assert result.stale_citations == []

    def test_memory_some_stale(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")

        memory = Memory(
            id="some-stale",
            subject="test",
            path=tmp_path / "test.md",
            content="",
            citations=[
                Citation(path="exists.py"),
                Citation(path="missing.py"),
            ],
        )
        result = verify_memory(memory, tmp_path)

        assert result.valid is False
        assert result.valid_count == 1
        assert result.total_citations == 2
        assert result.confidence == 0.5
        assert len(result.stale_citations) == 1

    def test_memory_all_stale(self, tmp_path):
        memory = Memory(
            id="all-stale",
            subject="test",
            path=tmp_path / "test.md",
            content="",
            citations=[
                Citation(path="gone1.py"),
                Citation(path="gone2.py"),
            ],
        )
        result = verify_memory(memory, tmp_path)

        assert result.valid is False
        assert result.confidence == 0.0


class TestVerifyAllMemories:
    """Tests for verify_all_memories."""

    def test_empty_directory(self, tmp_path):
        results = verify_all_memories(tmp_path, tmp_path)
        assert results == []

    def test_skips_memories_without_citations(self, tmp_path):
        (tmp_path / "no-cite.md").write_text("Just text, no frontmatter.\n")
        results = verify_all_memories(tmp_path, tmp_path)
        assert results == []

    def test_verifies_memories_with_citations(self, tmp_path):
        (tmp_path / "target.py").write_text("code here\n")
        (tmp_path / "cited.md").write_text(
            "---\n"
            "id: mem-cited\n"
            "citations:\n"
            "  - path: target.py\n"
            "    line: 1\n"
            "---\n"
            "\n"
            "Content.\n"
        )
        results = verify_all_memories(tmp_path, tmp_path)
        assert len(results) == 1
        assert results[0].valid is True

    def test_handles_parse_errors_gracefully(self, tmp_path, capsys):
        bad_file = tmp_path / "bad.md"
        bad_file.write_text(
            "---\n"
            "citations:\n"
            "  - invalid_yaml: [broken\n"
            "---\n"
        )
        results = verify_all_memories(tmp_path, tmp_path)
        captured = capsys.readouterr()
        assert len(results) == 0
        assert "Warning" in captured.err

    def test_multiple_memories(self, tmp_path):
        (tmp_path / "code.py").write_text("hello\n")

        (tmp_path / "mem1.md").write_text(
            "---\n"
            "id: mem-1\n"
            "citations:\n"
            "  - path: code.py\n"
            "---\n"
            "\n"
            "Content 1.\n"
        )
        (tmp_path / "mem2.md").write_text(
            "---\n"
            "id: mem-2\n"
            "citations:\n"
            "  - path: missing.py\n"
            "---\n"
            "\n"
            "Content 2.\n"
        )

        results = verify_all_memories(tmp_path, tmp_path)
        assert len(results) == 2
        valid_ids = [r.memory_id for r in results if r.valid]
        stale_ids = [r.memory_id for r in results if not r.valid]
        assert "mem-1" in valid_ids
        assert "mem-2" in stale_ids
