"""Tests for convert_memory_references.py."""

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import convert_memory_references


class TestConvertBacktickRefs:
    """Tests for convert_backtick_refs function."""

    def test_converts_known_memory(self):
        content = "See `test-memory` for details."
        names = {"test-memory": True}
        result = convert_memory_references.convert_backtick_refs(content, names)
        assert "[test-memory](test-memory.md)" in result

    def test_skips_unknown(self):
        content = "See `unknown-ref` for details."
        names = {"test-memory": True}
        result = convert_memory_references.convert_backtick_refs(content, names)
        assert "`unknown-ref`" in result
        assert "[unknown-ref]" not in result

    def test_skips_file_paths(self):
        content = "See `src/main.py` for details."
        names = {"src": True}
        result = convert_memory_references.convert_backtick_refs(content, names)
        # Paths with / should not match the pattern
        assert "src/main.py" in result

    def test_skips_already_linked(self):
        content = "See [`test-memory`](other.md) for details."
        names = {"test-memory": True}
        result = convert_memory_references.convert_backtick_refs(content, names)
        # Should not double-link
        assert result.count("[test-memory]") <= 1

    def test_multiple_refs(self):
        content = "Use `mem-a` and `mem-b` together."
        names = {"mem-a": True, "mem-b": True}
        result = convert_memory_references.convert_backtick_refs(content, names)
        assert "[mem-a](mem-a.md)" in result
        assert "[mem-b](mem-b.md)" in result


class TestProcessFiles:
    """Integration tests for process_files function."""

    def test_processes_all_md_files(self, tmp_path):
        (tmp_path / "target.md").write_text("# Target")
        (tmp_path / "source.md").write_text("See `target` for info.")

        stats = convert_memory_references.process_files(tmp_path, None, True)
        assert stats["FilesProcessed"] >= 1

    def test_respects_files_filter(self, tmp_path):
        (tmp_path / "target.md").write_text("# Target")
        source = tmp_path / "source.md"
        source.write_text("See `target` for info.")

        stats = convert_memory_references.process_files(
            tmp_path, [source], True
        )
        assert stats["FilesProcessed"] == 1

    def test_empty_dir(self, tmp_path):
        stats = convert_memory_references.process_files(tmp_path, None, True)
        assert stats["FilesProcessed"] == 0


class TestGetMemoryNames:
    """Tests for get_memory_names function."""

    def test_strips_extension(self, tmp_path):
        (tmp_path / "my-memory.md").write_text("# Test")
        names = convert_memory_references.get_memory_names(tmp_path)
        assert "my-memory" in names
        assert "my-memory.md" not in names


class TestCountMdLinks:
    """Tests for count_md_links function."""

    def test_counts_correctly(self):
        assert convert_memory_references.count_md_links("[a](a.md)") == 1
        assert convert_memory_references.count_md_links("no links") == 0
