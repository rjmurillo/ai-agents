"""Behavior tests for bootstrap_boundary plan, snapshot, and verify."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import bootstrap_boundary
import pytest

ROOT = ".claude/skills"


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict]:
    code = bootstrap_boundary.main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


def _plan(
    capsys: pytest.CaptureFixture[str], repo: Path, *extra: str, root: str = ROOT
) -> tuple[int, dict]:
    return _run(capsys, "plan", "--repo", str(repo), "--output-root", root, *extra)


def _snapshot(capsys: pytest.CaptureFixture[str], repo: Path, out: Path) -> Path:
    code, _ = _run(capsys, "snapshot", "--repo", str(repo), "--out", str(out))
    assert code == 0
    return out


def _verify(
    capsys: pytest.CaptureFixture[str], repo: Path, snap: Path, *names: str
) -> tuple[int, dict]:
    argv = ["verify", "--repo", str(repo), "--snapshot", str(snap), "--output-root", ROOT]
    for name in names:
        argv += ["--name", name]
    return _run(capsys, *argv)


@pytest.fixture
def snap_path(tmp_path: Path) -> Path:
    return tmp_path / "snaps" / "snapshot.json"


def _write(repo: Path, rel: str, text: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# plan


def test_plan_new_name_is_new_and_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--name", "proj-release")

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


def test_plan_existing_name_without_update_is_conflict(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--name", "existing-skill")

    assert code == 1
    assert payload["proposed"][0]["status"] == "conflict"


def test_plan_existing_name_with_update_is_update(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--name", "existing-skill", "--update", "existing-skill")

    assert code == 0
    assert payload["proposed"][0]["status"] == "update"


@pytest.mark.parametrize(
    "name",
    [
        "Upper-case",
        "double--hyphen",
        "a" * 65,
        "-leading",
        "trailing-",
        "has_underscore",
    ],
)
def test_plan_invalid_name_is_invalid_and_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    code, payload = _plan(capsys, repo, f"--name={name}")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"
    assert payload["proposed"][0]["defects"]


def test_plan_name_of_64_characters_is_accepted(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--name", "a" * 64)

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


def test_plan_missing_project_prefix_is_invalid(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--project", "snafu", "--name", "release")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"
    assert "snafu" in payload["proposed"][0]["defects"][0]


def test_plan_matching_project_prefix_is_new(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--project", "snafu", "--name", "snafu-release")

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


def test_plan_update_without_matching_name_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _plan(capsys, repo, "--update", "existing-skill")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"
    assert payload["proposed"][0]["defects"] == ["--update without --name"]


@pytest.mark.parametrize("root", ["docs/skills", "../x/.claude/skills", "skills", ".claude"])
def test_plan_root_outside_allowed_set_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], root: str
) -> None:
    code, payload = _plan(capsys, repo, "--name", "proj-x", root=root)

    assert code == 2
    assert payload["error"] == "config"


def test_plan_backslash_root_is_accepted(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _plan(capsys, repo, "--name", "proj-x", root=".claude\\skills")

    assert code == 0
    assert payload["existing_skills"] == ["existing-skill"]


def test_plan_lists_existing_skills(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, payload = _plan(capsys, repo, "--name", "proj-x")

    assert payload["existing_skills"] == ["existing-skill"]


def test_plan_github_skills_root_is_accepted_when_directory_is_absent(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not (repo / ".github" / "skills").exists()

    code, payload = _plan(capsys, repo, "--name", "proj-x", root=".github/skills")

    assert code == 0
    assert payload["existing_skills"] == []
    assert payload["proposed"][0]["status"] == "new"


def test_plan_non_directory_repo_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")

    code, payload = _plan(capsys, not_a_dir, "--name", "proj-x")

    assert code == 2
    assert payload["error"] == "config"


def test_plan_outside_git_repository_exits_three(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    bare = tmp_path / "plain"
    bare.mkdir()

    code, payload = _plan(capsys, bare, "--name", "proj-x")

    assert code == 3
    assert payload["error"] == "git"


# git missing


def test_git_missing_exits_three(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(bootstrap_boundary.subprocess, "run", _no_git)

    code, payload = _plan(capsys, repo, "--name", "proj-x")

    assert code == 3
    assert payload["error"] == "git"
    assert "git" in payload["message"]


# snapshot


def test_snapshot_inside_repo_exits_two(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = _run(
        capsys, "snapshot", "--repo", str(repo), "--out", str(repo / "snapshot.json")
    )

    assert code == 2
    assert payload["error"] == "config"
    assert not (repo / "snapshot.json").exists()


def test_snapshot_outside_repo_writes_schema_and_head(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    code, payload = _run(capsys, "snapshot", "--repo", str(repo), "--out", str(snap_path))

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["schema"] == "skill-bootstrap-snapshot/1"
    assert record["head"] == run_git(repo, "rev-parse", "HEAD").strip()
    assert payload["head"] == record["head"]


def test_snapshot_records_dirty_untracked_path(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _write(repo, "notes.txt")

    _snapshot(capsys, repo, snap_path)

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert list(record["paths"]) == ["notes.txt"]


def test_snapshot_in_repository_without_commit_records_empty_head(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    run_git(empty, "init", "-q")

    code, _ = _run(capsys, "snapshot", "--repo", str(empty), "--out", str(snap_path))

    record = json.loads(snap_path.read_text(encoding="utf-8"))
    assert code == 0
    assert record["head"] == ""
    assert record["branch"] == ""


# verify


def test_verify_new_file_in_authorized_skill_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/proj-release/SKILL.md")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 0
    assert ".claude/skills/proj-release/SKILL.md" in payload["changed"]
    assert payload["violations"] == []


def test_verify_nested_file_in_authorized_skill_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/proj-release/references/a.md")

    code, _ = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 0


def test_verify_no_changes_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 0
    assert payload["changed"] == []


def test_verify_new_file_outside_boundary_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, "docs/x.md")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 1
    assert {"kind": "outside-boundary", "path": "docs/x.md"} in payload["violations"]


def test_verify_sibling_skill_with_shared_prefix_is_outside_boundary(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/proj-release-extra/SKILL.md")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 1
    assert payload["violations"][0]["kind"] == "outside-boundary"


def test_verify_modified_preexisting_dirty_file_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _write(repo, "notes.txt", "before\n")
    _snapshot(capsys, repo, snap_path)
    _write(repo, "notes.txt", "after\n")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 1
    assert {"kind": "outside-boundary", "path": "notes.txt"} in payload["violations"]


def test_verify_unchanged_preexisting_dirty_file_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _write(repo, "notes.txt", "user work\n")
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/proj-release/SKILL.md")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 0
    assert "notes.txt" not in payload["changed"]


def test_verify_deleted_preexisting_dirty_file_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _write(repo, "notes.txt", "user work\n")
    _snapshot(capsys, repo, snap_path)
    (repo / "notes.txt").unlink()

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 1
    assert "notes.txt" in payload["changed"]


def test_verify_write_to_existing_skill_without_naming_it_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/existing-skill/SKILL.md", "changed\n")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 1
    assert payload["violations"][0]["path"] == ".claude/skills/existing-skill/SKILL.md"


def test_verify_write_to_existing_skill_when_named_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/existing-skill/SKILL.md", "changed\n")

    code, _ = _verify(capsys, repo, snap_path, "existing-skill")

    assert code == 0


def test_verify_new_commit_reports_head_changed(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    _write(repo, ".claude/skills/proj-release/SKILL.md")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "feat: add skill")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    kinds = [v["kind"] for v in payload["violations"]]
    assert code == 1
    assert "head-changed" in kinds


def test_verify_branch_switch_reports_branch_changed(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    run_git(repo, "checkout", "-q", "-b", "other")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    kinds = [v["kind"] for v in payload["violations"]]
    assert code == 1
    assert kinds == ["branch-changed"]


def test_verify_snapshot_from_another_repo_exits_two(
    tmp_path: Path,
    repo: Path,
    make_repo: Callable[[Path], Path],
    capsys: pytest.CaptureFixture[str],
    snap_path: Path,
) -> None:
    other = make_repo(tmp_path / "other")
    _snapshot(capsys, other, snap_path)

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 2
    assert payload["error"] == "config"


def test_verify_corrupt_snapshot_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text("{not json", encoding="utf-8")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 2
    assert payload["error"] == "config"


def test_verify_snapshot_with_wrong_schema_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text(json.dumps({"schema": "other/1"}), encoding="utf-8")

    code, _ = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 2


def test_verify_missing_snapshot_file_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    code, _ = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 2


def test_verify_renamed_tracked_file_outside_boundary_exits_one(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)
    run_git(repo, "mv", "README.md", "README2.md")

    code, payload = _verify(capsys, repo, snap_path, "proj-release")

    assert code == 1
    assert "README.md" in payload["changed"]
    assert "README2.md" in payload["changed"]


def test_verify_output_root_outside_allowed_set_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], snap_path: Path
) -> None:
    _snapshot(capsys, repo, snap_path)

    code, _ = _run(
        capsys,
        "verify",
        "--repo",
        str(repo),
        "--snapshot",
        str(snap_path),
        "--output-root",
        "docs/skills",
    )

    assert code == 2


# CLI entry


def test_script_runs_as_a_process_and_reports_plan_help(tmp_path: Path) -> None:
    script = bootstrap_boundary.__file__
    assert script is not None

    proc = subprocess.run(
        ["python3", script, "plan", "--help"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 0
    assert "--output-root" in proc.stdout
