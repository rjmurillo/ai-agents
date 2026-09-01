"""Fixture builders reproducing the 2026-08-09 bulk-cancellation blast radius.

Issue #4835 records the incident shape: 41 PR branches updated in parallel,
820 queued or in-progress workflow runs, 818 cancelled. These builders recreate
that shape so the guard's dry-run report is exercised against the real scale
rather than a two-run toy.

Shared by tests/ci/test_recovery_manifest.py and
tests/ci/test_bulk_cancel_guard.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from scripts.github_core.recovery_manifest import WorkflowRun, plan_recovery
from scripts.github_core.workflow_event_subscriptions import (
    WorkflowSubscriptions,
    parse_workflow_subscriptions,
)

INCIDENT_PR_COUNT = 41

# Frozen so a manifest's `generated_at` is assertable.
PINNED_CLOCK = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

# Two required contexts drawn from the pinned ruleset contract in
# scripts/ci/ruleset_required_contexts.py, plus one context that ruleset does
# not require. Workflow name and context name are deliberately different, which
# is how the real repository is shaped: .github/workflows/pr-validation.yml
# line 1 reads `name: PR Validation` and line 43 reads `name: Validate PR` for
# the job, and branch protection matches the job name, not the workflow name.
REQUIRED_WORKFLOW = "PR Validation"
REQUIRED_CONTEXT = "Validate PR"
SECOND_REQUIRED_WORKFLOW = "Python Tests"
SECOND_REQUIRED_CONTEXT = "Run Python Tests"
OPTIONAL_WORKFLOW = "Label PR"
OPTIONAL_CONTEXT = "Sync Labels"
BASE_REPOSITORY = "rjmurillo/ai-agents"

_WORKFLOW_CONTEXTS = (
    (REQUIRED_WORKFLOW, REQUIRED_CONTEXT),
    (SECOND_REQUIRED_WORKFLOW, SECOND_REQUIRED_CONTEXT),
    (OPTIONAL_WORKFLOW, OPTIONAL_CONTEXT),
)

_CONTEXT_BY_WORKFLOW = dict(_WORKFLOW_CONTEXTS)


def make_run(
    run_id: int,
    *,
    workflow: str = REQUIRED_WORKFLOW,
    context: str | None = None,
    pr_number: int = 1,
    branch: str | None = None,
    event: str = "synchronize",
    status: str = "queued",
    head_repo: str = BASE_REPOSITORY,
) -> WorkflowRun:
    """Build one run record with sensible incident-shaped defaults.

    ``context`` defaults to the check context the named workflow really
    publishes, so a caller that only cares about ids does not accidentally
    build a run whose context is a workflow name nothing requires.
    """
    resolved = context if context is not None else _CONTEXT_BY_WORKFLOW.get(workflow, workflow)
    return WorkflowRun(
        run_id=run_id,
        workflow_name=workflow,
        pr_number=pr_number,
        branch=branch if branch is not None else f"feat/pr-{pr_number}",
        event=event,
        status=status,
        contexts=(resolved,),
        head_repo=head_repo,
    )


def incident_runs(pr_count: int = INCIDENT_PR_COUNT) -> list[WorkflowRun]:
    """Build the 41-PR inventory: three workflows per PR, alternating status.

    Each PR contributes one run per workflow in ``_WORKFLOW_CONTEXTS``, so the
    inventory holds ``pr_count * 3`` runs across ``pr_count`` branches.
    """
    runs: list[WorkflowRun] = []
    run_id = 1_000_000
    for pr_number in range(1, pr_count + 1):
        for index, (workflow, context) in enumerate(_WORKFLOW_CONTEXTS):
            run_id += 1
            runs.append(
                make_run(
                    run_id,
                    workflow=workflow,
                    context=context,
                    pr_number=pr_number,
                    status="queued" if index % 2 == 0 else "in_progress",
                )
            )
    return runs


def workflow_document(
    name: str,
    pr_types: list[str],
    *,
    jobs: dict[str, object] | None = None,
    paths: list[str] | None = None,
) -> dict[str, object]:
    """Build one parsed workflow document in the shape the real files take.

    ``jobs`` defaults to empty rather than to the workflow's own context so the
    static job-name union contributes nothing unless a test opts in. That keeps
    every case that predates the union scoring exactly the API-derived contexts
    it was written against.
    """
    trigger: dict[str, object] = {"types": list(pr_types)}
    if paths is not None:
        trigger["paths"] = list(paths)
    return {
        "name": name,
        "on": {"pull_request": trigger},
        "jobs": dict(jobs or {}),
    }


def subscriptions_with(types: dict[str, list[str]]) -> dict[str, WorkflowSubscriptions]:
    """Build a name-to-subscriptions map from workflow name to its PR types."""
    return {
        name: parse_workflow_subscriptions(workflow_document(name, list(pr_types)))
        for name, pr_types in types.items()
    }


def plan_with_pinned_contract(runs, subscriptions, recovery_event):
    """Plan against the pinned ruleset contract and a fixed clock.

    Shared by ``test_recovery_manifest.py`` and
    ``test_recovery_manifest_context_sources.py`` so both score runs against the
    same required-context set the production CLI passes.
    """
    return plan_recovery(
        runs,
        required=REQUIRED_CONTEXTS,
        subscriptions=subscriptions,
        recovery_event=recovery_event,
        repository=BASE_REPOSITORY,
        now=PINNED_CLOCK,
    )


def healthy_subscriptions() -> dict[str, WorkflowSubscriptions]:
    """Every incident workflow subscribing to both recovery-capable PR types."""
    return subscriptions_with(
        {
            workflow: ["opened", "synchronize", "reopened"]
            for workflow, _ in _WORKFLOW_CONTEXTS
        }
    )


def reopened_omitting_subscriptions() -> dict[str, WorkflowSubscriptions]:
    """The 2026-08-09 shape: one required workflow omits ``reopened``."""
    healthy = healthy_subscriptions()
    healthy.update(
        subscriptions_with({REQUIRED_WORKFLOW: ["opened", "synchronize"]})
    )
    return healthy
