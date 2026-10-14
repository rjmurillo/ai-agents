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
