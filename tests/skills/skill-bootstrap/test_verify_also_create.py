"""Behavior tests for the create-only `--also-create` grant of bootstrap_boundary verify."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import boundary_grants
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


def test_verify_tracked_file_removed_from_index_then_edited_is_not_a_create(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    run_git(repo, "rm", "-q", "--cached", TRACKED_ADR)
    write(repo, TRACKED_ADR, "# rewritten\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert ("create-only-changed", TRACKED_ADR) in kinds(payload)


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


def test_verify_ignored_file_already_under_create_grant_does_not_fail(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    ignore(repo, ".DS_Store")
    write(repo, "docs/adr/.DS_Store")
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/.DS_Store", "changed by the desktop\n")
    write(repo, NEW_ADR)

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 0
    assert payload["violations"] == []


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


def test_verify_new_gitignore_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/.gitignore", "*.tmp\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", "docs/adr/.gitignore")]


def test_verify_new_gitattributes_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/.gitattributes", "*.md -diff\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", "docs/adr/.gitattributes")]


def test_verify_new_symlink_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path, tmp_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    symlink_or_skip(repo / "docs/adr/0002-link.md", tmp_path / "outside.md")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", "docs/adr/0002-link.md")]


def test_verify_new_nested_repository_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    commit_tracked_adr(repo)
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/nested/readme.md")
    run_git(repo / "docs/adr/nested", "init", "-q")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", "docs/adr/nested")]


def test_verify_create_grant_in_a_repository_with_no_commit_accepts_a_new_file(
    tmp_path: Path, capsys: Capsys, snap_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    run_git(empty, "init", "-q")
    (empty / ".claude" / "skills").mkdir(parents=True)
    take_snapshot(capsys, empty, snap_path)
    write(empty, NEW_ADR)

    code, payload = verify(capsys, empty, snap_path, "--also-create", ADR_DIR)

    assert code == 0
    assert payload["violations"] == []


def test_new_untracked_with_no_create_grant_never_calls_git() -> None:
    before = {"head": "a" * 40, "paths": {}}
    after = {"paths": {"docs/adr/0002-second.md": "??|" + "b" * 64 + ":644"}}

    def refuse(*_args: str) -> str:
        raise AssertionError("git must not run without a create grant")

    assert boundary_grants.new_untracked(before, after, [], refuse) == set()


def test_new_untracked_checks_head_in_batches() -> None:
    paths = {f"docs/adr/{n:04d}-x.md": "??|" + "c" * 64 + ":644" for n in range(250)}
    calls: list[int] = []

    def fake_git(*args: str) -> str:
        calls.append(len(args[args.index("--") + 1 :]))
        return ""

    created = boundary_grants.new_untracked(
        {"head": "a" * 40, "paths": {}},
        {"paths": paths},
        [(PurePosixPath("docs/adr"), True)],
        fake_git,
    )

    assert created == set(paths)
    assert calls == [100, 100, 50]


def test_verify_self_ignoring_gitignore_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/.gitignore", ".gitignore\n*.tmp\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", "docs/adr/.gitignore")]


def test_verify_upper_case_gitignore_under_create_grant_is_create_only_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/adr/.GITIGNORE", "*.tmp\n")

    code, payload = verify(capsys, repo, snap_path, "--also-create", ADR_DIR)

    assert code == 1
    assert kinds(payload) == [("create-only-changed", "docs/adr/.GITIGNORE")]
