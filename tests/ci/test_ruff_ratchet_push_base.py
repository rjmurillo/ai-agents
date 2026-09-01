from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        check=False,
    )


def _check_git(repo: Path, *argv: str) -> str:
    result = _git(repo, *argv)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _check_git(repo, "add", "-A")
    _check_git(repo, "commit", "-qm", message)
    return _check_git(repo, "rev-parse", "HEAD")


def _write(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    _check_git(repo, "init", "-q", "-b", "main")
    _check_git(repo, "config", "user.email", "tests@example.com")
    _check_git(repo, "config", "user.name", "Tests")
    _write(repo, "shared.py", "value = 1\n")
    _commit(repo, "base")
    _check_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def _changed_python_files(repo: Path, base_ref: str = "origin/main") -> list[str]:
    status, files, _base = ruff_ratchet.changed_python_files(base_ref, repo)
    assert status == ruff_ratchet.EXIT_OK
    return files


def test_push_event_ignores_github_before_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("RUFF_RATCHET_BASE_REF", "a" * 40)

    assert ruff_ratchet.default_base_ref() == "origin/main"


def test_pull_request_event_keeps_pr_base_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    base_sha = "b" * 40
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("RUFF_RATCHET_BASE_REF", base_sha)

    assert ruff_ratchet.default_base_ref() == base_sha


def test_branch_ahead_counts_only_branch_python_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _check_git(repo, "checkout", "-qb", "feature")
    _write(repo, "feature.py", "value = 2\n")
    _commit(repo, "feature")

    assert _changed_python_files(repo) == ["feature.py"]


def test_branch_behind_origin_main_excludes_main_python_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _check_git(repo, "checkout", "-qb", "feature")
    _write(repo, "feature.py", "value = 2\n")
    _commit(repo, "feature")
    _check_git(repo, "checkout", "main")
    _write(repo, "main_only.py", "value = 3\n")
    _commit(repo, "advance main")
    _check_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _check_git(repo, "checkout", "feature")

    assert _changed_python_files(repo) == ["feature.py"]


def test_merge_commit_of_main_excludes_merge_brought_python_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _check_git(repo, "checkout", "-qb", "feature")
    _write(repo, "feature.py", "value = 2\n")
    _commit(repo, "feature")
    _check_git(repo, "checkout", "main")
    _write(repo, "main_only.py", "value = 3\n")
    _commit(repo, "advance main")
    _check_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _check_git(repo, "checkout", "feature")
    _check_git(repo, "merge", "--no-edit", "origin/main")

    assert _changed_python_files(repo) == ["feature.py"]


def test_linked_worktree_stale_local_main_uses_origin_main(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    linked = tmp_path / "linked"
    _init_repo(primary)
    base = _check_git(primary, "rev-parse", "HEAD")
    _check_git(primary, "worktree", "add", "-qb", "feature", str(linked), "HEAD")

    _write(linked, "feature.py", "value = 2\n")
    _commit(linked, "feature")

    _write(primary, "main_only.py", "value = 3\n")
    advanced = _commit(primary, "advance remote main")
    _check_git(primary, "update-ref", "refs/remotes/origin/main", advanced)
    _check_git(primary, "reset", "--hard", base)
    _check_git(linked, "merge", "--no-edit", "origin/main")

    assert _changed_python_files(linked) == ["feature.py"]
    assert sorted(_changed_python_files(linked, "main")) == ["feature.py", "main_only.py"]
