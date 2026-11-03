"""The ``--evidence`` install never replaces an entry it did not validate (#7034)."""

from __future__ import annotations

import errno
import json
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path

import api_examples as ax
import pytest
from api_fixtures import WORKED_EXAMPLE
from test_run import run_args

pytestmark = pytest.mark.skipif(
    not ax._ANCHORED_WRITES, reason="needs O_NOFOLLOW, dir_fd, and hard link support"
)

PRIOR = {"verdict": "PASS", "doc_sha256": {}, "executed": 0}
NEW = {"verdict": "PASS", "doc_sha256": {}, "executed": 1}


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_prior(path: Path) -> bytes:
    path.write_text(json.dumps(PRIOR), encoding="utf-8")
    return path.read_bytes()


def _after_check(monkeypatch: pytest.MonkeyPatch, action: Callable[[], object]) -> None:
    """Run ``action`` right after the write-time entry check returns."""
    real = ax._check_entry_at

    def checked_then_act(raw: str, parent_fd: int, name: str) -> os.stat_result | None:
        info: os.stat_result | None = real(raw, parent_fd, name)
        action()
        return info

    monkeypatch.setattr(ax, "_check_entry_at", checked_then_act)


def _names(path: Path) -> list[str]:
    return sorted(p.name for p in path.iterdir())


