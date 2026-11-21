"""Blob pins and the directory skip for ADR-122 item 10 (issue #7493)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from .test_assess import _mod
from .test_change_admission import (
    _LIB_MIRROR,
    _REAL_BLOB_IDS,
    _RECORDS,
    _admit,
    _build_lib_mirror_repo,
    _comparison,
    _pinned_blobs,
    _record,
    _run,
)


@pytest.fixture
def blob_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return Path(_build_lib_mirror_repo(tmp_path, monkeypatch))


@pytest.fixture(autouse=True)
def _use_pinned_blobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_mod, "_blob_ids", _pinned_blobs)


# --- blob pins (ADR-122 item 10) ---------------------------------------------------


def test_every_record_pins_a_base_and_a_head_blob() -> None:
    for record in _RECORDS:
        for key in ("baseBlob", "headBlob"):
            assert isinstance(record[key], str)
            assert len(record[key]) == 40
            assert all(c in "0123456789abcdef" for c in record[key])


def test_a_head_blob_mismatch_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _record(_LIB_MIRROR, "coupling")
    monkeypatch.setattr(_mod, "_blob_ids", lambda path, base: (record["baseBlob"], "0" * 40))

    comparison = _admit(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}))

    assert comparison.change_admissions is None
    assert "differs from the pinned blobs" in capsys.readouterr().err


def test_a_base_blob_mismatch_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record(_LIB_MIRROR, "coupling")
    monkeypatch.setattr(_mod, "_blob_ids", lambda path, base: ("0" * 40, record["headBlob"]))

    comparison = _admit(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}))

    assert comparison.change_admissions is None


def test_an_admitted_comparison_carries_the_blob_ids() -> None:
    record = _record(_LIB_MIRROR, "coupling")

    comparison = _admit(_comparison(_LIB_MIRROR, {"coupling": (8.0, 7.0)}))

    assert (comparison.base_blob, comparison.head_blob) == (record["baseBlob"], record["headBlob"])


def test_blob_ids_reads_git_for_base_and_working_tree(
    blob_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=blob_repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.strip()

    assert _REAL_BLOB_IDS(_LIB_MIRROR, "main") == (
        git("rev-parse", f"main:{_LIB_MIRROR}"),
        git("hash-object", "--", _LIB_MIRROR),
    )


def test_a_same_score_edit_with_other_content_stays_blocking_end_to_end(
    blob_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The fixture reproduces the pinned scores, 8.0 to 7.0, with different
    # content. With the real blob lookup restored the record must not match.
    monkeypatch.setattr(_mod, "_blob_ids", _REAL_BLOB_IDS)

    rc = _run(blob_repo, {"thresholds": {}, "changeAdmissions": _RECORDS})
    err = capsys.readouterr().err

    assert rc == 10
    assert "NOT ADMITTED" in err
    assert "differs from the pinned blobs" in err


# --- directory skip ----------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need Developer Mode on Windows")
def test_an_added_directory_link_is_skipped_with_a_stderr_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real_pkg").mkdir()
    (tmp_path / "linked_pkg").symlink_to("real_pkg", target_is_directory=True)
    changes = [_mod.ChangedFile("A", None, Path("linked_pkg"))]

    files = _mod.get_files_to_assess(".", True, changed_files=changes)

    assert files == []
    assert "SKIPPED (directory): linked_pkg" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need Developer Mode on Windows")
def test_a_type_change_to_a_directory_link_still_reaches_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real_pkg").mkdir()
    (tmp_path / "was_a_file").symlink_to("real_pkg", target_is_directory=True)
    changes = [_mod.ChangedFile("T", Path("was_a_file"), Path("was_a_file"))]

    files = _mod.get_files_to_assess(".", True, changed_files=changes)

    assert files == [Path("was_a_file")]
    assert "SKIPPED" not in capsys.readouterr().err
