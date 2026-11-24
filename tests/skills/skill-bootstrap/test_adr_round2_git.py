"""Review round 2 tests for the git environment and the commit reader: items 3 and 11."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import adr_scan
import pytest
from adr_helpers import commit, git, new_repo, run_cli, write
from draft_helpers import _cand, _scan_file

# ---------------------------------------------------------------------------
# Item 3: discovery limits in the parent environment do not reach git
# ---------------------------------------------------------------------------


def test_git_env_drops_the_discovery_limit_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/somewhere")
    monkeypatch.setenv("GIT_DISCOVERY_ACROSS_FILESYSTEM", "1")
    env = adr_scan.git_env()
    assert "GIT_CEILING_DIRECTORIES" not in env
    assert "GIT_DISCOVERY_ACROSS_FILESYSTEM" not in env


def test_a_ceiling_at_the_repository_does_not_turn_an_in_repo_folder_into_scratch(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    (repo / "docs" / "other").mkdir()
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _cand())
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(repo)}
    code, payload = run_cli(
        "draft",
        "--scan",
        scan,
        "--id",
        "c-1234567",
        "--out",
        str(repo / "docs" / "other"),
        env=env,
    )
    assert code == 2 and payload["error"] == "config"
    assert not list((repo / "docs" / "other").iterdir())


# ---------------------------------------------------------------------------
# Item 11: object sizes are checked before the batch read
# ---------------------------------------------------------------------------

BIG = "Adopt Redis instead of Memcached\n\n" + "Because the team already runs it. " * 40


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Record the ``cat-file`` calls, in order, and let them run."""
    real = adr_scan.git_bytes
    calls: list[tuple[str, ...]] = []

    def spy(
        repo: Path, *args: str, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        if args[0] == "cat-file":
            calls.append(args)
        result: subprocess.CompletedProcess[bytes] = real(repo, *args, stdin=stdin)
        return result

    monkeypatch.setattr(adr_scan, "git_bytes", spy)
    return calls


def test_a_commit_over_the_size_limit_is_skipped_and_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    big = commit(repo, BIG)
    head = commit(repo, "Use Postgres for the events store")
    monkeypatch.setattr(adr_scan, "MAX_COMMIT_BYTES", 600)
    dropped: dict[str, int] = {}
    records, truncated = adr_scan.read_commits(repo, head, 10, None, dropped)
    assert big not in [r.sha for r in records] and len(records) == 2 and truncated is False
    assert dropped == {"commit_too_large": 1}


def test_scan_reports_a_commit_too_large_under_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, BIG)
    monkeypatch.setattr(adr_scan, "MAX_COMMIT_BYTES", 600)
    payload = adr_scan.scan(repo, "HEAD", 10, None, None)
    assert payload["dropped"]["commit_too_large"] == 1
    assert payload["candidates"] == [] and payload["examined"]["commits"] == 0


def test_a_commit_at_the_size_limit_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    head = commit(repo, "Use Postgres for the events store")
    size = int(git(repo, "cat-file", "-s", head))
    monkeypatch.setattr(adr_scan, "MAX_COMMIT_BYTES", size)
    records, _ = adr_scan.read_commits(repo, head, 10, None, {})
    assert [r.sha for r in records] == [head]


def test_the_size_check_runs_before_the_batch_read_on_the_same_shas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    for n in range(3):
        commit(repo, f"Decision number {n}")
    head = git(repo, "rev-parse", "HEAD").strip()
    calls = _spy(monkeypatch)
    adr_scan.read_commits(repo, head, 10)
    assert [call[1] for call in calls] == ["--batch-check", "--batch"]


def test_a_batch_holds_at_most_the_byte_limit_of_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    for n in range(6):
        commit(repo, f"Decision number {n}")
    head = git(repo, "rev-parse", "HEAD").strip()
    sizes = [int(git(repo, "cat-file", "-s", sha)) for sha in git(repo, "rev-list", head).split()]
    monkeypatch.setattr(adr_scan, "MAX_BATCH_BYTES", max(sizes) * 2)
    calls = _spy(monkeypatch)
    records, _ = adr_scan.read_commits(repo, head, 10)
    reads = [call for call in calls if call[1] == "--batch"]
    assert len(records) == 6 and len(reads) == 3
    assert [r.subject for r in records] == [f"Decision number {n}" for n in range(5, -1, -1)]


def test_one_object_over_the_batch_byte_limit_still_forms_a_batch_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    for n in range(3):
        commit(repo, f"Decision number {n}")
    head = git(repo, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(adr_scan, "MAX_BATCH_BYTES", 10)
    calls = _spy(monkeypatch)
    records, _ = adr_scan.read_commits(repo, head, 10)
    assert len(records) == 3 and len([c for c in calls if c[1] == "--batch"]) == 3


def test_no_commits_run_no_size_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = new_repo(tmp_path / "r")
    head = commit(repo, "Initial work")
    calls = _spy(monkeypatch)
    assert adr_scan.read_commits(repo, head, 0) == ([], True)
    assert calls == []


def _fake_check(monkeypatch: pytest.MonkeyPatch, stdout: bytes, code: int = 0) -> None:
    real = adr_scan.git_bytes

    def fake(
        repo: Path, *args: str, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        if args[:2] == ("cat-file", "--batch-check"):
            return subprocess.CompletedProcess(args, code, stdout, b"boom")
        result: subprocess.CompletedProcess[bytes] = real(repo, *args, stdin=stdin)
        return result

    monkeypatch.setattr(adr_scan, "git_bytes", fake)


@pytest.mark.parametrize(
    "reply",
    [
        b"",
        b"{sha} missing\n",
        b"{sha} blob 3\n",
        b"{other} commit 3\n",
        b"{sha} commit 3",
        b"{sha} commit 3\n{sha} commit 3\n",
        b"{sha} commit x\n",
        b"{sha} commit 3\n\n",
    ],
)
def test_a_size_reply_that_does_not_match_the_request_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: bytes
) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, "Initial work")
    text = reply.replace(b"{sha}", sha.encode()).replace(b"{other}", b"c" * 40)
    _fake_check(monkeypatch, text)
    with pytest.raises(adr_scan.GitError, match="batch-check"):
        adr_scan.read_commits(repo, sha, 5)


def test_a_failing_size_check_is_a_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = new_repo(tmp_path / "r")
    sha = commit(repo, "Initial work")
    _fake_check(monkeypatch, b"", code=128)
    with pytest.raises(adr_scan.GitError, match="batch-check failed"):
        adr_scan.read_commits(repo, sha, 5)


def test_the_new_drop_keys_are_in_the_payload(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    commit(repo, "Initial work")
    payload: dict[str, Any] = adr_scan.scan(repo, "HEAD", 5, None, None)
    assert payload["dropped"]["commit_too_large"] == 0
