"""CLI contract tests for count_memory_tokens.py: help works, output is bounded."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import count_memory_tokens as cmt


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    """A memory directory with 5 files; token counts are stubbed to 10, 20, 30, 40, 50."""
    root = tmp_path / "memories"
    root.mkdir()
    for index in range(1, 6):
        (root / f"m{index}.md").write_text("x", encoding="utf-8")

    def fake_count_directory(path, pattern, cache, force):
        return {path / f"m{i}.md": i * 10 for i in range(1, 6)}

    monkeypatch.setattr(cmt, "_HAS_TIKTOKEN", True)
    monkeypatch.setattr(cmt, "count_directory", fake_count_directory)
    monkeypatch.setattr(cmt, "validate_path_no_traversal", lambda p: Path(p))
    return root


class TestHelpWithoutTiktoken:
    def test_help_exits_0_and_prints_usage(self, monkeypatch, capsys):
        monkeypatch.setattr(cmt, "_HAS_TIKTOKEN", False)

        with pytest.raises(SystemExit) as exc:
            cmt.main(["--help"])

        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "usage:" in out
        assert "--limit" in out

    def test_counting_without_tiktoken_exits_1_and_names_the_install_command(
        self, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr(cmt, "_HAS_TIKTOKEN", False)

        rc = cmt.main([str(tmp_path)])

        captured = capsys.readouterr()
        assert rc == 1
        assert captured.out == ""
        assert "Expected: pip install tiktoken" in captured.err


class TestBoundedListing:
    def test_limit_lists_the_largest_files_and_totals_every_file(self, memory_dir, capsys):
        rc = cmt.main([str(memory_dir), "--limit", "2"])

        captured = capsys.readouterr()
        assert rc == 0
        assert "m5.md: 50 tokens" in captured.out
        assert "m4.md: 40 tokens" in captured.out
        assert "m1.md" not in captured.out
        assert "Total: 150 tokens across 5 files" in captured.out
        assert "Showing the 2 largest of 5 files" in captured.err

    def test_limit_zero_lists_every_file(self, memory_dir, capsys):
        rc = cmt.main([str(memory_dir), "--limit", "0"])

        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out.count(" tokens\n") == 5
        assert "Showing" not in captured.err

    def test_default_limit_leaves_a_small_directory_unchanged(self, memory_dir, capsys):
        rc = cmt.main([str(memory_dir)])

        captured = capsys.readouterr()
        assert rc == 0
        assert "m1.md: 10 tokens" in captured.out
        assert "Showing" not in captured.err

    def test_limit_equal_to_the_file_count_prints_no_notice(self, memory_dir, capsys):
        rc = cmt.main([str(memory_dir), "--limit", "5"])

        assert rc == 0
        assert "Showing" not in capsys.readouterr().err

    def test_negative_limit_exits_1_and_says_the_expected_range(self, memory_dir, capsys):
        rc = cmt.main([str(memory_dir), "--limit", "-1"])

        captured = capsys.readouterr()
        assert rc == 1
        assert "--limit must be 0 or greater" in captured.err
        assert captured.out == ""
