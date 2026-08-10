---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10026-merge-workflow-docs.json
qaCommit: dac8dfa0f57d2953793ec7601fba7c6cbf0149a6
---
# Test Report: Strict Serial Auto-Merge Protocol

## Scope

Documentation-only change for issue #4820:

- `.agents/SESSION-PROTOCOL.md`
- `.agents/governance/GOTCHAS.md`
- `.agents/critique/SESSION-PROTOCOL-merge-workflow-debate-log.md`

## Live evidence

| Claim | Verified result |
|-------|-----------------|
| Strict branch freshness | Ruleset 11104075 returned `strict: true` |
| No merge queue | Ruleset returned zero `merge_queue` rules |
| Native queue unavailable | Repository is user-owned, not organization-owned |
| Trunk removed | PR #4814 and issues #4815/#4818 closed |
| Parallel update cost | 41 branch updates triggered 820 runs; 818 cancelled |

## Procedure under test

Strict freshness provides the server-side stale-merge guard. Cost stays bounded
by updating and testing one front PR at a time. Dependent new work uses stacked
PRs; unrelated backlog work does not.

## Review

The review panel evaluated strict and non-strict variants. The strict-off
variant exposed a merge-time TOCTOU. The final design restores strict and keeps
the one-front cost control. No P0/P1 issue remains in the final model.

## Verdict

PASS. The documentation matches live policy, preserves stale-merge safety, and
records the cost control that prevents another parallel CI explosion.
