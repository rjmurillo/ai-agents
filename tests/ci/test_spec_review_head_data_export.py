"""Run the ai-spec-review head-data export for real against a local fake origin.

Issue #6506 workflow-ci-04: the review job checks out the base commit and
receives the pull request head as data. The YAML-shape tests cannot tell
whether the export works, so this runs the step's script and then the spec
loader from the exported tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ai-spec-review.yml"
LOADER = REPO_ROOT / "scripts" / "ci" / "spec_load_content.py"
EXPORTER = REPO_ROOT / "scripts" / "ci" / "spec_review_export_head.py"
STEP_NAME = "Fetch pull request head as data"
PR_NUMBER = "7"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    )
    return result.stdout.strip()


def test_the_workflow_step_runs_the_exporter() -> None:
    data: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = {step.get("name"): step for step in data["jobs"]["review-spec"]["steps"]}

    assert steps[STEP_NAME]["run"].strip() == "python3 scripts/ci/spec_review_export_head.py"
    assert steps[STEP_NAME]["if"] == "github.event_name == 'pull_request'"


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, Path | str]:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "checkout", "-q", "-b", "main")
    (work / "README.md").write_text("base\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "push", "-q", "origin", "main")
    base_sha = _git(work, "rev-parse", "HEAD")

    _git(work, "checkout", "-q", "-b", "pr")
    specs = work / ".project-toolkit" / "specs"
    specs.mkdir(parents=True)
    (specs / "SPEC-new.md").write_text("# New spec from the PR head\n", encoding="utf-8")
    secret = tmp_path / "runner-secret.md"
    secret.write_text("TOKEN-IN-RUNNER-FILE\n", encoding="utf-8")
    (specs / "evil.md").symlink_to(secret)
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "head")
    head_sha = _git(work, "rev-parse", "HEAD")
    _git(work, "push", "-q", "origin", f"HEAD:refs/pull/{PR_NUMBER}/head")

    # The workspace is the base checkout: base commit only, head not present.
    workspace = tmp_path / "workspace"
    _git(tmp_path, "clone", "-q", str(origin), str(workspace))
    _git(workspace, "checkout", "-q", "--detach", base_sha)
    return {"workspace": workspace, "head": head_sha, "tmp": tmp_path}


def _run_step(
    repos: dict[str, Path | str], head_sha: str, **overrides: str
) -> subprocess.CompletedProcess[str]:
    tmp = Path(str(repos["tmp"]))
    runner_temp = tmp / "runner"
    runner_temp.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "GH_TOKEN": "not-a-real-token",
        "PR_NUMBER": PR_NUMBER,
        "HEAD_SHA": head_sha,
        "RUNNER_TEMP": str(runner_temp),
        **overrides,
    }
    return subprocess.run(
        [sys.executable, str(EXPORTER)],
        cwd=Path(str(repos["workspace"])),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _export(repos: dict[str, Path | str], head_sha: str) -> Path:
    result = _run_step(repos, head_sha)
    assert result.returncode == 0, result.stderr
    return Path(str(repos["tmp"])) / "runner" / "pr-head-data"


def test_head_specs_export_and_the_base_workspace_stays_on_base(
    repos: dict[str, Path | str],
) -> None:
    data = _export(repos, str(repos["head"]))
    workspace = Path(str(repos["workspace"]))

    assert (data / ".project-toolkit" / "specs" / "SPEC-new.md").is_file()
    # Head content is data under the temp dir, never the executing workspace.
    assert not (workspace / ".project-toolkit").exists()
    assert _git(workspace, "rev-parse", "HEAD") != str(repos["head"])


def test_symlinks_in_the_head_are_not_exported(repos: dict[str, Path | str]) -> None:
    data = _export(repos, str(repos["head"]))

    assert not (data / ".project-toolkit" / "specs" / "evil.md").exists()
    assert not (data / ".project-toolkit" / "specs" / "evil.md").is_symlink()


def test_loader_reads_a_new_head_spec_from_the_exported_tree(
    repos: dict[str, Path | str],
) -> None:
    data = _export(repos, str(repos["head"]))
    runner_temp = data.parent
    output = runner_temp / "out.txt"
    env = {
        **os.environ,
        "SPEC_REFS": ".project-toolkit/specs/SPEC-new.md",
        "ISSUE_REFS": "",
        "AZURE_REFS": "",
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_OUTPUT": str(output),
        "GITHUB_RUN_ID": "1",
    }
    result = subprocess.run(
        [sys.executable, str(LOADER)],
        cwd=data,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    spec_file = Path(output.read_text(encoding="utf-8").split("spec_file=")[1].strip())
    assert "New spec from the PR head" in spec_file.read_text(encoding="utf-8")


def test_a_head_without_spec_trees_exports_nothing_and_does_not_fail(
    repos: dict[str, Path | str],
) -> None:
    tmp = Path(str(repos["tmp"]))
    work = tmp / "work"
    _git(work, "checkout", "-q", "main")
    (work / "other.txt").write_text("x\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "no specs")
    bare_head = _git(work, "rev-parse", "HEAD")
    _git(work, "push", "-q", "-f", "origin", f"HEAD:refs/pull/{PR_NUMBER}/head")

    data = _export(repos, bare_head)

    assert data.is_dir()
    assert not any(data.rglob("*.md"))


def test_a_moved_head_is_fetched_by_sha(repos: dict[str, Path | str]) -> None:
    """The ref moved on after the event fired; the event SHA is still exported."""
    tmp = Path(str(repos["tmp"]))
    work = tmp / "work"
    _git(work, "checkout", "-q", "pr")
    (work / "later.txt").write_text("later\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "later")
    _git(work, "push", "-q", "-f", "origin", f"HEAD:refs/pull/{PR_NUMBER}/head")
    # Keep the older commit reachable from a ref, as GitHub does for pull refs.
    _git(work, "push", "-q", "origin", f"{repos['head']}:refs/heads/older")

    data = _export(repos, str(repos["head"]))

    assert (data / ".project-toolkit" / "specs" / "SPEC-new.md").is_file()


def test_missing_environment_is_a_config_error(repos: dict[str, Path | str]) -> None:
    result = _run_step(repos, str(repos["head"]), GH_TOKEN="")

    assert result.returncode == 2
    assert "required" in result.stderr


def test_a_non_numeric_pr_number_is_refused(repos: dict[str, Path | str]) -> None:
    result = _run_step(repos, str(repos["head"]), PR_NUMBER="7; rm -rf /")

    assert result.returncode == 2


def test_an_unfetchable_head_is_an_external_failure(repos: dict[str, Path | str]) -> None:
    result = _run_step(repos, str(repos["head"]), PR_NUMBER="999")

    assert result.returncode == 3
    assert "could not fetch" in result.stderr


@pytest.mark.parametrize("bad_sha", ["--upload-pack=evil", "abc123", "", "g" * 40, "-" + "a" * 39])
def test_a_head_sha_that_is_not_a_full_object_name_is_refused(
    repos: dict[str, Path | str], bad_sha: str
) -> None:
    result = _run_step(repos, bad_sha)

    assert result.returncode == 2


def test_non_ascii_digits_in_the_pr_number_are_refused(repos: dict[str, Path | str]) -> None:
    result = _run_step(repos, str(repos["head"]), PR_NUMBER="\u00b2")

    assert result.returncode == 2
