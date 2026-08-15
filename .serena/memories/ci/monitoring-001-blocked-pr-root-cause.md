# Skill: Blocked PR Root Cause Analysis (96%)

## Statement

When a PR shows BLOCKED status, examine specific check statuses - don't assume "awaiting review" without verifying required checks have run.

## Context

When monitoring PRs for actionable issues. BLOCKED can mean:

1. Awaiting human review (true wait state)
2. Required check hasn't run (actionable - needs main merge)
3. Check failed (actionable - needs fix)
4. Merge conflict (actionable - needs resolution)

## Evidence

PR #334 (2025-12-24): Incorrectly marked as "awaiting review" when actual blocker was "Validate Memory Files" check not running. The check was a required status check, but PR predated the fix (PR #346) that made the workflow always run.

## Anti-Pattern

```text
# WRONG: Assume BLOCKED means waiting for review
if (mergeStateStatus == "BLOCKED") {
    mark as "awaiting review"
}

# RIGHT: Check specific blockers
if (mergeStateStatus == "BLOCKED") {
    checks = get_pr_checks()
    if (any_check_pending_or_not_run()) {
        investigate why check not running
    }
    if (any_check_failed()) {
        investigate if fixable
    }
    if (all_checks_pass() && reviewDecision == "") {
        THEN mark as "awaiting review"
    }
}
```

## Pattern: Required Check Diagnosis

```bash
# Get all required checks status
gh pr checks $PR_NUMBER --repo $REPO | grep -E "(pending|fail|skipping)"

# If check shows "skipping" or not present, likely needs:
# 1. Merge main to pick up workflow changes
# 2. Or workflow has path filters preventing run
```

## Root Cause Types

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Check shows "pending" indefinitely | Workflow not triggered | Merge main or re-push |
| Check not in list | Required check workflow has path filters | Merge main with fix |
| Check shows "skipping" | Conditional execution skipped | Check conditions |
| Check shows "fail" | Actual failure | Fix code/config |

## Superseded specifics (measured 2026-08-01)

The principle above holds. Three of its specifics no longer match the repo:

1. "Needs main merge" is NOT a valid diagnosis. The main ruleset
   sets `strict_required_status_checks_policy: false`, so being behind main
   does not block a merge. Do not refresh the branch unless a status check
   itself requires current content (e.g. count ratchets).
2. "Awaiting review" is rarely the answer. `required_approving_review_count`
   is 0. What does block is `required_review_thread_resolution: true`, so an
   unresolved thread, not a missing approval.
3. `BLOCKED` with every gate clear does not mean the server refuses. Verified
   on #4387 and #4328: both merged on the first call to the merge endpoint.

Read `diagnosing-a-blocked-pr.md` for the measured ruleset, the API paths, and
the three-outcome diagnosis. That file is authoritative for what gates a merge
in this repo; this one is authoritative for the reasoning habit.

## Memory-First Requirement

**BEFORE** marking any PR as "awaiting review", read:

- `ci-workflow-required-checks.md` - Understand required check patterns
- Specific workflow files to understand trigger conditions

## Atomicity

96% - Single focused skill about BLOCKED status root cause analysis

## Tag

helpful

## Impact

10/10 - Prevents wasted cycles and incorrect status reporting

## Created

2025-12-24

## Validated

1 (PR #334 incident)
