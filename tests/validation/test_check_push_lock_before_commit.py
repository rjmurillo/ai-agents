"""Issue #5123: refuse a commit that starts while this branch's own push is
in flight.

Reuses the canonical per-branch push-lock file (``.claude/rules/push-lock.md``)
rather than a second locking scheme, so these tests probe the same lock a real
push recipe would take.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import check_push_lock_before_commit as checker

# fcntl is POSIX-only; these tests hold the real lock via a second open() to
# exercise checker._push_is_in_flight's POSIX branch, which only runs on
# sys.platform != "win32". Importing fcntl unconditionally crashes collection
# of this whole file on Windows CI (ModuleNotFoundError), taking down every
# platform-agnostic test in it too, so the import itself is guarded here.
if sys.platform != "win32":
    import fcntl
else:
    import msvcrt

_posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="exercises the POSIX fcntl.flock branch of _push_is_in_flight",
)

# Copilot review, PR #5287: the Windows msvcrt.locking branch of
# _push_is_in_flight had zero test execution anywhere in CI. The main
# python-tests job never imports msvcrt (sys.platform != "win32" on that
# runner), and .github/workflows/pytest.yml:603-607 runs `pytest -m
# windows_path` on windows-latest, which this module never carried, so a
# regression in the Windows branch could make the guard silently allow every
# commit on that platform while CI stayed green. windows_path is additive,
# not exclusive (pyproject.toml markers, no `-m "not windows_path"`
# deselection on the main job), so marking these also keeps them collected
# and skipped (not hidden) on POSIX.
_windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="exercises the Windows msvcrt.locking branch of _push_is_in_flight",
)


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


@_posix_only
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


@_posix_only
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


@pytest.mark.windows_path
@_windows_only
def test_push_is_in_flight_true_while_another_open_holds_the_lock_windows(tmp_path):
    lock_path = tmp_path / "push-lock-held.lock"
    holder = lock_path.open("a+b")
    holder.seek(0)
    msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        assert checker._push_is_in_flight(lock_path) is True
    finally:
        holder.seek(0)
        msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
        holder.close()


@pytest.mark.windows_path
@_windows_only
def test_push_is_in_flight_false_after_the_holder_releases_windows(tmp_path):
    lock_path = tmp_path / "push-lock-released.lock"
    holder = lock_path.open("a+b")
    holder.seek(0)
    msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
    holder.seek(0)
    msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
    holder.close()

    assert checker._push_is_in_flight(lock_path) is False


@pytest.mark.windows_path
@_windows_only
def test_main_exits_one_when_push_holds_the_lock_windows(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder = lock_path.open("a+b")
    holder.seek(0)
    msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
    monkeypatch.setattr(checker, "_lock_directory", lambda: lock_dir)

    try:
        assert checker.main(["--repo-root", str(repo)]) == 1
    finally:
        holder.seek(0)
        msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
        holder.close()


# ---------------------------------------------------------------------------
# lock_path_for_branch: the canonical naming scheme
# ---------------------------------------------------------------------------


def test_lock_path_for_branch_matches_the_canonical_scheme(tmp_path):
    assert checker.lock_path_for_branch("fix/foo", tmp_path) == tmp_path / "push-lock-fix-foo.lock"


def test_lock_path_for_branch_falls_back_to_lock_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(checker, "_lock_directory", lambda: tmp_path)

    assert checker.lock_path_for_branch("main") == tmp_path / "push-lock-main.lock"


# ---------------------------------------------------------------------------
# check_push_not_in_flight: the full decision, against a real throwaway repo
# ---------------------------------------------------------------------------


def test_check_push_not_in_flight_allows_when_no_lock_file_exists_yet(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(checker, "_lock_directory", lambda: tmp_path / "locks")

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "no lock file yet" in message


def test_check_push_not_in_flight_allows_when_lock_is_free(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "push-lock-main.lock").touch()
    monkeypatch.setattr(checker, "_lock_directory", lambda: lock_dir)

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "lock is free" in message


@_posix_only
def test_check_push_not_in_flight_blocks_when_push_holds_the_lock(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    monkeypatch.setattr(checker, "_lock_directory", lambda: lock_dir)

    try:
        allowed, message = checker.check_push_not_in_flight(repo)
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)

    assert allowed is False
    assert "#5123" in message
    assert "main" in message
    assert "on this machine" in message
    assert checker.SKIP_ENV in message


def test_check_push_not_in_flight_allows_on_detached_head(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=10,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "--quiet", head], check=True, timeout=10)
    monkeypatch.setattr(checker, "_lock_directory", lambda: tmp_path / "locks")

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "detached HEAD" in message


def test_check_push_not_in_flight_fails_open_when_git_errors(tmp_path):
    """Issue #5123 review finding F3: a git failure (not a repo, no commits)
    must not block every commit; the guard fails open with the reason."""
    not_a_repo = tmp_path / "plain-directory"
    not_a_repo.mkdir()

    allowed, message = checker.check_push_not_in_flight(not_a_repo)

    assert allowed is True
    assert "could not determine the branch" in message
    assert "not a git repository" in message.lower()


def test_check_push_not_in_flight_fails_open_when_lock_directory_cannot_resolve(
    monkeypatch, tmp_path
):
    """F6: a RuntimeError from Path.home() (e.g. no resolvable home directory)
    must not crash the guard or block the commit."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)

    def _raise():
        raise RuntimeError("could not determine home directory")

    monkeypatch.setattr(checker, "_lock_directory", _raise)

    allowed, message = checker.check_push_not_in_flight(repo)

    assert allowed is True
    assert "could not resolve the lock directory" in message


