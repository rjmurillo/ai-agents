#!/usr/bin/env python3
"""Tests for fix_fences module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/fix-markdown-fences/fix_fences.py")
repair_markdown_fences = mod.repair_markdown_fences
fix_fences = mod.fix_fences
main = mod.main


class TestRepairMarkdownFences:
    """Tests for repair_markdown_fences function."""

    def test_no_change_for_valid_fences(self) -> None:
        content = "```python\nprint('hello')\n```\n"
        result = repair_markdown_fences(content)
        assert result == content

    def test_fixes_closing_fence_with_language(self) -> None:
        content = "```python\ncode1\n```python\ncode2\n```\n"
        result = repair_markdown_fences(content)
        assert result.count("```python") == 2
        # Should have inserted a closing ``` before the second opening
        lines = result.split("\n")
        assert lines[2] == "```"

    def test_adds_closing_fence_at_eof(self) -> None:
        content = "```python\nunclosed block"
        result = repair_markdown_fences(content)
        assert result.endswith("```")

    def test_preserves_indentation(self) -> None:
        content = "  ```python\n  code\n  ```python\n  more code\n  ```\n"
        result = repair_markdown_fences(content)
        lines = result.split("\n")
        # Should have a closing fence with matching indent before second opening
        assert "  ```" in lines

    def test_handles_empty_content(self) -> None:
        result = repair_markdown_fences("")
        assert result == ""

    def test_handles_no_code_blocks(self) -> None:
        content = "# Title\nSome text\nMore text\n"
        result = repair_markdown_fences(content)
        assert result == content

    def test_handles_multiple_valid_blocks(self) -> None:
        content = "```python\ncode\n```\n\n```bash\nscript\n```\n"
        result = repair_markdown_fences(content)
        assert result == content

    def test_handles_crlf_line_endings(self) -> None:
        content = "```python\r\ncode\r\n```\r\n"
        result = repair_markdown_fences(content)
        # Should handle CRLF properly
        assert "code" in result


class TestFixFences:
    """Tests for fix_fences function."""

    def test_fixes_files_in_directory(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("```python\ncode\n```python\nmore\n```\n")
        count = fix_fences([str(tmp_path)])
        assert count == 1
        fixed = md_file.read_text()
        assert fixed.count("```") >= 4  # Two opening + two closing

    def test_returns_zero_for_no_changes(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("```python\ncode\n```\n")
        count = fix_fences([str(tmp_path)])
        assert count == 0

    def test_skips_nonexistent_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        count = fix_fences([str(tmp_path / "nonexistent")])
        assert count == 0

    def test_respects_pattern_filter(self, tmp_path: Path) -> None:
        (tmp_path / "test.md").write_text("```python\ncode\n```python\nmore\n```\n")
        (tmp_path / "test.txt").write_text("```python\ncode\n```python\nmore\n```\n")
        count = fix_fences([str(tmp_path)], pattern="*.md")
        assert count == 1

    def test_processes_subdirectories(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "test.md").write_text("```python\ncode\n```python\nmore\n```\n")
        count = fix_fences([str(tmp_path)])
        assert count == 1

    def test_skips_empty_files(self, tmp_path: Path) -> None:
        (tmp_path / "empty.md").write_text("")
        count = fix_fences([str(tmp_path)])
        assert count == 0


class TestMain:
    """Tests for main entry point."""

    def test_returns_zero(self, tmp_path: Path) -> None:
        with patch("sys.argv", ["fix_fences.py", "--directories", str(tmp_path)]):
            result = main()
        assert result == 0

    def test_prints_no_files_message(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        with patch("sys.argv", ["fix_fences.py", "--directories", str(tmp_path)]):
            main()
        captured = capsys.readouterr()
        assert "No files needed fixing" in captured.out

    def test_prints_fixed_count(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        (tmp_path / "test.md").write_text("```python\ncode\n```python\nmore\n```\n")
        with patch("sys.argv", ["fix_fences.py", "--directories", str(tmp_path)]):
            main()
        captured = capsys.readouterr()
        assert "fixed 1 file(s)" in captured.out
