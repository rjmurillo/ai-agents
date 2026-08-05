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


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=10,
    )
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


def _commit(repo: Path, message: str) -> None:
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "--quiet", "-m", message)


@pytest.mark.parametrize(
    ("target", "left_append", "right_append"),
    (
        (
            ".agents/governance/GOTCHAS.md",
            "\n## Left Gotcha\n\nLeft branch detail.\n",
            "\n## Right Gotcha\n\nRight branch detail.\n",
        ),
        (
            ".serena/memories/memory-index.md",
            "|left keywords: [left-memory](left-memory.md) (1)\n",
            "|right keywords: [right-memory](right-memory.md) (1)\n",
        ),
    ),
)
def test_builtin_union_driver_preserves_independent_appends(
    target: str,
    left_append: str,
    right_append: str,
) -> None:
    with _scratch_repo("independent-appends") as repo:
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
