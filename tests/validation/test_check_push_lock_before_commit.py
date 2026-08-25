"""Issue #5123: refuse a commit while this branch's own push is in flight.

Reuses the canonical per-branch push-lock file (``.claude/rules/push-lock.md``)
rather than a second locking scheme, so these tests probe the same lock a real
push recipe would take.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path

from scripts.validation import check_push_lock_before_commit as checker


def _init_git_repo(repo: Path) -> None:
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=repo, check=True, timeout=10)
    subprocess.run(
        ["git", "-c", "user.name=pytest", "-c", "user.email=pytest@example.invalid", "commit",
         "--allow-empty", "--quiet", "-m", "initial"],
        cwd=repo,
        check=True,
        timeout=10,
    )


# ---------------------------------------------------------------------------
# _push_is_in_flight: exercises the real POSIX flock, not a mock, since a
# second open() of the same path contends with the first even in one process.
# ---------------------------------------------------------------------------


def test_push_is_in_flight_true_while_another_open_holds_the_lock(tmp_path):
    lock_path = tmp_path / "push-lock-held.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    try:
        assert checker._push_is_in_flight(lock_path) is True
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


def test_push_is_in_flight_false_when_lock_file_is_untouched(tmp_path):
    lock_path = tmp_path / "push-lock-free.lock"
    lock_path.touch()

    assert checker._push_is_in_flight(lock_path) is False


def test_push_is_in_flight_false_after_the_holder_releases(tmp_path):
    lock_path = tmp_path / "push-lock-released.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    fcntl.flock(holder_fd, fcntl.LOCK_UN)
    os.close(holder_fd)

    assert checker._push_is_in_flight(lock_path) is False


def test_push_is_in_flight_false_when_lock_file_cannot_be_opened(tmp_path):
    """A filesystem problem unrelated to a concurrent push must not block a
    commit; the push itself would hit the same problem and fail loudly there."""
    missing_parent = tmp_path / "does-not-exist" / "push-lock-x.lock"

    assert checker._push_is_in_flight(missing_parent) is False


# ---------------------------------------------------------------------------
# lock_path_for_branch: the canonical naming scheme
# ---------------------------------------------------------------------------


def test_lock_path_for_branch_matches_the_canonical_scheme(monkeypatch, tmp_path):
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", tmp_path)

    assert checker.lock_path_for_branch("fix/foo") == tmp_path / "push-lock-fix-foo.lock"


# ---------------------------------------------------------------------------
# check_push_not_in_flight: the full decision, against a real throwaway repo
# ---------------------------------------------------------------------------


def test_check_push_not_in_flight_allows_when_no_lock_file_exists_yet(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", tmp_path / "locks")

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "no lock file yet" in message


def test_check_push_not_in_flight_allows_when_lock_is_free(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "push-lock-main.lock").touch()
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", lock_dir)

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "lock is free" in message


def test_check_push_not_in_flight_blocks_when_push_holds_the_lock(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", lock_dir)

    try:
        allowed, message = checker.check_push_not_in_flight(repo)
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)

    assert allowed is False
    assert "#5123" in message
    assert "main" in message


def test_check_push_not_in_flight_allows_on_detached_head(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "--quiet", head], check=True, timeout=10)
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", tmp_path / "locks")

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "detached HEAD" in message


# ---------------------------------------------------------------------------
# main(): the process-exit contract (testing.md MUST 8)
# ---------------------------------------------------------------------------


def test_main_exits_zero_when_lock_is_free(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", tmp_path / "locks")

    assert checker.main(["--repo-root", str(repo)]) == 0


def test_main_exits_one_when_push_holds_the_lock(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", lock_dir)

    try:
        assert checker.main(["--repo-root", str(repo)]) == 1
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


def test_main_exits_two_when_repo_root_is_not_a_git_repository(tmp_path):
    not_a_repo = tmp_path / "plain-directory"
    not_a_repo.mkdir()

    assert checker.main(["--repo-root", str(not_a_repo)]) == 2


def test_main_prints_the_examined_branch_on_success(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(checker, "LOCK_DIRECTORY", tmp_path / "locks")

    checker.main(["--repo-root", str(repo)])

    assert "main" in capsys.readouterr().out
