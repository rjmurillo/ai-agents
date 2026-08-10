# Cancelling Required Runs Destroys Status Recovery

**Atomicity**: 98%
**Category**: CI operations, GitHub Actions, required checks

## Statement

Never bulk-cancel required CI without a recovery event for every affected PR.

## Observation

[2026-08-09] [user]: A panic cancellation stopped 818 queued or in-progress
workflow runs after 41 PR branches were updated in parallel. The cancelled runs
were the only producers of required status contexts. PRs then showed cancelled,
pending, or permanently missing checks.

Close/reopen was not a universal recovery because active workflows with
explicit `pull_request.types` omitted `reopened`. A tree-identical commit was
needed to emit `synchronize` and regenerate the full check set.

## Constraint

Before cancelling runs on PR branches:

1. List affected PRs, workflow names, and required check contexts.
2. Name the event that will regenerate each context.
3. Prove that event is included in each workflow's trigger contract.
4. Cancel only after the recovery plan exists.

If no recovery event is proven, do not cancel the run.

## Relations

- **related_to**: ci-concurrency-group-evicts-pending-runs-on-main
- **related_to**: ci-infrastructure-workflow-required-checks
- **related_to**: agent-behavior/error-recovery-obligations
