# ADR Debate Log: ADR-120 The Completion Gate Reports a Refused Session as Unknown (second debate)

## Summary

- **Rounds**: 2 of 10. Round 2 reached consensus.
- **Prior debate log**: `.project-toolkit/critique/ADR-120-debate-log.md`
- **Outcome**: Consensus. Round 2: six Accept.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-120-completion-gate-unknown-verdict.md`
- **Edit**: Decisions 3, 4, and 8. The gate now treats `api_error: true` as an unanswered row. A Negative bullet that accepted a `failed` row in this case is removed.
- **Trigger**: an owner-requested review of PR #7090. The merged gate ran against a fake `gh` in three refusal shapes. With the viewer query served and repository calls refused, it gave verdict `fail` on a healthy PR. `get_unresolved_review_threads.py` reports an API failure at exit 0, so that row never became unknown and outranked four correct rows.
- **Why a new log**: the first log closed, so this edit opens a new debate.

Panel: full panel, because the edit changes executable enforcement.

Method: each seat ran as its own subagent with read-only tools and voted on the diff.

## Round 1 (2026-11-04)

The first revision keyed on `fetched_pages_complete: false`.

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | Criterion met. Decision 3 wording needs care. |
| critic | Accept | No false pass. `pass_when` requires the field to be true. |
| independent-thinker | Accept | The field only decides whether to probe. |
| security | Block | A PR commenter controls the field. A thread with 101 comments sets it false. |
| analyst | Disagree-and-Commit | Decision 3 and criterion 4 became literally false. |
| high-level-advisor | Accept | Decision 3 needs a clause on what the field decides. |

### Issues Raised

| Priority | Issue | Resolution |
|----------|-------|------------|
| P1 | `fetched_pages_complete` is reachable by a PR commenter, so a real failure could read unknown | The gate reads `api_error`, set only when a `gh` call raised |
| P1 | Decisions 3 and 8 stated guarantees the code no longer met | Both rewritten |
| P2 | Spec criteria 3, 4, and 5 contradicted the code | All three updated |

## Round 2 (2026-11-04)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | Decision 3 matches the code. |
| critic | Accept | Only the raised call sets `api_error`. |
| independent-thinker | Accept | No open P0 or P1. |
| security | Accept | A PR author cannot set `api_error`. Conditional on this log. |
| analyst | Accept | All three findings resolved. |
| high-level-advisor | Accept | The revision fixes a real hole. |

### Dissent and P2 Items

| Item | Agent | Disposition |
|------|-------|-------------|
| "Only a failed `gh` call can read unknown" overclaims, since exit 2 can too | security | Fixed after the vote. The sentence now names exits above 1 |
| Probes run bare `gh` from PATH | critic | Dissent recorded. Residual risk states it |
| `gh_graphql` raises for any failure, so a GraphQL error body sets `api_error` | independent-thinker | Dissent recorded. A row changes only with a measured REST refusal, and it never passes |
| A later page failing after page 1 found threads reads unknown | security | Dissent recorded. It needs over 100 threads and a real failed call, and the hand check runs |
| No test for a future verifier that emits `api_error` | critic | Dissent recorded. Only one verifier emits it today |

## Closing Summary

Consensus in round 2 with six Accept. Security's Block changed the mechanism, and that change is what the panel accepted. The one post-vote edit narrows a sentence and changes no decision.
