"""Input validation tests for bootstrap_boundary verify: snapshot and output root."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from bootstrap_helpers import ignore, snapshot_result, take_snapshot, verify, write

Capsys = pytest.CaptureFixture[str]


def test_verify_snapshot_from_another_repo_exits_two(
    tmp_path: Path,
    repo: Path,
    make_repo: Callable[[Path], Path],
    capsys: Capsys,
    snap_path: Path,
) -> None:
    take_snapshot(capsys, make_repo(tmp_path / "other"), snap_path)

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 2
    assert payload["error"] == "config"


def test_verify_corrupt_snapshot_exits_two(repo: Path, capsys: Capsys, snap_path: Path) -> None:
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text("{not json", encoding="utf-8")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 2
    assert payload["error"] == "config"


@pytest.mark.parametrize("schema", ["other/1", "skill-bootstrap-snapshot/1"])
def test_verify_snapshot_with_wrong_schema_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, schema: str
) -> None:
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text(json.dumps({"schema": schema}), encoding="utf-8")

    code, _ = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 2


def test_verify_missing_snapshot_file_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    code, _ = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 2


def test_verify_output_root_differs_from_snapshot_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, root=".github/skills")

    assert code == 2
    assert "output root" in payload["message"]


@pytest.mark.windows_path
def test_verify_backslash_output_root_matches_a_posix_snapshot(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, _ = verify(capsys, repo, snap_path, root=".claude\\skills")

    assert code == 0


def test_verify_output_root_outside_allowed_set_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)

    code, _ = verify(capsys, repo, snap_path, root="docs/skills")

    assert code == 2


def test_verify_output_root_ignored_by_git_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    ignore(repo, ".claude/skills/")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 2
    assert "ignored by git" in payload["message"]


def test_verify_snapshot_for_github_root_checks_that_root(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    snapshot_result(capsys, repo, snap_path, root=".github/skills")
    write(repo, ".github/skills/proj-release/SKILL.md")

    code, _ = verify(capsys, repo, snap_path, "--name", "proj-release", root=".github/skills")

    assert code == 0


@pytest.mark.parametrize(
    "path",
    [
        ".claude/skills/existing-skill",
        ".claude/skills",
        ".claude",
        "./.claude/skills",
        ".github/skills/other",
        ".git/hooks",
    ],
)
def test_verify_also_allow_overlapping_a_skills_root_or_git_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, path: str
) -> None:
    take_snapshot(capsys, repo, snap_path)
    write(repo, ".claude/skills/existing-skill/SKILL.md", "changed\n")

    code, payload = verify(capsys, repo, snap_path, "--also-allow", path)

    assert code == 2
    assert payload["error"] == "config"


def test_verify_named_skill_hidden_by_a_nested_ignore_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, ".claude/skills/.gitignore", "proj-*/\n")
    take_snapshot(capsys, repo, snap_path)
    write(repo, ".claude/skills/proj-release/SKILL.md")

    code, payload = verify(capsys, repo, snap_path, "--name", "proj-release")

    assert code == 2
    assert "git ignores .claude/skills/proj-release/SKILL.md" in payload["message"]


def test_verify_also_allow_path_hidden_by_ignore_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    ignore(repo, "templates/")
    take_snapshot(capsys, repo, snap_path)

    code, payload = verify(capsys, repo, snap_path, "--also-allow", "templates/x.tmpl")

    assert code == 2
    assert "git ignores templates/x.tmpl" in payload["message"]
