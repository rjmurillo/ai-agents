"""Tests for the no-follow file helpers in scripts/eval/_controller_io.py.

Every controller read or write of a file a child could have replaced goes
through `read_private`, `write_private`, or the digest's `_file_digest`. These
pin what each refuses: a link at the leaf, a link above it, a hard link, a
FIFO (which must not hang the controller), and a missing file.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

_EVAL = Path(__file__).resolve().parents[2] / "scripts" / "eval"
sys.path.insert(0, str(_EVAL))

import _controller_io as io  # noqa: E402
from _controller_config import ControllerError  # noqa: E402

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX links and FIFOs")


def _victim(tmp_path: Path) -> Path:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    return victim


def test_read_private_reads_a_plain_file(tmp_path: Path) -> None:
    path = tmp_path / "f.json"
    path.write_bytes(b'{"a": 1}')
    assert io.read_private(path, "results") == b'{"a": 1}'


def test_read_private_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ControllerError, match="results .* is not a regular file"):
        io.read_private(tmp_path / "absent", "results")


@posix_only
def test_read_private_refuses_a_leaf_link(tmp_path: Path) -> None:
    link = tmp_path / "f.json"
    link.symlink_to(_victim(tmp_path))
    with pytest.raises(ControllerError, match="not a regular file with one link"):
        io.read_private(link, "results")


def test_read_private_refuses_a_hard_link(tmp_path: Path) -> None:
    path = tmp_path / "f.json"
    os.link(_victim(tmp_path), path)
    with pytest.raises(ControllerError, match="one link"):
        io.read_private(path, "results")


def test_read_private_refuses_a_directory(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    with pytest.raises(ControllerError, match="not a regular file"):
        io.read_private(tmp_path / "d", "results")


@posix_only
@pytest.mark.timeout(30)
def test_read_private_refuses_a_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "f.json"
    os.mkfifo(fifo)
    with pytest.raises(ControllerError, match="not a regular file"):
        io.read_private(fifo, "results")


def test_write_private_creates_a_new_file(tmp_path: Path) -> None:
    path = tmp_path / "tasks.txt"
    io.write_private(path, "a\nb\n")
    assert path.read_text(encoding="utf-8") == "a\nb\n"


def test_write_private_writes_bytes_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "task.json"
    io.write_private(path, b'{"id": "\xff"}')
    assert path.read_bytes() == b'{"id": "\xff"}'


def test_write_private_create_refuses_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "tasks.txt"
    path.write_text("old", encoding="utf-8")
    with pytest.raises(ControllerError, match="not a regular file the controller made"):
        io.write_private(path, "new")
    assert path.read_text(encoding="utf-8") == "old"


@posix_only
@pytest.mark.parametrize("append", [False, True])
def test_write_private_never_writes_through_a_link(tmp_path: Path, append: bool) -> None:
    victim = _victim(tmp_path)
    link = tmp_path / "log.jsonl"
    link.symlink_to(victim)
    with pytest.raises(ControllerError):
        io.write_private(link, "planted\n", append=append)
    assert victim.read_text(encoding="utf-8") == "keep"


@posix_only
def test_write_private_never_writes_through_a_dangling_link(tmp_path: Path) -> None:
    target = tmp_path / "would-be-created"
    link = tmp_path / "tasks.txt"
    link.symlink_to(target)
    with pytest.raises(ControllerError):
        io.write_private(link, "x")
    assert not target.exists()


def test_write_private_append_refuses_a_hard_link(tmp_path: Path) -> None:
    victim = _victim(tmp_path)
    path = tmp_path / "log.jsonl"
    os.link(victim, path)
    with pytest.raises(ControllerError):
        io.write_private(path, "planted\n", append=True)
    assert victim.read_text(encoding="utf-8") == "keep"


def test_write_private_append_creates_then_appends(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    io.write_private(path, "one\n", append=True)
    io.write_private(path, "two\n", append=True)
    assert path.read_text(encoding="utf-8") == "one\ntwo\n"


@posix_only
@pytest.mark.timeout(30)
def test_write_private_append_refuses_a_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "log.jsonl"
    os.mkfifo(fifo)
    with pytest.raises(ControllerError):
        io.write_private(fifo, "x\n", append=True)


def test_is_real_dir_accepts_a_plain_directory(tmp_path: Path) -> None:
    (tmp_path / "runs" / "r").mkdir(parents=True)
    assert io.is_real_dir(tmp_path.resolve() / "runs" / "r")


def test_is_real_dir_rejects_a_file_and_a_missing_path(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")
    assert not io.is_real_dir(tmp_path.resolve() / "f")
    assert not io.is_real_dir(tmp_path.resolve() / "absent")


@posix_only
@pytest.mark.parametrize("swap", ["leaf", "parent"])
def test_is_real_dir_rejects_a_link_at_the_leaf_or_above(tmp_path: Path, swap: str) -> None:
    root = tmp_path.resolve()
    elsewhere = root / "elsewhere" / "r"
    elsewhere.mkdir(parents=True)
    if swap == "leaf":
        (root / "runs").mkdir()
        (root / "runs" / "r").symlink_to(elsewhere)
    else:
        (root / "runs").symlink_to(elsewhere.parent)
    assert not io.is_real_dir(root / "runs" / "r")


@posix_only
@pytest.mark.timeout(30)
def test_file_digest_does_not_block_on_a_file_swapped_for_a_fifo(tmp_path: Path) -> None:
    # `tree_digest` checks `is_file()` and then reads; a FIFO swapped in
    # between must read as unreadable, not block the controller forever.
    fifo = tmp_path / "b"
    os.mkfifo(fifo)
    assert io._file_digest(fifo) == "unreadable"


def test_tree_digest_still_sees_a_content_change(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    before = io.tree_digest([tmp_path])
    path.write_text("y", encoding="utf-8")
    assert io.tree_digest([tmp_path]) != before
    path.write_text("x", encoding="utf-8")
    assert io.tree_digest([tmp_path]) == before


@posix_only
def test_read_artifact_refuses_a_link_swapped_in(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.symlink_to(_victim(tmp_path))
    with pytest.raises(ControllerError, match="no longer a regular file"):
        io.read_artifact(artifact)


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EACCES])
def test_open_errors_other_than_a_refusal_name_their_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    # A full disk or a denied permission is not tampering; say what it is.
    if code == errno.EACCES and sys.platform == "win32":
        pytest.skip("Windows reports a directory as EACCES, so it is a refusal there")
    path = tmp_path / "f.txt"

    def failing(*_args: object, **_kwargs: object) -> int:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(io.os, "open", failing)
    with pytest.raises(ControllerError, match=f"could not open {path}: {os.strerror(code)}"):
        io.write_private(path, "x")


def test_collect_into_reports_a_failed_move_and_collect_all_keeps_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "a.xml", tmp_path / "b.xml"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    real_move = io.shutil.move

    def flaky(source: str, destination: str) -> object:
        if source == str(first):
            raise OSError(errno.EIO, "disk error")
        return real_move(source, destination)

    monkeypatch.setattr(io.shutil, "move", flaky)
    problems = io.collect_all([str(first), str(second)], {}, run_dir)
    assert problems == [f"could not move scorer output {first}: [Errno {errno.EIO}] disk error"]
    assert (run_dir / "1").read_text(encoding="utf-8") == "b"
