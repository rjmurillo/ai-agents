"""Tests for memory-index token repair."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.update_memory_index_tokens as updater


def _write_memory(memories_dir: Path, name: str, content: str = "memory text\n") -> None:
    target = memories_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_update_line_adds_missing_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    _write_memory(memories_dir, "new.md")
    monkeypatch.setattr(updater, "get_memory_token_count", lambda _path: 5)

    updated = updater.update_line("|new row: [new](new.md)\n", memories_dir)

    assert updated == "|new row: [new](new.md) (5)\n"


def test_update_line_keeps_missing_memory_reference(tmp_path: Path) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    updated = updater.update_line("|missing: [missing](missing.md) (1)\n", memories_dir)

    assert updated == "|missing: [missing](missing.md) (1)\n"


def test_update_line_keeps_count_when_counter_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    _write_memory(memories_dir, "broken.md")

    def fail_count(_path: Path) -> int:
        raise OSError("cannot read")

    monkeypatch.setattr(updater, "get_memory_token_count", fail_count)

    updated = updater.update_line("|broken: [broken](broken.md) (1)\n", memories_dir)

    assert updated == "|broken: [broken](broken.md) (1)\n"
    assert "cannot read" in capsys.readouterr().err


def test_update_memory_index_collapses_duplicate_rows_after_counts_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    _write_memory(memories_dir, "shared.md")
    index_path = memories_dir / "memory-index.md"
    index_path.write_text(
        "[Section]\n"
        "|shared keywords: [shared](shared.md) (1)\n"
        "|shared keywords: [shared](shared.md) (2)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "get_memory_token_count", lambda _path: 7)

    modified = updater.update_memory_index(index_path, memories_dir)

    assert modified is True
    content = index_path.read_text(encoding="utf-8")
    assert content.count("[shared](shared.md)") == 1
    assert "|shared keywords: [shared](shared.md) (7)" in content


def test_update_memory_index_exits_when_index_is_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        updater.update_memory_index(tmp_path / "missing.md", tmp_path)

    assert exc.value.code == 1


def test_update_memory_index_allows_distinct_rows_that_share_a_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    _write_memory(memories_dir, "shared.md")
    index_path = memories_dir / "memory-index.md"
    index_path.write_text(
        "[Section]\n"
        "|first keywords: [shared](shared.md) (1)\n"
        "|second keywords: [shared](shared.md) (2)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "get_memory_token_count", lambda _path: 7)

    modified = updater.update_memory_index(index_path, memories_dir)

    content = index_path.read_text(encoding="utf-8")
    assert modified is True
    assert content.count("[shared](shared.md)") == 2
    assert "|first keywords: [shared](shared.md) (7)" in content
    assert "|second keywords: [shared](shared.md) (7)" in content


def test_update_memory_index_rejects_repeated_link_in_one_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()
    _write_memory(memories_dir, "shared.md")
    index_path = memories_dir / "memory-index.md"
    index_path.write_text(
        "[Section]\n"
        "|bad row: [shared](shared.md) (1), [shared](shared.md) (2)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "get_memory_token_count", lambda _path: 7)

    with pytest.raises(updater.DuplicateMemoryIndexEntryError):
        updater.update_memory_index(index_path, memories_dir)


def test_main_returns_nonzero_when_duplicate_rows_need_manual_merge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(updater, "HAS_TIKTOKEN", True)

    def fail_duplicate(_index_path: Path, _memories_dir: Path) -> bool:
        raise updater.DuplicateMemoryIndexEntryError("duplicate row")

    monkeypatch.setattr(updater, "update_memory_index", fail_duplicate)

    assert updater.main() == 1
    assert "duplicate row" in capsys.readouterr().err


def test_main_returns_two_when_tiktoken_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(updater, "HAS_TIKTOKEN", False)

    assert updater.main() == 2


@pytest.mark.parametrize(("modified", "message"), (
    (True, "Updated token counts"),
    (False, "already current"),
))
def test_main_reports_update_result(
    modified: bool,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(updater, "HAS_TIKTOKEN", True)
    monkeypatch.setattr(updater, "update_memory_index", lambda _index, _memories: modified)

    assert updater.main() == 0
    assert message in capsys.readouterr().out


def test_duplicate_row_from_union_merge_is_healed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Memory Merge Test"], cwd=repo, check=True)
    (repo / ".gitattributes").write_text(".serena/memories/memory-index.md merge=union\n")
    memories_dir = repo / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    _write_memory(memories_dir, "shared.md")
    index_path = memories_dir / "memory-index.md"
    index_path.write_text(
        "[Section]\n"
        "|shared keywords: [shared](shared.md) (1)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "base"], cwd=repo, check=True)

    subprocess.run(["git", "checkout", "--quiet", "-b", "left"], cwd=repo, check=True)
    index_path.write_text(
        "[Section]\n"
        "|shared keywords: [shared](shared.md) (2)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "left recount"], cwd=repo, check=True)

    subprocess.run(["git", "checkout", "--quiet", "-b", "right", "HEAD~1"], cwd=repo, check=True)
    index_path.write_text(
        "[Section]\n"
        "|shared keywords: [shared](shared.md) (3)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "right recount"], cwd=repo, check=True)

    subprocess.run(["git", "checkout", "--quiet", "left"], cwd=repo, check=True)
    subprocess.run(["git", "merge", "--no-edit", "right"], cwd=repo, check=True)
    assert index_path.read_text(encoding="utf-8").count("[shared](shared.md)") == 2

    monkeypatch.setattr(updater, "get_memory_token_count", lambda _path: 7)

    assert updater.update_memory_index(index_path, memories_dir) is True
    assert index_path.read_text(encoding="utf-8").count("[shared](shared.md)") == 1
