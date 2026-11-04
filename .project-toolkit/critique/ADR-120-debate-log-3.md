# ADR Debate Log: ADR-120 The Completion Gate Reports a Refused Session as Unknown (third debate)

## Summary

- **Rounds**: 1 of 10. Round 1 reached consensus.
- **Prior debate log**: `.project-toolkit/critique/ADR-120-debate-log-2.md`
- **Outcome**: Consensus. Round 1: two Accept.
- **Final Status**: accepted

## Change Under Review

- **ADR**: `.project-toolkit/architecture/ADR-120-completion-gate-unknown-verdict.md`
- **Edit**: one sentence in Decision 4 now names both ways a PR can set `fetched_pages_complete` false. No rule changes.
- **Trigger**: review of PR #7093 said a comment count cannot set that field in `get_unresolved_review_threads.py`. That is true of that script. `check_review_thread_resolution_shas.py` does compare comment counts, and the gate reads the field from every row, so the record names both paths.

Panel: reduced panel (architect, critic), because the edit is prose and changes no rule.

## Round 1 (2026-11-04)

### Agent Positions

| Agent | Position | Summary |
|-------|----------|---------|
| architect | Accept | Corrects a factual claim and changes no decision. |
| critic | Accept | Verified both paths against the source. |

### Issues Raised

None at P0, P1, or P2.

### Claims Checked

| Claim | Agent | Result |
|-------|-------|--------|
| A thread with over 100 comments sets the field in `check_review_thread_resolution_shas.py` | critic, security | VERIFIED |
| The 50-page cap sets the field in `get_unresolved_review_threads.py` | critic, security | VERIFIED |
| Comment count does not affect the field in `get_unresolved_review_threads.py` | security | VERIFIED |

### Carried Forward

The critic's P2 dissent on bare `gh` from PATH stands from the second log.

## Closing Summary

Consensus in round 1 with two Accept. The decision is unchanged.