def test_file_created_by_another_writer_after_the_check_survives(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    _after_check(monkeypatch, lambda: evidence.write_text("other writer\n", encoding="utf-8"))

    with pytest.raises(ax.InputError, match="created by another writer"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_text(encoding="utf-8") == "other writer\n"
    assert _names(work) == ["evidence.json"]


def test_prior_report_swapped_for_another_file_is_put_back_and_refused(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)

    def swap() -> None:
        stranger = work / "stranger"
        stranger.write_text("not a report\n", encoding="utf-8")
        stranger.replace(evidence)

    _after_check(monkeypatch, swap)

    with pytest.raises(ax.InputError, match="changed after the check"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_text(encoding="utf-8") == "not a report\n"
    assert _names(work) == ["evidence.json"]


def test_prior_report_rewritten_in_place_is_put_back_and_refused(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)

    def rewrite() -> None:
        evidence.write_text("rewritten in place, longer than before\n", encoding="utf-8")

    _after_check(monkeypatch, rewrite)

    with pytest.raises(ax.InputError, match="changed after the check"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_text(encoding="utf-8") == "rewritten in place, longer than before\n"
    assert _names(work) == ["evidence.json"]


def test_prior_report_swapped_for_a_directory_is_put_back_and_refused(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)

    def swap() -> None:
        evidence.unlink()
        evidence.mkdir()
        (evidence / "keep.txt").write_text("keep\n", encoding="utf-8")

    _after_check(monkeypatch, swap)

    with pytest.raises(ax.InputError, match="changed after the check"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert (evidence / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert _names(work) == ["evidence.json"]


def test_prior_report_removed_after_the_check_is_written_as_new(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)
    _after_check(monkeypatch, evidence.unlink)

    ax._write_evidence(Path("evidence.json"), NEW)

    assert json.loads(evidence.read_text(encoding="utf-8")) == NEW
    assert _names(work) == ["evidence.json"]


def test_writer_that_claims_the_name_after_the_move_keeps_it_and_prior_is_kept_aside(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    prior = _write_prior(evidence)
    real = ax._same_entry

    def claim_then_compare(moved: os.stat_result, checked: os.stat_result) -> bool:
        evidence.write_text("claimed\n", encoding="utf-8")
        same: bool = real(moved, checked)
        return same

    monkeypatch.setattr(ax, "_same_entry", claim_then_compare)

    with pytest.raises(ax.InputError, match=r"prior report is kept at `\.evidence\.json\.") as err:
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_text(encoding="utf-8") == "claimed\n"
    aside = [p for p in work.iterdir() if p.name.endswith(".old")]
    assert len(aside) == 1
    assert aside[0].read_bytes() == prior
    assert aside[0].name in str(err.value)
    assert not [p for p in work.iterdir() if p.name.endswith((".tmp", ".probe"))]


def test_unchanged_prior_report_is_replaced_and_nothing_is_left_aside(work: Path) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)

    ax._write_evidence(Path("evidence.json"), NEW)

    assert json.loads(evidence.read_text(encoding="utf-8")) == NEW
    assert _names(work) == ["evidence.json"]


def test_filesystem_without_hard_links_leaves_prior_report_in_place(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    prior = _write_prior(evidence)

    def no_links(*_args: object, **_kwargs: object) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(ax.os, "link", no_links)

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_bytes() == prior
    assert _names(work) == ["evidence.json"]


def test_failed_install_after_the_move_puts_the_prior_report_back(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = work / "evidence.json"
    prior = _write_prior(evidence)
    real_link = os.link
    calls: list[str] = []

    def fail_install(src: str, dst: str, **kwargs: object) -> None:
        calls.append(dst)
        if dst == "evidence.json" and src.endswith(".tmp"):
            raise OSError(5, "Input/output error")
        real_link(src, dst, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ax.os, "link", fail_install)

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax._write_evidence(Path("evidence.json"), NEW)

    assert evidence.read_bytes() == prior
    assert _names(work) == ["evidence.json"]
    assert calls.count("evidence.json") == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_new_report_is_owner_only(work: Path) -> None:
    old_umask = os.umask(0o022)
    try:
        ax._write_evidence(Path("evidence.json"), NEW)
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE((work / "evidence.json").stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_replaced_report_is_owner_only(work: Path) -> None:
    evidence = work / "evidence.json"
    _write_prior(evidence)
    evidence.chmod(0o644)

    ax._write_evidence(Path("evidence.json"), NEW)

    assert stat.S_IMODE(evidence.stat().st_mode) == 0o600


def test_platform_without_anchored_writes_refuses_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ax, "_ANCHORED_WRITES", False)
    sent: list[str] = []

    def sender(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        sent.append(url)
        return ax.Reply(200, b"{}")

    with pytest.raises(ax.InputError, match="stdout"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], "http://127.0.0.1:1", tmp_path / "e.json"), sender)

    assert sent == []
    assert not (tmp_path / "e.json").exists()


def test_cli_exits_2_on_a_platform_without_anchored_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ax, "_ANCHORED_WRITES", False)

    code = ax.main(
        [
            "run",
            str(WORKED_EXAMPLE),
            "--base-url",
            "http://127.0.0.1:1",
            "--evidence",
            str(tmp_path / "e.json"),
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert code == ax.EXIT_UNVERIFIABLE
    assert out["verdict"] == "UNVERIFIED"
    assert "save the report printed to stdout" in out["error"]


def test_report_swapped_in_only_for_the_read_cannot_vouch_for_another_file(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lstat sees file X, the open reads report R, then X returns: X must survive."""
    evidence = work / "evidence.json"
    evidence.write_text("unrelated file\n", encoding="utf-8")
    report = work / "report"
    _write_prior(report)
    real_open = os.open

    def swap_for_the_read(path: str, flags: int, *args: object, **kwargs: object) -> int:
        if path == "evidence.json" and not flags & os.O_CREAT:
            evidence.rename(work / "hold")
            report.rename(evidence)
            fd = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
            (work / "hold").rename(evidence)
            return fd
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

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

    def fifo_for_the_read(path: str, flags: int, *args: object, **kwargs: object) -> int:
        if path == "evidence.json" and not flags & os.O_CREAT:
            evidence.unlink()
            os.mkfifo(evidence)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

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

    def keep_old(path: str, *args: object, **kwargs: object) -> None:
        if path.endswith(".old"):
            raise OSError(errno.EIO, "Input/output error")
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ax.os, "unlink", keep_old)

    ax._write_evidence(Path("evidence.json"), NEW)

    assert json.loads(evidence.read_text(encoding="utf-8")) == NEW
    assert "could not remove" in capsys.readouterr().err
