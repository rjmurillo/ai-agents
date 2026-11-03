"""The write-time check vouches only for the file it read, and failures stay legible (#7034)."""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path

import api_examples as ax
import pytest
from test_evidence_install import NEW, _after_check, _names, _write_prior

pytestmark = pytest.mark.skipif(
    not ax._ANCHORED_WRITES, reason="needs O_NOFOLLOW, dir_fd, and hard link support"
)


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_report_swapped_in_only_for_the_read_cannot_vouch_for_another_file(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lstat sees file X, the open reads report R, then X returns: X must survive."""
    evidence = work / "evidence.json"
    evidence.write_text("unrelated file\n", encoding="utf-8")
    report = work / "report"
    _write_prior(report)
    real_open = os.open

    def swap_for_the_read(
        path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        if path == "evidence.json" and not flags & os.O_CREAT:
            evidence.rename(work / "hold")
            report.rename(evidence)
            fd = real_open(path, flags, mode, dir_fd=dir_fd)
            (work / "hold").rename(evidence)
            return fd
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(ax, "_check_evidence_path", lambda raw: Path(raw))
    monkeypatch.setattr(ax.os, "open", swap_for_the_read)

    with pytest.raises(ax.InputError, match="not a prior evidence report"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_text(encoding="utf-8") == "unrelated file\n"
    assert _names(work) == ["evidence.json"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_fifo_swapped_in_before_the_read_is_refused_without_hanging(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)
    real_open = os.open

    def fifo_for_the_read(
        path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        if path == "evidence.json" and not flags & os.O_CREAT:
            evidence.unlink()
            os.mkfifo(evidence)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(ax.os, "open", fifo_for_the_read)

    with pytest.raises(ax.InputError, match="not a prior evidence report"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert stat.S_ISFIFO(evidence.lstat().st_mode)


def test_same_size_rewrite_with_a_new_mtime_is_put_back_and_refused(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    prior = _write_prior(evidence)
    same_size = prior.replace(b'"PASS"', b'"FAIL"')
    assert len(same_size) == len(prior)

    def rewrite() -> None:
        before = evidence.stat().st_mtime_ns
        evidence.write_bytes(same_size)
        os.utime(evidence, ns=(before + 1_000_000, before + 1_000_000))

    _after_check(monkeypatch, rewrite)

    with pytest.raises(ax.InputError, match="changed after the check"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_bytes() == same_size
    assert _names(work) == ["evidence.json"]


def test_new_target_on_a_filesystem_without_hard_links_names_the_cause(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EOPNOTSUPP, "Operation not supported")

    monkeypatch.setattr(ax.os, "link", no_links)

    with pytest.raises(ax.InputError, match="does not support hard links.*stdout"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert _names(work) == []


def test_failed_cleanup_of_the_old_copy_keeps_the_new_report(
    work: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)
    real_unlink = os.unlink

    def keep_old(path: str, *, dir_fd: int | None = None) -> None:
        if path.endswith(".old"):
            raise OSError(errno.EIO, "Input/output error")
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(ax.os, "unlink", keep_old)

    ax._write_evidence(Path("evidence.json"), NEW)

    assert json.loads(evidence.read_text(encoding="utf-8")) == NEW
    assert "could not remove" in capsys.readouterr().err
