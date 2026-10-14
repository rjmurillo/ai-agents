"""Behavior tests for bootstrap_boundary verify."""

from __future__ import annotations

from pathlib import Path

import pytest
from bootstrap_helpers import run_git, take_snapshot, verify, write

Capsys = pytest.CaptureFixture[str]
SKILL = ".claude/skills/proj-release/SKILL.md"
EXISTING = ".claude/skills/existing-skill/SKILL.md"


def test_verify_new_file_in_authorized_skill_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, SKILL)

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 0
    assert SKILL in payload["changed"]
    assert payload["violations"] == []


def test_verify_nested_file_in_authorized_skill_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, ".claude/skills/proj-release/references/a.md")

    code, _ = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 0


def test_verify_no_changes_exits_zero(repo: Path, capsys: Capsys, snap_path: Path) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 0
    assert payload["changed"] == []


def test_verify_examined_counts_paths_dirty_before_or_after(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "notes.txt", "user work\n")
    take_snapshot(capsys, repo, snap_path)
    write(repo, SKILL)

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 0
    assert payload["examined"] == 2
    assert payload["changed"] == [SKILL]


def test_verify_examined_is_zero_for_a_clean_repository(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)

    _, payload = verify(capsys, repo, snap_path)

    assert payload["examined"] == 0


def test_verify_new_file_outside_boundary_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "docs/x.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert {"kind": "outside-boundary", "path": "docs/x.md"} in payload["violations"]


def test_verify_file_directly_under_root_is_outside_boundary(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, ".claude/skills/stray.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "stray")

    assert code == 1
    assert payload["violations"] == [
        {"kind": "outside-boundary", "path": ".claude/skills/stray.md"}
    ]


def test_verify_sibling_skill_with_shared_prefix_is_outside_boundary(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, ".claude/skills/proj-release-extra/SKILL.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert payload["violations"][0]["kind"] == "outside-boundary"


def test_verify_skill_in_the_other_root_is_outside_boundary(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, ".github/skills/proj-release/SKILL.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert payload["violations"][0]["kind"] == "outside-boundary"


def test_verify_modified_preexisting_dirty_file_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "notes.txt", "before\n")
    take_snapshot(capsys, repo, snap_path)
    write(repo, "notes.txt", "after\n")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert {"kind": "outside-boundary", "path": "notes.txt"} in payload["violations"]


def test_verify_unchanged_preexisting_dirty_file_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "notes.txt", "user work\n")
    take_snapshot(capsys, repo, snap_path)
    write(repo, SKILL)

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 0
    assert "notes.txt" not in payload["changed"]


def test_verify_deleted_preexisting_dirty_file_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, "notes.txt", "user work\n")
    take_snapshot(capsys, repo, snap_path)
    (repo / "notes.txt").unlink()

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert "notes.txt" in payload["changed"]


# unauthorized-update and --update


def test_verify_write_to_existing_skill_without_update_is_unauthorized_update(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, EXISTING, "changed\n")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert payload["violations"] == [{"kind": "unauthorized-update", "path": EXISTING}]


def test_verify_existing_skill_passed_only_as_name_is_unauthorized_update(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, EXISTING, "changed\n")

    code, payload = verify(capsys, repo, snap_path, "--name", "existing-skill")

    assert code == 1
    assert payload["violations"][0]["kind"] == "unauthorized-update"


def test_verify_write_to_existing_skill_with_update_exits_zero(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, EXISTING, "changed\n")

    code, payload = verify(capsys, repo, snap_path, "--update", "existing-skill")

    assert code == 0
    assert payload["violations"] == []


def test_verify_update_of_one_skill_does_not_cover_another_existing_skill(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, ".claude/skills/second-skill/SKILL.md")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "feat: second skill")
    take_snapshot(capsys, repo, snap_path)
    write(repo, EXISTING, "changed\n")
    write(repo, ".claude/skills/second-skill/SKILL.md", "changed\n")

    code, payload = verify(capsys, repo, snap_path, "--update", "existing-skill")

    paths = [v["path"] for v in payload["violations"]]
    assert code == 1
    assert paths == [".claude/skills/second-skill/SKILL.md"]


def test_verify_skill_created_after_snapshot_is_not_an_unauthorized_update(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, SKILL)
    write(repo, ".claude/skills/proj-release/references/a.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 0
    assert payload["violations"] == []


@pytest.mark.parametrize("bad", [".", "", "Bad", "has_underscore", "a--b"])
@pytest.mark.parametrize("flag", ["--name", "--update"])
def test_verify_invalid_name_or_update_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, flag: str, bad: str
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, flag, bad)

    assert code == 2
    assert payload["error"] == "config"
    assert "invalid skill names" in payload["message"]


# --also-allow


def test_verify_also_allow_file_authorizes_that_path(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "templates/skills/x.tmpl")

    code, _ = verify(capsys, repo, snap_path, "--also-allow", "templates/skills/x.tmpl")

    assert code == 0


def test_verify_also_allow_directory_authorizes_paths_below_it(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "templates/skills/a/b.tmpl")

    code, _ = verify(capsys, repo, snap_path, "--also-allow", "templates/skills/")

    assert code == 0


def test_verify_also_allow_file_grant_does_not_cover_paths_below_it(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "templates/x.tmpl/nested.txt")

    code, payload = verify(capsys, repo, snap_path, "--also-allow", "templates/x.tmpl")

    assert code == 1
    assert payload["violations"] == [
        {"kind": "outside-boundary", "path": "templates/x.tmpl/nested.txt"}
    ]


def test_verify_also_allow_does_not_cover_a_sibling_path(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "templates/skills/x.tmpl")
    write(repo, "templates/skills-other/y.tmpl")

    code, payload = verify(capsys, repo, snap_path, "--also-allow", "templates/skills/")

    assert code == 1
    assert payload["violations"] == [
        {"kind": "outside-boundary", "path": "templates/skills-other/y.tmpl"}
    ]


def test_verify_also_allow_repeated_authorizes_each_path(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "a/one.txt")
    write(repo, "b/two.txt")

    code, _ = verify(capsys, repo, snap_path, "--also-allow", "a/", "--also-allow", "b/")

    assert code == 0


@pytest.mark.windows_path
def test_verify_also_allow_backslash_path_is_normalized(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, "templates/skills/x.tmpl")

    code, _ = verify(capsys, repo, snap_path, "--also-allow", "templates\\skills\\")

    assert code == 0


@pytest.mark.parametrize("bad", ["../outside.txt", "a/../../outside.txt", "..", ""])
def test_verify_also_allow_outside_repository_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, bad: str
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, f"--also-allow={bad}")

    assert code == 2
    assert "--also-allow" in payload["message"]


# HEAD and branch


def test_verify_new_commit_reports_head_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, SKILL)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "feat: add skill")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert "head-changed" in [v["kind"] for v in payload["violations"]]


def test_verify_branch_switch_reports_branch_changed(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    run_git(repo, "checkout", "-q", "-b", "other")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert [v["kind"] for v in payload["violations"]] == ["branch-changed"]


def test_verify_renamed_tracked_file_outside_boundary_exits_one(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    run_git(repo, "mv", "README.md", "README2.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 1
    assert "README.md" in payload["changed"]
    assert "README2.md" in payload["changed"]
