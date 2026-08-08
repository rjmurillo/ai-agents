"""Tests for the memory index token-count repair and verifier."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import update_memory_index_tokens as tokens  # noqa: E402


def _memory_tree(tmp_path: Path) -> tuple[Path, Path]:
    memories = tmp_path / ".serena" / "memories"
    memories.mkdir(parents=True)
    memory = memories / "entry.md"
    memory.write_text("one two three\n", encoding="utf-8")
    index = memories / "memory-index.md"
    index.write_text("[Entry](entry.md) (1)\n", encoding="utf-8")
    return memories, index


def test_check_reports_stale_without_modifying_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memories, index = _memory_tree(tmp_path)
    monkeypatch.setattr(tokens, "get_memory_token_count", lambda _path: 3)
    original = index.read_bytes()

    rc = tokens.run(index, memories, check=True)

    assert rc == 1
    assert index.read_bytes() == original


def test_repair_and_check_share_the_same_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memories, index = _memory_tree(tmp_path)
    monkeypatch.setattr(tokens, "get_memory_token_count", lambda _path: 3)

    assert tokens.run(index, memories, check=False) == 0
    assert index.read_text(encoding="utf-8") == "[Entry](entry.md) (3)\n"
    assert tokens.run(index, memories, check=True) == 0


def test_check_fails_when_token_counter_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memories, index = _memory_tree(tmp_path)

    def fail_count(_path: Path) -> int:
        raise OSError("cannot read memory")

    monkeypatch.setattr(tokens, "get_memory_token_count", fail_count)

    assert tokens.run(index, memories, check=True) == 1


def test_check_fails_when_index_references_missing_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memories = tmp_path / ".serena" / "memories"
    memories.mkdir(parents=True)
    valid_memory = memories / "entry.md"
    valid_memory.write_text("one two three\n", encoding="utf-8")
    monkeypatch.setattr(tokens, "get_memory_token_count", lambda _path: 3)
    index = memories / "memory-index.md"
    index.write_text(
        "[Entry](entry.md) (3)\n[Missing](missing.md) (1)\n",
        encoding="utf-8",
    )

    assert tokens.run(index, memories, check=True) == 1


def test_check_fails_when_index_contains_no_memory_links(tmp_path: Path) -> None:
    memories = tmp_path / ".serena" / "memories"
    memories.mkdir(parents=True)
    index = memories / "memory-index.md"
    index.write_text("# Empty index\n", encoding="utf-8")

    assert tokens.run(index, memories, check=True) == 1


def test_main_check_fails_when_tiktoken_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tokens, "HAS_TIKTOKEN", False)

    rc = tokens.main(["--check"], repo_root=tmp_path)

    assert rc == 2
