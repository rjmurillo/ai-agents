"""Behavior tests for the Dependabot auto-merge workflow-file guard (#6506 review-gates-15).

The "Enable auto-merge" step body runs under ``bash -e`` with a stub ``gh`` that logs
its calls, so the tests execute the real step instead of matching its source text.
The token and trigger regression tests live in ``tests/test_dependabot_workflow_token.py``.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.test_dependabot_workflow_token import WORKFLOW
from tests.test_renovate_config import _EXEMPT_FILE_GLOBS


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _merge_step_run(workflow: dict) -> str:
    steps = {s.get("name"): s for s in workflow["jobs"]["dependabot"]["steps"]}
    return steps["Enable auto-merge"]["run"]


def _run_merge_step(
    workflow: dict, tmp_path: Path, changed_files: str, gh_exit: int = 0
) -> tuple[int, str]:
    """Run the real step body under `bash -e` with a stub `gh` that logs its calls."""
    log = tmp_path / "gh.log"
    stub = tmp_path / "gh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{log}"\n'
        'if [ "$1 $2" = "pr diff" ]; then\n'
        f"  printf '%s' {shlex.quote(changed_files)}\n"
        f"  exit {gh_exit}\n"
        "fi\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "PR_URL": "https://example.test/pull/1",
    }
    result = subprocess.run(
        ["bash", "-e", "-c", _merge_step_run(workflow)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
@pytest.mark.parametrize(
    "changed",
    [
        ".github/workflows/ci.yml\n",
        "src/a.py\n.github/workflows/ci.yml\n",
        ".github/cli-smoke/pi/package-lock.json\n",
    ],
)
def test_workflow_file_prs_are_left_for_manual_merge(
    workflow: dict, tmp_path: Path, changed: str
) -> None:
    """Positive: a PR touching .github/workflows/ never reaches gh pr merge (review-gates-15)."""
    code, calls = _run_merge_step(workflow, tmp_path, changed)
    assert code == 0
    assert "pr merge" not in calls


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
@pytest.mark.parametrize(
    "changed",
    ["src/a.py\n", "uv.lock\n", "a/.github/workflows/x.yml\n", ".github/workflows-notes.md\n"],
)
def test_other_prs_still_get_auto_merge(workflow: dict, tmp_path: Path, changed: str) -> None:
    """Edge: only the workflow directory is excluded, not look-alike paths."""
    code, calls = _run_merge_step(workflow, tmp_path, changed)
    assert code == 0
    assert "pr merge --auto --squash https://example.test/pull/1" in calls


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_failed_file_list_read_fails_closed(workflow: dict, tmp_path: Path) -> None:
    """Error path: when gh pr diff fails, the step fails and no merge is enabled."""
    code, calls = _run_merge_step(workflow, tmp_path, "", gh_exit=1)
    assert code != 0
    assert "pr merge" not in calls


def test_job_has_a_timeout(workflow: dict) -> None:
    """Edge: a hung gh call must not hold the write token for the 360 minute default."""
    assert workflow["jobs"]["dependabot"]["timeout-minutes"] == 5


def test_dependabot_regex_covers_the_same_directories_as_the_renovate_globs(
    workflow: dict,
) -> None:
    """Drift guard: the step's directory list equals the directories in the Renovate globs."""
    run = _merge_step_run(workflow)
    match = re.search(r"grep -qE '\^\\\.github/\(([^)]*)\)/'", run)
    assert match, "the step no longer greps for the exempt directories"
    in_step = set(match.group(1).split("|"))
    in_renovate = {glob.split("/")[1] for glob in _EXEMPT_FILE_GLOBS}
    assert in_step == in_renovate