# ---------------------------------------------------------------------------
# main(): the process-exit contract (testing.md MUST 8)
# ---------------------------------------------------------------------------


def test_main_exits_zero_when_lock_is_free(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(checker, "_lock_directory", lambda: tmp_path / "locks")

    assert checker.main(["--repo-root", str(repo)]) == 0


@_posix_only
def test_main_exits_one_when_push_holds_the_lock(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    monkeypatch.setattr(checker, "_lock_directory", lambda: lock_dir)

    try:
        assert checker.main(["--repo-root", str(repo)]) == 1
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


def test_main_exits_zero_when_repo_root_is_not_a_git_repository(tmp_path):
    """F3: fails open (exit 0) rather than exit 2, so a config problem here
    cannot block every commit in an unrelated directory."""
    not_a_repo = tmp_path / "plain-directory"
    not_a_repo.mkdir()

    assert checker.main(["--repo-root", str(not_a_repo)]) == 0


@_posix_only
def test_main_exits_zero_and_skips_the_lock_check_when_bypass_env_is_set(
    monkeypatch, tmp_path
):
    """F1: SKIP_PUSH_LOCK_COMMIT_GUARD=1 bypasses the guard even while the
    lock is genuinely held, for a stuck lock from a crashed holder."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    monkeypatch.setattr(checker, "_lock_directory", lambda: lock_dir)
    monkeypatch.setenv(checker.SKIP_ENV, "1")

    try:
        assert checker.main(["--repo-root", str(repo)]) == 0
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


@_posix_only
@pytest.mark.parametrize("bad_value", ["0", "true", "yes", ""])
def test_main_does_not_bypass_on_a_non_1_value(monkeypatch, tmp_path, bad_value):
    """Edge case for the SKIP_PUSH_LOCK_COMMIT_GUARD flag (config-catalog
    checklist): only the exact string "1" bypasses; every other value,
    including truthy-looking ones, leaves the guard enforced."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "push-lock-main.lock"
    holder_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    monkeypatch.setattr(checker, "_lock_directory", lambda: lock_dir)
    monkeypatch.setenv(checker.SKIP_ENV, bad_value)

    try:
        assert checker.main(["--repo-root", str(repo)]) == 1
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


def test_main_prints_the_examined_branch_on_success(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(checker, "_lock_directory", lambda: tmp_path / "locks")

    checker.main(["--repo-root", str(repo)])

    assert "main" in capsys.readouterr().out


def test_main_exits_two_on_unknown_arguments(capsys):
    """Copilot review, PR #5287: the module docstring's ADR-035 exit-code
    table did not name argparse's own usage-error exit. main() parses argv
    with argparse.ArgumentParser, which calls sys.exit(2) on an unknown or
    malformed flag before this module's own logic runs."""
    with pytest.raises(SystemExit) as excinfo:
        checker.main(["--not-a-real-flag"])

    assert excinfo.value.code == 2
