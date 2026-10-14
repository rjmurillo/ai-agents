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


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_verify_write_to_a_file_flagged_before_the_snapshot_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path, flag: str
) -> None:
    run_git(repo, "update-index", flag, "README.md")
    take_snapshot(capsys, repo, snap_path)
    write(repo, "README.md", "hidden\n")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert {"kind": "outside-boundary", "path": "README.md"} in payload["violations"]


def test_verify_write_inside_a_submodule_set_to_ignore_dirty_exits_one(
    repo: Path, tmp_path: Path, capsys: Capsys, snap_path: Path
) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    run_git(upstream, "init", "-q")
    write(upstream, "lib.txt", "v1\n")
    run_git(upstream, "add", "lib.txt")
    run_git(upstream, "commit", "-q", "-m", "init")
    run_git(
        repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(upstream), "sub"
    )
    run_git(repo, "config", "-f", ".gitmodules", "submodule.sub.ignore", "dirty")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "chore: add submodule")
    take_snapshot(capsys, repo, snap_path)
    write(repo, "sub/lib.txt", "changed\n")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert {"kind": "outside-boundary", "path": "sub"} in payload["violations"]


def test_verify_staging_a_user_file_outside_the_boundary_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "draft.md", "user draft\n")
    take_snapshot(capsys, repo, snap_path)
    run_git(repo, "add", "draft.md")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert {"kind": "outside-boundary", "path": "draft.md"} in payload["violations"]


def test_verify_mode_change_on_a_dirty_user_file_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "README.md", "user edit\n")
    take_snapshot(capsys, repo, snap_path)
    (repo / "README.md").chmod(0o755)

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert {"kind": "outside-boundary", "path": "README.md"} in payload["violations"]


def test_verify_user_file_staged_before_the_snapshot_and_untouched_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "draft.md", "user draft\n")
    run_git(repo, "add", "draft.md")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path)

    assert code == 0
    assert payload["examined"] == 1


def test_verify_unstaging_a_user_file_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "draft.md", "user draft\n")
    run_git(repo, "add", "draft.md")
    take_snapshot(capsys, repo, snap_path)
    run_git(repo, "reset", "-q", "draft.md")

    code, payload = verify(capsys, repo, snap_path)

    assert code == 1
    assert {"kind": "outside-boundary", "path": "draft.md"} in payload["violations"]
