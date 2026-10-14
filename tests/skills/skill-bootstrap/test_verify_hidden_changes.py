"""verify must see writes that git status hides or folds together."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from bootstrap_helpers import ignore, run_git, take_snapshot, verify, write

Capsys = pytest.CaptureFixture[str]


def test_verify_worktree_rename_reports_the_deleted_source(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "abc", "a\n")
    run_git(repo, "add", "abc")
    run_git(repo, "commit", "-q", "-m", "chore: short name")
    take_snapshot(capsys, repo, snap_path)
    target = repo / ".claude/skills/proj-new/abc"
    target.parent.mkdir(parents=True)
    (repo / "abc").rename(target)
    run_git(repo, "add", "-N", ".claude/skills/proj-new/abc")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-new")

    assert code == 1
    assert {"kind": "outside-boundary", "path": "abc"} in payload["violations"]


def test_verify_write_inside_a_pre_existing_nested_repo_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    nested = repo / "vendor"
    nested.mkdir()
    subprocess.run(["git", "-C", str(nested), "init", "-q"], check=True)
    write(repo, "vendor/y.txt", "v\n")
    take_snapshot(capsys, repo, snap_path)
    write(repo, "vendor/y.txt", "changed\n")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert {"kind": "outside-boundary", "path": "vendor"} in payload["violations"]


def test_verify_skip_worktree_flag_set_during_the_run_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    run_git(repo, "update-index", "--skip-worktree", "README.md")
    write(repo, "README.md", "hidden\n")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert payload["violations"][0]["kind"] == "git_flags-changed"


def test_verify_info_exclude_edited_during_the_run_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    with (repo / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
        handle.write("docs/\n")
    write(repo, "docs/hidden.md")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert payload["violations"][0]["kind"] == "git_flags-changed"


def test_verify_update_skill_whose_directory_is_ignored_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, ".claude/skills/.gitignore", "existing-skill/\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "chore: ignore skill")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--update", "existing-skill")

    assert code == 2
    assert "git ignores" in payload["message"]


def test_verify_also_allow_directory_that_is_ignored_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    ignore(repo, "gen/")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-allow", "gen")

    assert code == 2
    assert "git ignores" in payload["message"]
