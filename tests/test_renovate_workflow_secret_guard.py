"""Regression test for #2551.

The "Renovate" job in `.github/workflows/dependabot-approve-and-auto-merge.yml`
silently fails when `secrets.GH_ACTIONS_PR_WRITE` resolves to an empty string
at run time (PAT expired, rotated, or renamed). The visible failure is
`gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN
environment variable.` which does not tell an operator that the actual root
cause is a missing repository secret.

Evidence:
https://github.com/rjmurillo/ai-agents/actions/runs/27254832120/job/79190113142

This test asserts every job that depends on `GH_ACTIONS_PR_WRITE` runs a
preflight guard that:

  1. Fails fast (exit 1) when the secret is empty.
  2. Emits a `::error::` annotation naming the secret and the admin remediation
     so the failure is self-diagnosing in the Actions UI.

Without this guard, an empty secret produces a cryptic `gh` error in a later
step and operators have to read raw logs to discover the root cause.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "dependabot-approve-and-auto-merge.yml"
)

PAT_SECRET = "GH_ACTIONS_PR_WRITE"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def _step_string(step: dict, key: str) -> str:
    value = step.get(key)
    return value if isinstance(value, str) else ""


def _step_mapping(step: dict, key: str) -> dict:
    value = step.get(key)
    return value if isinstance(value, dict) else {}


def _job_uses_pat(job: dict) -> bool:
    """Return True if any step in this job references the PAT secret in env."""
    for step in job.get("steps", []):
        env = _step_mapping(step, "env")
        for value in env.values():
            if isinstance(value, str) and PAT_SECRET in value:
                return True
    return False


def _jobs_requiring_pat(workflow: dict) -> dict[str, dict]:
    """Return jobs whose steps depend on the GH_ACTIONS_PR_WRITE PAT."""
    jobs = workflow.get("jobs", {})
    return {name: job for name, job in jobs.items() if _job_uses_pat(job)}


def _preflight_step(job: dict) -> dict | None:
    """Return the first step whose `run` block guards against an empty PAT.

    A guard step MUST:

      * reference `GH_ACTIONS_PR_WRITE` in `env`,
      * test the variable for emptiness in `run` (e.g. `[ -z "$..." ]`),
      * emit a `::error::` annotation so the failure surfaces in the UI,
      * exit non-zero.
    """
    for step in job.get("steps", []):
        run_block = _step_string(step, "run")
        env = _step_mapping(step, "env")
        pat_in_env = any(
            isinstance(value, str) and PAT_SECRET in value for value in env.values()
        )
        if not pat_in_env:
            continue
        if "-z" not in run_block:
            continue
        if "::error::" not in run_block:
            continue
        if "exit 1" not in run_block:
            continue
        return step
    return None


def test_renovate_job_uses_pat(workflow: dict) -> None:
    """Sanity: the Renovate job still depends on GH_ACTIONS_PR_WRITE.

    If this fails, the workflow no longer needs the PAT and the rest of the
    suite should be deleted or rewritten. Without this assertion the guard
    tests below would pass vacuously on an unrelated workflow refactor.
    """
    job = workflow["jobs"]["renovate"]
    assert _job_uses_pat(job), (
        "Renovate job no longer references GH_ACTIONS_PR_WRITE; either the "
        "PAT is no longer needed (delete this test) or the secret was renamed "
        "(update PAT_SECRET in this file). See #2551."
    )


def test_dependabot_job_uses_pat(workflow: dict) -> None:
    """Sanity: the Dependabot job still depends on GH_ACTIONS_PR_WRITE."""
    job = workflow["jobs"]["dependabot"]
    assert _job_uses_pat(job), (
        "Dependabot job no longer references GH_ACTIONS_PR_WRITE. Update "
        "PAT_SECRET or delete this test. See #2551."
    )


@pytest.mark.parametrize("job_name", ["renovate", "dependabot"])
def test_job_has_preflight_secret_guard(workflow: dict, job_name: str) -> None:
    """Positive: every PAT-using job runs a preflight guard.

    The guard checks that GH_ACTIONS_PR_WRITE is non-empty, emits a
    `::error::` annotation, and exits 1. This prevents the cryptic
    `gh: To use GitHub CLI ... set the GH_TOKEN environment variable.`
    failure mode documented in #2551.
    """
    job = workflow["jobs"][job_name]
    guard = _preflight_step(job)
    assert guard is not None, (
        f"Job {job_name!r} must declare a preflight step that fails fast "
        f"with `::error::` when secrets.{PAT_SECRET} is empty. See #2551 for "
        f"the failure mode this guards against."
    )


@pytest.mark.parametrize("job_name", ["renovate", "dependabot"])
def test_preflight_runs_before_any_gh_call(workflow: dict, job_name: str) -> None:
    """Negative: the guard must run BEFORE any gh CLI invocation.

    A guard that runs after `gh pr view` is useless; the cryptic failure
    happens first and the operator never sees the helpful error.
    """
    job = workflow["jobs"][job_name]
    steps = job.get("steps", [])
    guard_index = next(
        (i for i, step in enumerate(steps) if step is _preflight_step(job)),
        -1,
    )
    assert guard_index >= 0, (
        f"Job {job_name!r} missing preflight guard (see other test for "
        f"details)."
    )
    for i, step in enumerate(steps[:guard_index]):
        run_block = _step_string(step, "run")
        assert "gh " not in run_block, (
            f"Job {job_name!r} step {i} ({step.get('name')!r}) invokes `gh` "
            f"before the preflight secret guard at index {guard_index}. The "
            f"guard must run first or the cryptic GH_TOKEN error happens "
            f"before the helpful annotation. See #2551."
        )


@pytest.mark.parametrize("job_name", ["renovate", "dependabot"])
def test_preflight_annotation_names_the_secret_and_admin_action(
    workflow: dict, job_name: str
) -> None:
    """Edge: the `::error::` annotation must be self-diagnosing.

    An operator landing on a failed run needs to see, without reading raw
    logs, that the secret is missing and a repo admin must rotate the PAT.
    """
    job = workflow["jobs"][job_name]
    guard = _preflight_step(job)
    assert guard is not None
    run_block = _step_string(guard, "run")
    assert PAT_SECRET in run_block, (
        f"Preflight annotation must name {PAT_SECRET!r} so operators know "
        f"which secret to rotate. See #2551."
    )
    # Either 'admin' or 'rotate' is fine — both signal "this isn't a code fix".
    assert any(
        marker in run_block.lower() for marker in ("admin", "rotate", "settings")
    ), (
        "Preflight annotation must mention admin/rotate/settings so the "
        "operator knows this is a repo-settings fix, not a code fix. "
        "See #2551."
    )


def test_yaml_null_env_does_not_crash_guard_detection() -> None:
    """Edge: YAML `env:` blocks that are explicit null are handled safely."""
    workflow = {
        "jobs": {
            "renovate": {
                "steps": [
                    {"name": "noop", "uses": "actions/checkout@v5", "env": None},
                    {
                        "name": "guard",
                        "env": {"PAT": "${{ secrets.GH_ACTIONS_PR_WRITE }}"},
                        "run": (
                            'if [ -z "$PAT" ]; then\n'
                            '  echo "::error::secrets.GH_ACTIONS_PR_WRITE is '
                            'empty; admin must rotate the PAT"\n'
                            "  exit 1\n"
                            "fi\n"
                        ),
                    },
                ]
            }
        }
    }
    guard = _preflight_step(workflow["jobs"]["renovate"])
    assert guard is not None
    assert guard["name"] == "guard"
