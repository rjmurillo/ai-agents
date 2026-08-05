"""Tests for append-target merge attributes."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH_ROOT = REPO_ROOT / ".pytest_tmp" / "append_merge_conflict_drivers"


@contextmanager
def _scratch_repo(test_name: str) -> Iterator[Path]:
    repo = SCRATCH_ROOT / f"{test_name}-{uuid.uuid4().hex}"
    repo.mkdir(parents=True)
    try:
        yield repo
    finally:
        if repo.exists():
            shutil.rmtree(repo)


def _run_git(
    repo: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=10,
    )
    if check:
        assert result.returncode == 0, (
            f"git {' '.join(args)} failed with {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _repo_attribute_line(target: str) -> str:
    for line in (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{target} "):
            return line
    pytest.fail(f"{target} has no .gitattributes entry")


def _repo_has_attribute_line(target: str) -> bool:
    return any(
        line.startswith(f"{target} ")
        for line in (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    )


def _commit(repo: Path, message: str) -> None:
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "--quiet", "-m", message)


def test_builtin_union_driver_preserves_independent_appends() -> None:
    with _scratch_repo("independent-appends") as repo:
        target = ".serena/memories/memory-index.md"
        left_append = "|left keywords: [left-memory](left-memory.md) (1)\n"
        right_append = "|right keywords: [right-memory](right-memory.md) (1)\n"
        _run_git(repo, "init", "--quiet")
        _run_git(repo, "config", "user.email", "test@example.com")
        _run_git(repo, "config", "user.name", "Append Merge Test")
        (repo / ".gitattributes").write_text(f"{_repo_attribute_line(target)}\n")
        target_path = repo / target
        target_path.parent.mkdir(parents=True)
        target_path.write_text("base\n", encoding="utf-8")
        _commit(repo, "base")

        _run_git(repo, "checkout", "--quiet", "-b", "left")
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + left_append,
            encoding="utf-8",
        )
        _commit(repo, "left append")

        _run_git(repo, "checkout", "--quiet", "-b", "right", "HEAD~1")
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + right_append,
            encoding="utf-8",
        )
        _commit(repo, "right append")

        _run_git(repo, "checkout", "--quiet", "left")
        _run_git(repo, "merge", "--no-edit", "right")

        merged = target_path.read_text(encoding="utf-8")
        assert left_append.strip() in merged
        assert right_append.strip() in merged
        assert "<<<<<<<" not in merged


def test_gotchas_keeps_loud_conflict_for_independent_appends() -> None:
    assert not _repo_has_attribute_line(".agents/governance/GOTCHAS.md")

    with _scratch_repo("gotchas-conflict") as repo:
        target = ".agents/governance/GOTCHAS.md"
        left_append = "\n## Left Gotcha\n\nLeft branch detail.\n"
        right_append = "\n## Right Gotcha\n\nRight branch detail.\n"
        _run_git(repo, "init", "--quiet")
        _run_git(repo, "config", "user.email", "test@example.com")
        _run_git(repo, "config", "user.name", "Append Merge Test")
        target_path = repo / target
        target_path.parent.mkdir(parents=True)
        target_path.write_text("base\n", encoding="utf-8")
        _commit(repo, "base")

        _run_git(repo, "checkout", "--quiet", "-b", "left")
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + left_append,
            encoding="utf-8",
        )
        _commit(repo, "left append")

        _run_git(repo, "checkout", "--quiet", "-b", "right", "HEAD~1")
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + right_append,
            encoding="utf-8",
        )
        _commit(repo, "right append")

        _run_git(repo, "checkout", "--quiet", "left")
        result = _run_git(repo, "merge", "--no-edit", "right", check=False)

        merged = target_path.read_text(encoding="utf-8")
        assert result.returncode == 1
        assert "<<<<<<<" in merged
        assert left_append.strip() in merged
        assert right_append.strip() in merged


def test_gotchas_union_would_hide_semantic_duplicates() -> None:
    with _scratch_repo("gotchas-semantic-duplicate") as repo:
        target = ".agents/governance/GOTCHAS.md"
        left_append = (
            "\n## Editing an always-on rule moves the doctrine figures\n\n"
            "Changing an always-on rule shifts the asserted rule count.\n"
        )
        right_append = (
            "\n## Editing any `.claude/rules/*.md` file changes a number the doctrine asserts\n\n"
            "The doctrine count changes whenever a rule file changes.\n"
        )
        _run_git(repo, "init", "--quiet")
        _run_git(repo, "config", "user.email", "test@example.com")
        _run_git(repo, "config", "user.name", "Append Merge Test")
        (repo / ".gitattributes").write_text(f"{target} merge=union\n", encoding="utf-8")
        target_path = repo / target
        target_path.parent.mkdir(parents=True)
        target_path.write_text("base\n", encoding="utf-8")
        _commit(repo, "base")

        _run_git(repo, "checkout", "--quiet", "-b", "left")
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + left_append,
            encoding="utf-8",
        )
        _commit(repo, "left duplicate")

        _run_git(repo, "checkout", "--quiet", "-b", "right", "HEAD~1")
        target_path.write_text(
            target_path.read_text(encoding="utf-8") + right_append,
            encoding="utf-8",
        )
        _commit(repo, "right duplicate")

        _run_git(repo, "checkout", "--quiet", "left")
        _run_git(repo, "merge", "--no-edit", "right")

        merged = target_path.read_text(encoding="utf-8")
        assert "## Editing an always-on rule moves the doctrine figures" in merged
        assert "## Editing any `.claude/rules/*.md` file changes a number" in merged
        assert "Changing an always-on rule shifts the asserted rule count." in merged
        assert "The doctrine count changes whenever a rule file changes." in merged
        assert "<<<<<<<" not in merged
