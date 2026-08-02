"""Regression guard for issue #4168: no workflow may bare-push.

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
- No workflow may contain a bare ``git push`` from a ``github-actions[bot]``
  context when it has write access to repository contents. The pattern
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

# Pattern that matches a bare "git push" command in a run block, including
# trailing comments and shell chains. The push that broke production was:
# ``git push`` with no arguments on a checkout of ``main``, so the refspec
# defaulted to ``main -> main``.
_BARE_GIT_PUSH = re.compile(
    r"^\s*git\s+push(?:\s+(?:--follow-tags|--tags))*\s*(?:(?:#.*)?|(?:&&|\|\||;).*)$",
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
    violations: list[str] = []
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
    violations: list[str] = []
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


class TestNoBareGitPushWithWriteContents:
    """No workflow with contents write may bare-push.

    The GH013 failure occurs when a workflow with ``contents: write`` runs a
    bare ``git push`` from a main checkout. Because ``github-actions[bot]`` is
    not a bypass actor on ruleset 11104075, the push is always rejected. The
    workflow is then red exactly when it has work to do and green when it is
    idle, which hides the breakage.
    """

    def test_no_push_bot_pattern(self) -> None:
        violations: list[str] = []
        for path in _workflow_files():
            wf = _load_workflow(path)
            if wf is None:
                continue
            violations.extend(_bare_push_violations_in_workflow(path, wf))
        assert not violations, "\n".join(violations)


def test_bare_push_guard_rejects_comment_and_shell_chain_forms() -> None:
    workflow = {
        "permissions": {"contents": "write"},
        "jobs": {
            "commented": {"steps": [{"run": "git push  # direct main push"}]},
            "chained": {"steps": [{"run": "git push || echo failed"}]},
        },
    }

    violations = _bare_push_violations_in_workflow(Path("bad.yml"), workflow)

    assert len(violations) == 2
    assert "commented" in violations[0]
    assert "chained" in violations[1]


def test_bare_push_guard_accepts_explicit_non_bare_push() -> None:
    workflow = {
        "permissions": {"contents": "write"},
        "jobs": {
            "safe": {"steps": [{"run": "git push origin HEAD:refs/heads/bot/update"}]}
        },
    }

    assert _bare_push_violations_in_workflow(Path("safe.yml"), workflow) == []


def test_no_push_bot_entrypoint_is_wired_to_reject_scheduled_bare_push(
    monkeypatch: Any, tmp_path: Path
) -> None:
    workflow = tmp_path / "scheduled.yml"
    workflow.write_text(
        """
on:
  schedule:
    - cron: "0 0 * * *"
permissions:
  contents: write
jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - run: git push || echo failed
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("tests.ci.test_no_push_bot.WORKFLOW_DIR", tmp_path)

    try:
        TestNoBareGitPushWithWriteContents().test_no_push_bot_pattern()
    except AssertionError as exc:
        assert "scheduled.yml" in str(exc)
        assert "bump" in str(exc)
    else:
        raise AssertionError("entrypoint accepted a scheduled bare git push")


def test_no_push_bot_entrypoint_accepts_safe_workflow(
    monkeypatch: Any, tmp_path: Path
) -> None:
    workflow = tmp_path / "safe.yml"
    workflow.write_text(
        """
on:
  schedule:
    - cron: "0 0 * * *"
permissions:
  contents: write
jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - run: git push origin HEAD:refs/heads/bot/update
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("tests.ci.test_no_push_bot.WORKFLOW_DIR", tmp_path)

    TestNoBareGitPushWithWriteContents().test_no_push_bot_pattern()
