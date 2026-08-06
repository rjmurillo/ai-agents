"""Tests for update_memory_index_tokens --check mode (issue #4441).

The check mode exits non-zero when any recorded token count differs from the
computed count. It does not modify the file. Nothing previously verified
counts in reverse.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import scripts.update_memory_index_tokens as umt


class TestCheckMode:
    """--check exits 1 on drift, 0 when counts match, and never writes."""

    def _make_index(self, tmp_path: Path, content: str) -> Path:
        idx = tmp_path / "memory-index.md"
        idx.write_text(content, encoding="utf-8")
        return idx

    def _make_memory(self, tmp_path: Path, name: str, token_count: int) -> Path:
        mem = tmp_path / name
        mem.parent.mkdir(parents=True, exist_ok=True)
        # Write enough content so that the token counter returns the expected value.
        mem.write_text("x " * token_count, encoding="utf-8")
        return mem

    def test_check_returns_0_when_all_counts_are_current(self, tmp_path: Path) -> None:
        idx = self._make_index(
            tmp_path,
            "| kw | [mem](sub/mem.md) (42) |\n",
        )
        memories_dir = tmp_path

        with mock.patch.object(umt, "get_memory_token_count", return_value=42):
            (tmp_path / "sub").mkdir()
            (tmp_path / "sub/mem.md").write_text("x", encoding="utf-8")
            drifted = umt.check_memory_index(idx, memories_dir)

        assert drifted == []

    def test_check_returns_drift_list_when_count_is_wrong(self, tmp_path: Path) -> None:
        idx = self._make_index(
            tmp_path,
            "| kw | [mem](sub/mem.md) (0) |\n",
        )
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub/mem.md").write_text("x", encoding="utf-8")

        with mock.patch.object(umt, "get_memory_token_count", return_value=891):
            drifted = umt.check_memory_index(idx, tmp_path)

        assert len(drifted) == 1
        assert "891" in drifted[0]
        assert "0" in drifted[0]

    def test_check_does_not_modify_the_file(self, tmp_path: Path) -> None:
        content = "| kw | [mem](sub/mem.md) (0) |\n"
        idx = self._make_index(tmp_path, content)
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub/mem.md").write_text("x", encoding="utf-8")

        with mock.patch.object(umt, "get_memory_token_count", return_value=891):
            umt.check_memory_index(idx, tmp_path)

        assert idx.read_text(encoding="utf-8") == content

    def test_check_skips_missing_file(self, tmp_path: Path) -> None:
        idx = self._make_index(
            tmp_path,
            "| kw | [missing](missing.md) (0) |\n",
        )
        drifted = umt.check_memory_index(idx, tmp_path)
        assert drifted == []

    def test_main_check_flag_exits_1_on_drift(self, tmp_path: Path) -> None:
        idx = tmp_path / "memory-index.md"
        idx.write_text("| kw | [mem](mem.md) (0) |\n", encoding="utf-8")
        (tmp_path / "mem.md").write_text("x", encoding="utf-8")

        with mock.patch.object(umt, "get_memory_token_count", return_value=891):
            drifted = umt.check_memory_index(idx, tmp_path)
        assert drifted, "expected drift to be detected when recorded=0 actual=891"

    def test_main_check_flag_exits_0_when_current(self, tmp_path: Path) -> None:
        idx = tmp_path / "memory-index.md"
        idx.write_text("| kw | [mem](mem.md) (42) |\n", encoding="utf-8")
        (tmp_path / "mem.md").write_text("x", encoding="utf-8")

        with mock.patch.object(umt, "get_memory_token_count", return_value=42):
            drifted = umt.check_memory_index(idx, tmp_path)
        assert drifted == []
