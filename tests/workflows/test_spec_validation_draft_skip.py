"""Pin the draft-pull-request skip in the spec validation workflow.

`Validate Spec Coverage` is a required status check, and the steps it gates
call paid AI agents (Analyst and Critic). Trunk Merge Queue tests a queued
pull request by opening a *draft* pull request, so without this skip every
queued pull request pays for a second full agent review that reviews the same
code the source pull request already reviewed.

The skip is expressed as a step-level output, never a job-level `if:`. The job
name is the required context, so the job runs on every pull request and
reports a real conclusion. A job-level `if:` would change the conclusion that
context reports on every draft, and the queue reads that conclusion to decide
whether to advance.

`Check for Failures` is the only step that can fail the job, and it carries
the same `skip != 'true'` guard, so a skipped draft reports success.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "ai-spec-validation.yml"
)

_SKIP_GUARD = "steps.should-run.outputs.skip != 'true'"


@pytest.fixture(scope="module")
def job() -> dict:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["validate-spec"]


@pytest.fixture(scope="module")
def should_run_step(job: dict) -> dict:
    steps = [s for s in job["steps"] if s.get("id") == "should-run"]
    assert len(steps) == 1, "expected exactly one should-run step"
    return steps[0]


def test_required_context_name_is_unchanged(job: dict) -> None:
    """The job name is the required status check context; renaming it is a
    branch-protection change (`.claude/rules/ci-scripts.md` MUST 22)."""
    assert job["name"] == "Validate Spec Coverage"


def test_job_is_not_gated_on_draft_state(job: dict) -> None:
    """Negative control. Gating the job on draft state changes the conclusion
    the required context reports on every queued pull request."""
    assert "draft" not in str(job.get("if", ""))


def test_draft_state_is_read_into_the_skip_step(should_run_step: dict) -> None:
    """Positive: the step reads draft state through env, not inline
    interpolation into the shell body."""
    assert should_run_step["env"]["IS_DRAFT"] == "${{ github.event.pull_request.draft }}"
    assert "${{" not in should_run_step["run"]


def test_draft_sets_skip(should_run_step: dict) -> None:
    body = should_run_step["run"]
    assert '"$IS_DRAFT" = "true"' in body
    assert "skip=true" in body


def test_no_code_changes_still_sets_skip(should_run_step: dict) -> None:
    """Edge: the draft branch must add to the existing skip, never replace it."""
    body = should_run_step["run"]
    assert '"$HAS_CODE_CHANGES" != "true"' in body
    assert body.count("skip=true") == 2


def test_failing_step_is_gated_on_the_skip(job: dict) -> None:
    """The only step that can fail the job honours the skip, so a skipped
    draft reports success rather than a red required context."""
    failing = [s for s in job["steps"] if s.get("name") == "Check for Failures"]
    assert len(failing) == 1
    assert failing[0]["if"].startswith(_SKIP_GUARD)


def test_every_agent_step_is_gated_on_the_skip(job: dict) -> None:
    """Positive: the paid agent steps are what the draft skip exists to avoid
    paying for twice."""
    agent_steps = [
        s
        for s in job["steps"]
        if "Agent)" in str(s.get("name", "")) or s.get("id") in {"trace", "completeness"}
    ]
    assert agent_steps, "no agent steps found"
    for step in agent_steps:
        assert _SKIP_GUARD in step.get("if", "")
