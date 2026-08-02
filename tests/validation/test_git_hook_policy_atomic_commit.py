from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _commit_file(repo: Path, relative_path: str, content: str = "content\n") -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "--", relative_path)
    _git(repo, "commit", "-m", f"add {relative_path}")


def _commit_files(repo: Path, paths: list[str]) -> None:
    for relative_path in paths:
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative_path}\n", encoding="utf-8")
    _git(repo, "add", "--", *paths)
    _git(repo, "commit", "-m", "add files")


def _stage_files(repo: Path, paths: list[str]) -> None:
    for relative_path in paths:
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative_path}\n", encoding="utf-8")
    _git(repo, "add", "--", *paths)


def test_atomic_commit_counts_deleted_files_over_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    paths = [f"file_{index}.txt" for index in range(6)]
    _commit_files(repo, paths)

    _git(repo, "rm", "--quiet", "--", *paths)

    assert policy.check_atomic_commit(repo) == 1


def test_atomic_commit_counts_renamed_files_over_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    paths = [f"old_{index}.txt" for index in range(6)]
    _commit_files(repo, paths)

    for index, old_path in enumerate(paths):
        _git(repo, "mv", old_path, f"new_{index}.txt")

    assert policy.check_atomic_commit(repo) == 1


def test_atomic_commit_counts_each_rename_once(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    paths = [f"old_{index}.txt" for index in range(5)]
    _commit_files(repo, paths)

    for index, old_path in enumerate(paths):
        _git(repo, "mv", old_path, f"new_{index}.txt")

    assert policy.check_atomic_commit(repo) == 0


def test_atomic_commit_counts_deletion_inside_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "obsolete.txt")

    _stage_files(repo, [f"file_{index}.txt" for index in range(4)])
    _git(repo, "rm", "--quiet", "--", "obsolete.txt")

    assert policy.check_atomic_commit(repo) == 0


def test_atomic_commit_message_names_only_local_remedy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "README.md", "init\n")
    _stage_files(repo, [f"file_{index}.txt" for index in range(6)])

    assert policy.check_atomic_commit(repo) == 1

    captured = capsys.readouterr()
    assert "Split this commit." in captured.err
    assert "commit-limit-bypass" not in captured.err
