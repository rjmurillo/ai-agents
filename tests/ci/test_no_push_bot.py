"""Regression guard for issue #4168: no workflow may push directly to main.

ADR-091 shipped a post-merge bot that committed parity manifest versions and
pushed directly to ``main``. Ruleset 11104075 rejects that push
unconditionally because ``github-actions[bot]`` is not a bypass actor. The
workflow was green exactly when idle (no-op early-exit 0) and red exactly when
it did its job (push rejected). That inversion hid the defect for multiple
merge cycles.

PR #4179 deleted the workflow and PR #4214 completed the remediation.
ADR-092 supersedes ADR-091 and removes the version field entirely so
freshness resolves from the git commit SHA.

This file guards against regression:

- ``post-merge-version-bump.yml`` must not exist. Recreating it with the
  same ``git push`` step recreates the GH013 failure.
- No push-triggered workflow may contain a bare ``git push`` targeting
  ``main`` from a ``github-actions[bot]`` context. The pattern
  ``git push`` in a ``run:`` block under ``permissions: contents: write``
  is the exact shape that failed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

_DELETED_WORKFLOW = WORKFLOW_DIR / "post-merge-version-bump.yml"

# Pattern that matches a bare "git push" in a run block (with or without
# flags that do not specify a different remote or branch).  The push that
# broke production was: ``git push`` with no arguments on a checkout of
# ``main``, so the refspec defaulted to ``main -> main``.
_BARE_GIT_PUSH = re.compile(
    r"^\s*git\s+push\s*(?:--follow-tags\s*|--tags\s*)?$",
    re.MULTILINE,
)


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def _load_workflow(path: Path) -> dict[Any, Any] | None:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _triggers_main_push(workflow: dict[Any, Any]) -> bool:
    on = workflow.get(True, workflow.get("on"))
    if isinstance(on, str):
        return on == "push"
    if isinstance(on, list):
        return "push" in on
    if not isinstance(on, dict) or "push" not in on:
        return False
    push = on["push"]
    if not isinstance(push, dict):
        return True
    branches = push.get("branches")
    if branches is None:
        return True
    return isinstance(branches, list) and "main" in branches


def _perms_write_contents(perms: Any) -> bool:
    if isinstance(perms, dict):
        return perms.get("contents") == "write"
    # "write-all" string grants contents:write
    return perms == "write-all"


def _has_write_contents(workflow: dict[Any, Any], job: dict[str, Any]) -> bool:
    """True when workflow- or job-level permissions include ``contents: write``."""
    return _perms_write_contents(workflow.get("permissions")) or _perms_write_contents(
        job.get("permissions")
    )


def _bare_push_violations_in_job(
    path_name: str, job_id: str, job: dict[str, Any]
) -> list[str]:
    violations = []
    for step in job.get("steps", []):
        if not isinstance(step, dict):
            continue
        run = step.get("run", "")
        if isinstance(run, str) and _BARE_GIT_PUSH.search(run):
            violations.append(
                f"{path_name}: job '{job_id}' bare-pushes to main. "
                "This will be rejected by ruleset 11104075 because "
                "github-actions[bot] is not a bypass actor. "
                "Open a PR instead of pushing directly."
            )
    return violations


def _bare_push_violations_in_workflow(path: Path, wf: dict[str, Any]) -> list[str]:
    violations = []
    jobs = wf.get("jobs", {})
    if not isinstance(jobs, dict):
        return violations
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if not _has_write_contents(wf, job):
            continue
        violations.extend(_bare_push_violations_in_job(path.name, job_id, job))
    return violations


class TestDeletedWorkflowAbsent:
    """post-merge-version-bump.yml must not be present."""

    def test_deleted_workflow_does_not_exist(self) -> None:
        """Recreating this file with a bare git push recreates GH013 failures."""
        assert not _DELETED_WORKFLOW.exists(), (
            f"{_DELETED_WORKFLOW.name} must not exist. "
            "ADR-092 (PR #4179) deleted it because github-actions[bot] cannot "
            "bypass ruleset 11104075. If you need a post-merge automation, "
            "open a PR instead of pushing directly to main."
        )


class TestNoBareGitPushOnMainPushTrigger:
    """No push-to-main workflow may bare-push back to main.

    The GH013 failure occurs when a workflow triggered by a push to main
    runs a bare ``git push``. Because ``github-actions[bot]`` is not a
    bypass actor on ruleset 11104075, the push is always rejected. The
    workflow is then red exactly when it has work to do and green when it
    is idle, which hides the breakage.
    """

    def test_no_push_bot_pattern(self) -> None:
        violations: list[str] = []
        for path in _workflow_files():
            wf = _load_workflow(path)
            if wf is None or not _triggers_main_push(wf):
                continue
            violations.extend(_bare_push_violations_in_workflow(path, wf))
        assert not violations, "\n".join(violations)
