# ADR Debate Log: ADR-122 pin renewal D12 and score change D13

## Summary

- **Rounds**: 4 advisor rounds, then a sol-loop of 2 rounds
- **Prior debate log**: [ADR-122-debate-log-4.md](ADR-122-debate-log-4.md)
- **Claims ledger**: [ADR-122-claims-ledger.md](ADR-122-claims-ledger.md)
- **Outcome**: Accepted. The owner kept the advisor rounds going and chose the sol-loop.
- **Final status**: accepted

## Scope

Decision D12 fixed review threads T2, T4, and T6 on PR #7523.
It renewed the search.py and recall shim head pins.
Decision D13 moved the search.py cohesion head score from 2.1 to 2.0.
A per-file deadline check in the filename scan added the lines.
Receipts: issue #7493 comments 7121288491 (D12) and 7121992178 (D13).
Both receipts were updated in place as the head blobs changed.

## Advisor rounds (Codex, decision D7)

Round 1 blocked twice.
The filename scan could overrun the recall deadline.
The shim could run an `__init__.py` linked outside the checkout.
Round 2 accepted the shim fix and blocked the scan again.
The clock was checked per directory, not per file.
Round 3 blocked the scan again.
The root listing and the final path resolution had no clock check.
The owner chose D13 to accept the score change and kept going.
The owner then directed the sol-loop.

## Sol-loop (gpt-6.2-sol)

Round 1 returned CHANGES with two blockers.
S1: padded link text passed the shim check.
S2: the scan read one entry before the clock check.
Both are fixed, and each has a test that fails on the old code.
The critic added three fixes: a symlink loop guard, a dot-entry skip, and ADR wording.
Round 2 returned APPROVE and marked S1 and S2 resolved.
Sol's last finding, S4 (a nit), is declined as a follow-up.
It matches the critic's C6: one entry that cannot resolve skips its siblings.
The run logs are under `.project-toolkit/metrics/sol-loop/`.

| Agent | Position |
| --- | --- |
| Security | Accept. Low notes only. The deadline note is fixed. |
| High-level advisor | Block in round 3. Sol round 2 approved the fix for each point. |
| Sol | Approve in round 2. |
| Critic | Approve with concerns. C6 is declined as a follow-up. |

The architect, independent thinker, and analyst seats did not run.
