"""Behavior tests for bootstrap_boundary plan and the CLI entry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import bootstrap_boundary
import pytest
from bootstrap_helpers import ignore, plan, run_cli, write

Capsys = pytest.CaptureFixture[str]


def test_plan_new_name_is_new_and_exits_zero(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--name", "proj-release")

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


def test_plan_existing_name_without_update_is_conflict_with_defect(
    repo: Path, capsys: Capsys
) -> None:
    code, payload = plan(capsys, repo, "--name", "existing-skill")

    entry = payload["proposed"][0]
    assert code == 1
    assert entry["status"] == "conflict"
    assert entry["defects"] == ["skill exists; pass --name and --update to modify it"]


def test_plan_existing_name_with_update_is_update(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--name", "existing-skill", "--update", "existing-skill")

    assert code == 0
    assert payload["proposed"][0]["status"] == "update"


def test_plan_update_of_absent_skill_is_invalid(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--name", "proj-ghost", "--update", "proj-ghost")

    entry = payload["proposed"][0]
    assert code == 1
    assert entry["status"] == "invalid"
    assert entry["defects"] == ["--update names no existing skill in the output root"]


def test_plan_update_skips_the_project_prefix_check(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(
        capsys,
        repo,
        "--project",
        "snafu",
        "--name",
        "existing-skill",
        "--update",
        "existing-skill",
    )

    assert code == 0
    assert payload["proposed"][0]["status"] == "update"


def test_plan_existing_name_without_update_is_invalid_under_a_project_prefix(
    repo: Path, capsys: Capsys
) -> None:
    code, payload = plan(capsys, repo, "--project", "snafu", "--name", "existing-skill")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"


def test_plan_update_without_matching_name_is_invalid(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--update", "existing-skill")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"
    assert payload["proposed"][0]["defects"] == ["--update without a matching --name"]


@pytest.mark.parametrize(
    "name",
    ["Upper-case", "double--hyphen", "a" * 65, "-leading", "trailing-", "has_underscore", "1abc"],
)
def test_plan_invalid_name_is_invalid_and_exits_one(repo: Path, capsys: Capsys, name: str) -> None:
    code, payload = plan(capsys, repo, f"--name={name}")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"
    assert payload["proposed"][0]["defects"]


@pytest.mark.parametrize("name", ["a", "a" * 64])
def test_plan_boundary_length_names_are_accepted(repo: Path, capsys: Capsys, name: str) -> None:
    code, payload = plan(capsys, repo, "--name", name)

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


def test_plan_missing_project_prefix_is_invalid(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--project", "snafu", "--name", "release")

    assert code == 1
    assert payload["proposed"][0]["status"] == "invalid"
    assert "snafu" in payload["proposed"][0]["defects"][0]


def test_plan_matching_project_prefix_is_new(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--project", "snafu", "--name", "snafu-release")

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


def test_plan_single_letter_project_is_valid(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--project", "p", "--name", "p-release")

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


@pytest.mark.parametrize("project", ["Bad", "bad_name", "-bad", "bad-", "a--b"])
def test_plan_invalid_project_exits_two(repo: Path, capsys: Capsys, project: str) -> None:
    code, payload = plan(capsys, repo, f"--project={project}", "--name", "proj-x")

    assert code == 2
    assert payload["error"] == "config"
    assert "--project" in payload["message"]


def test_plan_name_under_the_other_allowed_root_is_conflict(repo: Path, capsys: Capsys) -> None:
    write(repo, ".github/skills/other-skill/SKILL.md")

    code, payload = plan(capsys, repo, "--name", "other-skill")

    entry = payload["proposed"][0]
    assert code == 1
    assert entry["status"] == "conflict"
    assert entry["defects"] == ["same name exists under .github/skills"]


def test_plan_name_under_the_other_root_is_new_when_that_root_is_empty(
    repo: Path, capsys: Capsys
) -> None:
    code, payload = plan(capsys, repo, "--name", "proj-x", root=".github/skills")

    assert code == 0
    assert payload["proposed"][0]["status"] == "new"


@pytest.mark.parametrize("root", ["docs/skills", "../x/.claude/skills", "skills", ".claude"])
def test_plan_root_outside_allowed_set_exits_two(repo: Path, capsys: Capsys, root: str) -> None:
    code, payload = plan(capsys, repo, "--name", "proj-x", root=root)

    assert code == 2
    assert payload["error"] == "config"


@pytest.mark.windows_path
def test_plan_backslash_root_is_accepted(repo: Path, capsys: Capsys) -> None:
    code, payload = plan(capsys, repo, "--name", "proj-x", root=".claude\\skills")

    assert code == 0
    assert payload["output_root"] == ".claude/skills"
    assert payload["existing_skills"] == ["existing-skill"]


def test_plan_requires_output_root(repo: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        bootstrap_boundary.main(["plan", "--repo", str(repo), "--name", "proj-x"])

    assert exc.value.code == 2


@pytest.mark.parametrize("pattern", [".claude/skills/", ".claude/"])
def test_plan_output_root_ignored_by_git_exits_two(
    repo: Path, capsys: Capsys, pattern: str
) -> None:
    ignore(repo, pattern)

    code, payload = plan(capsys, repo, "--name", "proj-x")

    assert code == 2
    assert payload["error"] == "config"
    assert "ignored by git" in payload["message"]


def test_plan_ignored_other_root_does_not_block_the_chosen_root(repo: Path, capsys: Capsys) -> None:
    ignore(repo, ".github/skills/")

    code, _ = plan(capsys, repo, "--name", "proj-x")

    assert code == 0


def test_plan_lists_existing_skills(repo: Path, capsys: Capsys) -> None:
    _, payload = plan(capsys, repo, "--name", "proj-x")

    assert payload["existing_skills"] == ["existing-skill"]


def test_plan_github_skills_root_is_accepted_when_directory_is_absent(
    repo: Path, capsys: Capsys
) -> None:
    assert not (repo / ".github" / "skills").exists()

    code, payload = plan(capsys, repo, "--name", "proj-x", root=".github/skills")

    assert code == 0
    assert payload["existing_skills"] == []
    assert payload["proposed"][0]["status"] == "new"


def test_plan_non_directory_repo_exits_two(tmp_path: Path, capsys: Capsys) -> None:
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")

    code, payload = plan(capsys, not_a_dir, "--name", "proj-x")

    assert code == 2
    assert payload["error"] == "config"


def test_plan_outside_git_repository_exits_three(
    tmp_path: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    bare = tmp_path / "plain"
    bare.mkdir()

    code, payload = plan(capsys, bare, "--name", "proj-x")

    assert code == 3
    assert payload["error"] == "git"


def test_git_missing_exits_three(
    repo: Path, capsys: Capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(bootstrap_boundary.subprocess, "run", _no_git)

    code, payload = plan(capsys, repo, "--name", "proj-x")

    assert code == 3
    assert payload["error"] == "git"
    assert "git" in payload["message"]


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


def test_run_cli_helper_round_trips_json(repo: Path, capsys: Capsys) -> None:
    code, payload = run_cli(capsys, "plan", "--repo", str(repo), "--output-root", ".claude/skills")

    assert code == 0
    assert payload["proposed"] == []
