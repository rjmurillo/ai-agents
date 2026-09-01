# PR 5002 URL routing: push-gate catch before publish

**Date**: 2026-08-15
**Scope**: `.claude/skills/github-url-intercept/scripts/test_url_routing.py`, `src/copilot-cli/skills/github-url-intercept/scripts/test_url_routing.py`, `tests/skills/github/test_url_routing.py`, `tests/skills/github_url_intercept/test_repository_url_routing.py`, `scripts/validation/skill_portability_baseline.json`
**Trigger**: Issue #4993, PR #5002

## What happened

The URL-routing fix itself was correct and the scoped test pass was green, but the
branch was not actually ready to publish.

The first push attempt was blocked by a stale mutation-harness process in this
worktree. After recovery, the next push attempt cleared mutation safety and then
failed three later gates:

1. `retrospective-policy`, because this branch had no retrospective evidence.
2. `merge-tree-ratchet`, because the merged tree carried one extra taste error.
3. `pre-pr-validation`, because it reran the same merge-tree ratchet and failed
   for the same reason.

The extra taste error was our own new complexity finding on
`parse_github_url`. The function had grown to complexity 13 while closing the
control-character and malformed-host gaps.

## Failure mode classification

**Primary: #4 False completion markers** (`.agents/governance/FAILURE-MODES.md`).
The branch looked done after the scoped pytest run, but the publish gates proved
it was not done. "Tests passed" was treated like "ready to push", and those are
not the same claim in this repository.

**Secondary: #1 Context reading failure.** The branch reached push without the
retrospective artifact the protocol expects. The gate existed to catch exactly
that missing context artifact.

## Evidence

- Issue #4993 defines the URL-routing bug to fix.
- PR #5002 is the delivery branch for this work.
- Commit `2bb3c772d` contains the routing hardening and test updates.
- Merge commit `c6d3030338` brought `origin/main` into the branch without a
  force-push.
- `git_hook_policy.py retrospective ...` failed with `ERROR: git push requires
  retrospective evidence for this session`.
- `scripts/ci/merge_tree_ratchet_check.py --base-ref origin/main` failed with
  `taste count ratchet: REGRESSION. 584 > effective baseline 583 (+1)`.
- Direct taste-count diagnostics identified the branch-specific offender as
  `.claude/skills/github-url-intercept/scripts/test_url_routing.py: [complexity]
  Function 'parse_github_url' has complexity 13 (max 10)`.

## Impact

| Area | Severity | Detail |
|---|---|---|
| Publish latency | Medium | Two push attempts failed after the feature work was otherwise verified. |
| Signal quality | Medium | The scoped test pass hid a later publish blocker. |
| Code quality | Low | One new taste violation entered the branch and was caught before publish. |

## What worked

- The scoped pytest run caught the routing behavior regressions quickly.
- Mutation-safety blocked a push while a stale harness marker existed.
- The merge-tree ratchet prevented a new taste-count regression from landing.
- The retrospective gate caught missing session evidence before publish.

## What did not work

- The branch did not run the publish-shaped gates before the first push.
- The complexity increase in `parse_github_url` was visible as an advisory at
  commit time and still reached pre-push.
- Retrospective evidence was left until the gate demanded it.

## Remediation

| Action | Status | Reference |
|---|---|---|
| Refactor `parse_github_url` into smaller helpers so the new safety checks do not raise complexity debt | Done | PR #5002 |
| Merge `origin/main` into the branch instead of rebasing, because force-push is forbidden here | Done | PR #5002 |
| Record a retrospective before the final push, not after a gate failure | Done | this file |
| Treat "scoped tests green" as different from "publish gates green" on branch work | Done | PR #5002 |
