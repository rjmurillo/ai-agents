"""Every seed failure falls back to the full run without raising (issue #6239)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation import testmon_seed as seed
from scripts.validation import testmon_seed_archive as archive
from scripts.validation import testmon_seed_gh as gh_module
from tests.validation.testmon_seed_helpers import (
    DATABASE,
    FakeGh,
    artifact_entry,
    make_routes,
    make_run,
    make_zip,
    write_inputs,
)


def _gh(root: Path, zip_bytes: bytes | None = None) -> FakeGh:
    payload = zip_bytes if zip_bytes is not None else make_zip({".testmondata": DATABASE})
    routes = make_routes([make_run(7)], {7: [artifact_entry(root)]})
    return FakeGh(routes, zip_bytes=payload)


def test_a_missing_gh_falls_back_without_a_call(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    gh = FakeGh({})
    result = seed.fetch_seed(tmp_path, runner=gh, gh_available=lambda: False)
    assert result == seed.SeedResult(False, "gh is not installed")
    assert gh.calls == []


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (subprocess.CompletedProcess([], 4, b"", b"gh: not logged in"), "gh api failed"),
        (subprocess.CompletedProcess([], 1, b"", b"dial tcp: no such host"), "no such host"),
        (subprocess.TimeoutExpired([], 1.0), "timed out"),
        (subprocess.CompletedProcess([], 0, b"<html>", b""), "JSON"),
    ],
    ids=["unauthenticated", "offline", "timeout", "garbled-json"],
)
def test_a_failing_gh_falls_back(tmp_path: Path, failure: object, expected: str) -> None:
    write_inputs(tmp_path)

    def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        if isinstance(failure, Exception):
            raise failure
        assert isinstance(failure, subprocess.CompletedProcess)
        return failure

    result = seed.fetch_seed(
        tmp_path, runner=runner, gh_available=lambda: True, has_origin_main=lambda _r, _t: True
    )
    assert not result.seeded
    assert expected.lower() in result.detail.lower()


def test_the_whole_fetch_shares_one_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_inputs(tmp_path)
    seen: list[float] = []
    clock = {"now": 100.0}
    monkeypatch.setattr(gh_module.time, "monotonic", lambda: clock["now"])

    def runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        seen.append(timeout)
        clock["now"] += 20.0
        body = json.dumps({"workflow_runs": [make_run(7), make_run(8)]}).encode()
        return subprocess.CompletedProcess(args, 0, body, b"")

    result = seed.fetch_seed(
        tmp_path,
        runner=runner,
        gh_available=lambda: True,
        has_origin_main=lambda _r, _t: True,
        ancestor=lambda _r, _s, _t: True,
        timeout_seconds=30.0,
    )
    assert not result.seeded
    assert seen == [pytest.approx(30.0), pytest.approx(10.0)]
    assert "deadline" in result.detail


@pytest.mark.parametrize(
    "payload",
    [
        b"not a zip",
        make_zip({"other": DATABASE}),
        make_zip({".testmondata": b"not sqlite"}),
        make_zip({"../.testmondata": DATABASE}),
    ],
    ids=["not-a-zip", "wrong-member", "not-sqlite", "path-traversal"],
)
def test_a_bad_download_falls_back_and_writes_nothing(tmp_path: Path, payload: bytes) -> None:
    write_inputs(tmp_path)
    assert not _gh(tmp_path, payload).fetch(tmp_path).seeded
    assert not (tmp_path / ".testmondata").exists()
    assert not (tmp_path.parent / ".testmondata").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_an_oversized_database_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_inputs(tmp_path)
    monkeypatch.setattr(archive, "MAX_DATABASE_BYTES", 4)
    result = _gh(tmp_path).fetch(tmp_path)
    assert not result.seeded
    assert "size cap" in result.detail


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("download larger than the size cap"),
        TimeoutError("timed out"),
        RuntimeError("exit 1"),
    ],
    ids=["too-large", "timeout", "nonzero-exit"],
)
def test_a_failed_download_falls_back_and_removes_its_staging_directory(
    tmp_path: Path, failure: Exception
) -> None:
    write_inputs(tmp_path)
    gh = _gh(tmp_path)
    staged: list[Path] = []

    def downloader(endpoint: str, destination: Path, timeout: float, max_bytes: int) -> None:
        staged.append(destination)
        destination.write_bytes(b"partial")
        raise failure

    result = seed.fetch_seed(
        tmp_path,
        runner=gh,
        downloader=downloader,
        gh_available=lambda: True,
        has_origin_main=lambda _r, _t: True,
        ancestor=lambda _r, _s, _t: True,
    )
    assert not result.seeded
    assert not (tmp_path / ".testmondata").exists()
    assert not staged[0].parent.exists()
