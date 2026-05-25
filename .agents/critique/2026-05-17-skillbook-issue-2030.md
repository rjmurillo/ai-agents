# Critique: Skillbook Evidence-Tiered Policies (Issue #2030)

**Date**: 2026-05-17
**Session**: 1153
**Reviewer**: critic agent
**Verdict**: APPROVED_WITH_CONCERNS (confidence: HIGH)

## Summary

The skillbook implementation satisfies all 10 acceptance criteria of issue
#2030 with clean scoping, no creep into the deferred list, and a green test
suite. Approved for a pull request. Findings below are design-quality
concerns, not correctness blockers.

## Acceptance criteria

All 10 criteria verified PASS against the diff: seeded `policies.json`
(hypothesis tier, one policy per persona), `tensions.json`, `workflows.json`,
the six-command CLI with unit tests, four schemas plus the CI job, the
post-eval hook, a tagged eval fixture, the README, the documented promotion
boundary, and the never-decrease assertion plus its test.

## Findings and resolutions

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | `skillbook` name collides with the existing `skillbook` agent persona. | Non-blocking | Fixed: README "Not the skillbook agent" section disambiguates. |
| 2 | Post-eval idempotency depends on a stable run id, not enforced in code. | Non-blocking | Fixed: post-eval docstring and README state the run id is the canonical run directory name and must not be relabeled. |
| 3 | The skillbook is consumed by no agent yet. | Non-blocking | Fixed: README "Out of scope" now states no agent reads `select` in v1. |
| 4 | `assert new_rank >= old_rank` is structurally always true. | Non-blocking | Fixed: comment reworded to describe it as a regression guard. |
| 5 | `validate_skillbook.py` is not wired into `pre_pr.py`. | Non-blocking | Deferred to a follow-up. CI gates PRs via `skillbook-validation.yml`; the README documents the manual local command. `pre_pr.py` is CI-critical (Issue #1711) and a change there warrants its own PR. |
| 6 | No test drove a policy with populated evidence through the cross-file `$ref` plus integrity check. | Non-blocking | Fixed: `test_validates_a_policy_carrying_real_evidence` added. |
| 7 | `tension_prefer` re-pointing branch (same eval id, new winner) untested. | Non-blocking | Fixed: `test_prefer_repoints_when_same_eval_changes_winner` added. |

## Out-of-scope check

No violations. `select` uses simple ordering with no confidence weighting; no
auto-discovery, no in-session enforcement, no cross-repo sharing. The
implementation respected the deferred list.

## Disposition

Findings 1, 2, 3, 4, 6, 7 resolved in-session before PR. Finding 5 carried as
a follow-up and noted in the PR description.
