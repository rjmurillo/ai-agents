"""Descriptor handling in ``prune_branch_config._backup_config`` (issue #6506).

``os.fdopen`` owns the descriptor only once it returns. If it raises, the
descriptor from ``os.open`` must be closed by ``_backup_config`` itself.
"""

from __future__ import annotations

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
