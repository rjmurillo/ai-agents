"""Behavior tests for bootstrap_boundary snapshot."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import bootstrap_boundary
import pytest
from bootstrap_helpers import ignore, run_git, snapshot_result, take_snapshot, write

Capsys = pytest.CaptureFixture[str]


def test_snapshot_requires_output_root(repo: Path, snap_path: Path) -> None:
    argv = ["snapshot", "--repo", str(repo), "--out", str(snap_path)]

    with pytest.raises(SystemExit) as exc:
        bootstrap_boundary.main(argv)

    assert exc.value.code == 2
    assert not snap_path.exists()


def test_snapshot_inside_repo_exits_two(repo: Path, capsys: Capsys) -> None:
    code, payload = snapshot_result(capsys, repo, repo / "snapshot.json")

    assert code == 2
    assert payload["error"] == "config"
    assert not (repo / "snapshot.json").exists()


@pytest.mark.windows_path
def test_snapshot_outside_repo_writes_schema_root_and_head(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    code, payload = snapshot_result(capsys, repo, snap_path)

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["schema"] == "skill-bootstrap-snapshot/4"
    assert record["output_root"] == ".claude/skills"
    assert record["head"] == run_git(repo, "rev-parse", "HEAD").strip()
    assert payload["head"] == record["head"]


def test_snapshot_records_existing_skills_and_reports_their_count(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    write(repo, ".claude/skills/second-skill/SKILL.md")

    code, payload = snapshot_result(capsys, repo, snap_path)

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["existing_skills"] == ["existing-skill", "second-skill"]
    assert payload["existing_skills"] == 2


@pytest.mark.windows_path
def test_snapshot_backslash_output_root_is_normalized(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    code, _ = snapshot_result(capsys, repo, snap_path, root=".claude\\skills")

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["output_root"] == ".claude/skills"


def test_snapshot_absent_github_root_records_no_skills(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    code, _ = snapshot_result(capsys, repo, snap_path, root=".github/skills")

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["output_root"] == ".github/skills"
    assert record["existing_skills"] == []


@pytest.mark.parametrize("root", ["docs/skills", "skills", "../x/.claude/skills"])
def test_snapshot_output_root_outside_allowed_set_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path, root: str
) -> None:
    code, payload = snapshot_result(capsys, repo, snap_path, root=root)

    assert code == 2
    assert payload["error"] == "config"
    assert not snap_path.exists()


def test_snapshot_output_root_ignored_by_git_exits_two(
    repo: Path, capsys: Capsys, snap_path: Path
) -> None:
    ignore(repo, ".claude/skills/")

    code, payload = snapshot_result(capsys, repo, snap_path)

    assert code == 2
    assert "ignored by git" in payload["message"]
    assert not snap_path.exists()


def test_snapshot_records_dirty_untracked_path(repo: Path, capsys: Capsys, snap_path: Path) -> None:
    write(repo, "notes.txt")

    take_snapshot(capsys, repo, snap_path)

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert list(record["paths"]) == ["notes.txt"]


def test_snapshot_in_repository_without_commit_records_empty_head(
    tmp_path: Path, capsys: Capsys, snap_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    run_git(empty, "init", "-q")

    code, _ = snapshot_result(capsys, empty, snap_path)

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["head"] == ""
    assert record["branch"] == ""


def test_snapshot_refuses_to_overwrite_an_existing_snapshot(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    take_snapshot(capsys, repo, snap_path)
    first = snap_path.read_bytes()
    write(repo, "docs/stray.md")

    code, payload = snapshot_result(capsys, repo, snap_path)

    assert code == 2
    assert "already exists" in payload["message"]
    assert snap_path.read_bytes() == first


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="file mode 000 does not block reads on Windows or for root",
)
def test_snapshot_unreadable_user_file_exits_three_with_io_error(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    locked = repo / "locked.txt"
    locked.write_text("secret\n", encoding="utf-8")
    locked.chmod(0o000)
    try:
        code, payload = snapshot_result(capsys, repo, snap_path)
    finally:
        locked.chmod(0o600)

    assert code == 3
    assert payload["error"] == "io"
    assert not snap_path.exists()
