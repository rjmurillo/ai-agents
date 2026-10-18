"""Descriptor handling in ``prune_branch_config._backup_config`` (issue #6506).

``os.fdopen`` owns the descriptor only once it returns. If it raises, the
descriptor from ``os.open`` must be closed by ``_backup_config`` itself.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest import mock

import pytest

from scripts.maintenance import prune_branch_config as mod


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.write_text("[core]\n\tbare = false\n", encoding="utf-8")
    return config


def test_backup_closes_the_descriptor_when_fdopen_fails(tmp_path: Path) -> None:
    config = _config(tmp_path)
    opened: list[int] = []
    closed: list[int] = []
    real_open = mod.os.open
    real_close = mod.os.close

    def spy_open(path: Path, flags: int, mode: int = 0o777) -> int:
        fd = real_open(path, flags, mode)
        opened.append(fd)
        return fd

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    with (
        mock.patch.object(mod.os, "open", side_effect=spy_open),
        mock.patch.object(mod.os, "close", side_effect=spy_close),
        mock.patch.object(mod.os, "fdopen", side_effect=OSError("no memory")),
        pytest.raises(mod.GitError, match="could not write config backup"),
    ):
        mod._backup_config(config)

    assert len(opened) == 1
    assert closed == opened
    assert not config.with_name("config.before-prune").exists()


def test_backup_leaves_closing_to_the_file_object_on_success(tmp_path: Path) -> None:
    config = _config(tmp_path)
    closed: list[int] = []
    real_close = mod.os.close

    def spy_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    with mock.patch.object(mod.os, "close", side_effect=spy_close):
        backup = mod._backup_config(config)

    assert backup.read_bytes() == config.read_bytes()
    assert closed == []


def _fail_write_after(action: Callable[[], None]) -> AbstractContextManager[object]:
    """Patch ``os.fchmod`` to run ``action`` and then fail, after the write."""

    def failing(_fd: int, _mode: int) -> None:
        action()
        raise OSError("disk full")

    return mock.patch.object(mod.os, "fchmod", side_effect=failing, create=True)


@pytest.mark.skipif(not hasattr(mod.os, "fchmod"), reason="fchmod is POSIX only")
def test_failed_write_removes_the_backup_it_created(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backup = config.with_name("config.before-prune")

    with _fail_write_after(lambda: None), pytest.raises(mod.GitError, match="could not write"):
        mod._backup_config(config)

    assert not backup.exists()
    assert not backup.is_symlink()


@pytest.mark.skipif(not hasattr(mod.os, "fchmod"), reason="fchmod is POSIX only")
def test_failed_write_keeps_an_entry_swapped_in_at_the_backup_name(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backup = config.with_name("config.before-prune")
    victim = tmp_path / "victim"
    victim.write_text("keep me", encoding="utf-8")

    def swap() -> None:
        backup.unlink()
        backup.write_text("someone else's file", encoding="utf-8")

    with _fail_write_after(swap), pytest.raises(mod.GitError, match="could not write"):
        mod._backup_config(config)

    assert backup.read_text(encoding="utf-8") == "someone else's file"
    assert victim.read_text(encoding="utf-8") == "keep me"


@pytest.mark.skipif(not hasattr(mod.os, "fchmod"), reason="fchmod is POSIX only")
def test_failed_write_keeps_a_symlink_swapped_in_at_the_backup_name(tmp_path: Path) -> None:
    config = _config(tmp_path)
    backup = config.with_name("config.before-prune")
    target = tmp_path / "target"
    target.write_text("keep me", encoding="utf-8")

    def swap() -> None:
        backup.unlink()
        backup.symlink_to(target)

    with _fail_write_after(swap), pytest.raises(mod.GitError, match="could not write"):
        mod._backup_config(config)

    assert backup.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep me"


def test_remove_own_backup_ignores_a_missing_pathname(tmp_path: Path) -> None:
    created = _config(tmp_path).stat()

    mod._remove_own_backup(tmp_path / "gone", created)

    assert not (tmp_path / "gone").exists()


def test_remove_own_backup_removes_nothing_without_an_identity(tmp_path: Path) -> None:
    entry = tmp_path / "entry"
    entry.write_text("data", encoding="utf-8")

    mod._remove_own_backup(entry, None)

    assert entry.read_text(encoding="utf-8") == "data"
