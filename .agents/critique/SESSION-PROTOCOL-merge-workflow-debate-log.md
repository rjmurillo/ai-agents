# SESSION-PROTOCOL Merge Workflow Debate

## Decision under review

Document a serial GitHub auto-merge drain for a user-owned repository:

- `strict_required_status_checks_policy: false`
- no GitHub native merge queue
- no external merge queue
- one auto-merge front at a time
- update and test only the front PR against a recorded main SHA
- halt after any red main push

## Evidence

| Claim | Evidence |
|-------|----------|
| Strict is disabled | Ruleset 11104075 API returned `strict: false` |
| Native queue unavailable | GitHub merge queue requires an organization-owned repository |
| Trunk removed | PR #4814 and issues #4815/#4818 closed; remote branches deleted |
| Parallel refresh cost | 41 branch updates triggered 820 queued/in-progress runs |
| Cost rollback | Auto-merge disabled on 41 PRs; 818 runs cancelled |
| Serial invariant started | Exactly one PR, #4792, left armed |

## Review history

The first two review rounds evaluated strict freshness plus auto-merge. That
decision was abandoned after its O(N²) cost became concrete. The final round
reviewed the materially different strict-off serial procedure.

### Final-round findings

| Finding | Resolution |
|---------|------------|
| SHA check and merge are not atomic | Residual TOCTOU is explicitly accepted; concurrent landing sessions prohibited |
| One-front rule is procedural | Exact disarm command and verify-zero assertion added |
| `update-branch` can return 422 | Head reread, current-state check, one retry, then stop |
| Parallel update claim said O(N) | Corrected to O(N × R), where R is attempts per PR |
| Residual race could damage main | New main push workflows must be green before next PR; red halts drain |
| Main-health step lacked a command | Added `gh run list --commit "$MAIN_SHA"` command |

## Final votes

| Reviewer | Vote | Remaining P0/P1 |
|----------|------|-----------------|
| Architect | ACCEPT | None |
| Critic | ACCEPT | None |
| Independent Thinker | ACCEPT | None |
| Security | ACCEPT | None |
| Analyst | ACCEPT | None |
| High-Level Advisor | ACCEPT | None |

## Strategic lenses

| Lens | Result |
|------|--------|
| Chesterton's Fence | PASS. The strict and Trunk experiments are preserved with measured costs. |
| Reversibility | PASS. Strict is one ruleset field; serial drain can stop after any PR. |
| Core vs context | PASS with caution. Merge orchestration is context, so the solution uses GitHub APIs rather than a custom service. |
| Second-system effect | PASS. No queue, daemon, lock service, or repository bot is introduced. |

## Consensus

Six of six reviewers ACCEPT. No P0 or P1 issues remain. The residual stale-base
window is accepted, not hidden, and its blast radius is capped at one merge by
the post-merge main-health gate.
