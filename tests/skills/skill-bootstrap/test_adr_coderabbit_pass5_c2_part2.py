"""Tests for CodeRabbit pass 5 on PR #7527, group C2, part 2: the create-only write and the
main work tree on git with no ``worktree list -z``."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import adr_scan
import adr_write
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, write
from draft_helpers import _cand, _scan_file

_REAL_UNLINK = os.unlink


def _stuck_temp(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make removing a hidden ``*.tmp`` file fail; every other removal runs. Returns the tries."""
    tried: list[str] = []

    def unlink(path: Any, *args: Any, **kwargs: Any) -> None:
        name = os.path.basename(os.fspath(path))
        if name.startswith(".") and name.endswith(".tmp"):
            tried.append(name)
            raise PermissionError(13, "Permission denied", os.fspath(path))
        _REAL_UNLINK(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)
    return tried


def _decision_repo(tmp_path: Path) -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Adopt Postgres instead of MySQL\n\nBecause the team already runs it.\n")
    return repo


# --- C210: a cleanup failure never hides a published file or a primary error ---


def test_a_cleanup_failure_after_publication_returns_the_leftover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tried = _stuck_temp(monkeypatch)
    target = tmp_path / "0002-x.md"

    leftover = adr_write.create_new(target, b"body")

    assert tried and target.read_bytes() == b"body"
    assert leftover is not None and leftover.name == tried[0] and leftover.exists()


def test_a_temporary_file_already_gone_counts_as_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "0002-x.md"
    real_link = os.link

    def link_then_drop(source: str, name: Path) -> None:
        real_link(source, name)
        _REAL_UNLINK(source)

    monkeypatch.setattr(os, "link", link_then_drop)

    assert adr_write.create_new(target, b"body") is None
    assert target.read_bytes() == b"body" and os.listdir(tmp_path) == ["0002-x.md"]


def test_a_draft_whose_temporary_file_stays_still_reports_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _decision_repo(tmp_path)
    scan = _scan_file(tmp_path, repo, _cand())
    _stuck_temp(monkeypatch)
    out = repo / "docs" / "adr"

    code = bootstrap_adr.main(["draft", "--scan", scan, "--id", "c-1234567", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0 and Path(payload["path"]).is_file() and payload["number"] == 2
    assert Path(payload["leftover"]).parent == out


def test_a_scan_whose_temporary_file_stays_still_reports_its_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _decision_repo(tmp_path)
    _stuck_temp(monkeypatch)
    out = tmp_path / "scan.json"

    code = bootstrap_adr.main(["scan", "--repo", str(repo), "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0 and payload["out"] == str(out) and out.is_file()
    assert Path(payload["leftover"]).parent == tmp_path


def test_an_existing_target_stays_exists_when_cleanup_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "0002-x.md"
    target.write_bytes(b"mine")
    _stuck_temp(monkeypatch)

    with pytest.raises(FileExistsError):
        adr_write.create_new(target, b"new")
    assert target.read_bytes() == b"mine"


def test_a_failed_write_in_place_keeps_its_error_when_removal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "0002-x.md"

    def no_links(source: str, name: Path) -> None:
        raise PermissionError(1, "Operation not permitted")

    class Full:
        def __init__(self, path: Path, mode: str) -> None:
            self._handle = open(path, mode)

        def __enter__(self) -> Full:
            return self

        def __exit__(self, *exc: object) -> None:
            self._handle.close()

        def write(self, data: bytes) -> int:
            raise OSError(28, "No space left on device")

    def no_unlink(path: Any, *args: Any, **kwargs: Any) -> None:
        raise PermissionError(13, "Permission denied", os.fspath(path))

    monkeypatch.setattr(os, "link", no_links)
    monkeypatch.setattr(adr_write, "open", Full, raising=False)
    monkeypatch.setattr(os, "unlink", no_unlink)

    with pytest.raises(OSError, match="No space left") as caught:
        adr_write.create_new(target, b"body")
    assert caught.value.errno == 28


# --- C211: the legacy inventory never takes a separate git dir for the main work tree ---


def _without_z(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``worktree list -z`` fail as git before 2.36 does; every other call runs git."""
    real = adr_scan.git_bytes

    def old_git(repo: Path, *args: str, stdin: bytes | None = None) -> Any:
        if "-z" in args:
            return subprocess.CompletedProcess(args, 129, b"", b"error: unknown switch `z'")
        return real(repo, *args, stdin=stdin)

    monkeypatch.setattr(adr_scan, "git_bytes", old_git)
    monkeypatch.setattr(adr_write, "git_bytes", old_git)


def _separate(tmp_path: Path) -> tuple[Path, Path]:
    """A main work tree whose git dir is kept apart, and a linked work tree of it."""
    main = tmp_path / "main"
    git(tmp_path, "init", "-q", "-b", "main", f"--separate-git-dir={tmp_path / 'sep.git'}", "main")
    commit(main, "Initial work")
    git(main, "worktree", "add", "-q", "--detach", str(tmp_path / "wt"))
    return main.resolve(), (tmp_path / "wt").resolve()


def test_a_linked_tree_of_a_separate_git_dir_refuses_out_in_the_main_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, linked = _separate(tmp_path)
    nested = new_repo(main / "nested")
    _without_z(monkeypatch)

    with pytest.raises(adr_scan.ConfigError, match="main work tree"):
        adr_write.work_trees(linked)
    with pytest.raises(adr_scan.ConfigError, match="main work tree"):
        adr_write.out_outside_repo(linked, str(nested / "report.json"))


def test_the_main_tree_of_a_separate_git_dir_lists_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main, linked = _separate(tmp_path)
    _without_z(monkeypatch)

    assert adr_write.work_trees(main) == [main, linked]
    target = adr_write.out_outside_repo(main, str(tmp_path / "out" / "report.json"))
    assert target == (tmp_path / "out" / "report.json").resolve()
