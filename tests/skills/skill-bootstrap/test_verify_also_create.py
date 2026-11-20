"""Behavior tests for the create-only `--also-create` grant of bootstrap_boundary verify."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from bootstrap_helpers import ignore, run_git, symlink_or_skip, take_snapshot, verify, write

Capsys = pytest.CaptureFixture[str]
ADR_DIR = "docs/adr/"
TRACKED_ADR = "docs/adr/0001-first.md"
NEW_ADR = "docs/adr/0002-second.md"


def commit_tracked_adr(repo: Path) -> None:
    """Commit one ADR so it is a tracked file when the snapshot is taken."""
    write(repo, TRACKED_ADR, "# first\n")
    run_git(repo, "add", TRACKED_ADR)
    run_git(repo, "commit", "-q", "-m", "docs: add first adr")


def kinds(payload: dict[str, Any]) -> list[tuple[str, str | None]]:
    return [(v["kind"], v.get("path")) for v in payload["violations"]]


def test_verify_new_file_under_directory_create_grant_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    write(repo, NEW_ADR)

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 0
    assert NEW_ADR in payload["changed"]
    assert payload["violations"] == []


def test_verify_new_file_matching_a_file_create_grant_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, NEW_ADR)

    code, payload = verify(capsys, repo, snap_path, "--also-create", NEW_ADR)

    assert code == 0
    assert payload["violations"] == []


def test_verify_modified_tracked_file_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    write(repo, TRACKED_ADR, "# rewritten\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", TRACKED_ADR)]


def test_verify_deleted_tracked_file_under_create_grant_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    (repo / TRACKED_ADR).unlink()

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", TRACKED_ADR)]


def test_verify_mode_change_of_tracked_file_under_create_grant_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    (repo / TRACKED_ADR).chmod(0o755)

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", TRACKED_ADR)]


def test_verify_untracked_file_at_snapshot_then_edited_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, NEW_ADR, "draft\n")
    take_snapshot(capsys, repo, snap_path)
    write(repo, NEW_ADR, "edited\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", NEW_ADR)]


def test_verify_untracked_file_at_snapshot_left_alone_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, NEW_ADR, "draft\n")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 0
    assert payload["violations"] == []


def test_verify_new_file_staged_under_create_grant_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, NEW_ADR)
    run_git(repo, "add", NEW_ADR)

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", NEW_ADR)]


def test_verify_ignored_new_file_under_create_grant_is_ignored_in_boundary(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    ignore(repo, "*.tmp")
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/draft.tmp")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("ignored-in-boundary", "docs/adr/draft.tmp")]


def test_verify_new_file_outside_create_grant_is_outside_boundary(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, NEW_ADR)
    write(repo, "docs/notes/n.md")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("outside-boundary", "docs/notes/n.md")]


def test_verify_create_grant_does_not_cover_a_sibling_with_the_same_prefix(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr-extra/x.md")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("outside-boundary", "docs/adr-extra/x.md")]


def test_verify_also_allow_wins_over_create_grant_for_the_same_path(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    write(repo, TRACKED_ADR, "# rewritten\n")

    code, payload = verify(
        capsys, repo, snap_path, "--also-allow", ADR_DIR, "--also-create", ADR_DIR
    )

    assert code == 0
    assert payload["violations"] == []


def test_verify_create_grant_stays_create_only_beside_an_unrelated_also_allow(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    write(repo, TRACKED_ADR, "# rewritten\n")

    code, payload = verify(
        capsys, repo, snap_path, "--also-allow", "templates/", "--also-create", ADR_DIR
    )

    assert code == 1
    assert kinds(payload) == [("create-only-changed", TRACKED_ADR)]


@pytest.mark.parametrize(
    "path",
    ["../elsewhere/", "docs/../../elsewhere", ".git/hooks", ".git/"],
)
def test_verify_also_create_outside_repo_or_under_git_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, path: str
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-create", path)

    assert code == 2
    assert payload["error"] == "config"
    assert "--also-create" in payload["message"]


@pytest.mark.parametrize(
    "path",
    [".claude/skills/existing-skill", ".claude/skills", ".claude", ".github/skills/other"],
)
def test_verify_also_create_overlapping_a_skills_root_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, path: str
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-create", path)

    assert code == 2
    assert "--also-create" in payload["message"]
    assert "overlaps" in payload["message"]


def test_verify_also_create_path_hidden_by_ignore_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    ignore(repo, "templates/")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-create", "templates/")

    assert code == 2
    assert "git ignores templates" in payload["message"]


def test_verify_also_create_through_a_symlink_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    (repo / "real").mkdir()
    symlink_or_skip(repo / "linked", repo / "real")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-create", "linked/")

    assert code == 2
    assert "symlink" in payload["message"]
