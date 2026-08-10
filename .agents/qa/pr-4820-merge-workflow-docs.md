---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10026-merge-workflow-docs.json
qaCommit: 1a692aa7d951f6a796b857e33e7b173402424f41
---
# Test Report: Strict Serial Auto-Merge Protocol

## Scope

Documentation-only change for issue #4820:

- [`.agents/SESSION-PROTOCOL.md`](../SESSION-PROTOCOL.md)
- [`.agents/governance/GOTCHAS.md`](../governance/GOTCHAS.md)
- [`.agents/architecture/ADR-094-strict-serial-auto-merge.md`](../architecture/ADR-094-strict-serial-auto-merge.md)
- [`.agents/critique/ADR-094-debate-log.md`](../critique/ADR-094-debate-log.md)
- [formal consensus decision](../decisions/decision-2026-08-10T07-51-00-109946+00-00.json)
- [`.agents/retrospective/2026-08-09-trunk-ci-cancellation-incident.md`](../retrospective/2026-08-09-trunk-ci-cancellation-incident.md)
- three new CI Serena memories and one updated agent-behavior memory

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

The retrospective runs Five Whys and fishbone analysis over the 820-run update
and 818-run cancellation. Four learnings scored 75%, above the 70% persistence
threshold, and were persisted to Serena with memory-index entries.

## Verdict

PASS. The documentation matches live policy, preserves stale-merge safety, and
records the cost control that prevents another parallel CI explosion.
