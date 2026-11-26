# ADR-124 Debate Log

## Summary

- **Rounds**: 1 of 10. Round 2 has not run.
- **Prior debate log**: None. Round 1 ran on the draft numbered ADR-123.
- **Outcome**: Blocked in round 1. The owner narrowed scope afterward.
- **Final Status**: proposed.
- **Date**: 2026-11-20.
- **Claims ledger**: [ADR-124-claims-ledger.md](ADR-124-claims-ledger.md).

## Renumbering

Main merged a different ADR-123 while this draft was open.
The uniqueness helper returned 124 after the merge.
The draft, this log, and the ledger moved to ADR-124.
Round 1 text below is preserved from the ADR-123 draft log.

## Phase 0

GitHub related-work search found PR 7423, the external SDK marker change.
That search did not establish acceptance of the bundle design.

## Round 1 Votes

| Seat | Vote | P0 | P1 |
| --- | --- | ---: | ---: |
| Architect | Block | 2 | 3 |
| Critic | Block | 2 | 3 |
| Independent thinker | Block | 2 | 3 |
| Security | Block | 2 | 2 |
| Analyst | Block | 2 | 3 |
| High-level advisor | Block | 2 | 3 |

Three Codex seats first stalled and were interrupted under owner decision D23 A.
Native retries then stopped with exhausted model usage.
The votes above come from fresh reviews that completed.

## Consolidated P0 Findings

1. Resolver payoff is unmeasured. All six seats ask for a replay after genuine document repairs.
   The analyst found Python import repairs cleared 11 raw `UTC` findings in a sample.
   The same C# sample kept all 12 findings and added three `System` findings.
2. Replacing legacy shortcuts widens scope beyond D20 A for local receivers.
   Disabling the C-family receiver shortcut adds 87 raw findings (31 canonical).
   Disabling Python stdlib shortcuts adds 136 raw findings (42 canonical).
   Owner approval is required before this change.
3. Occurrence coverage and failure contracts are undefined. The critic reproduced false passes in the current scanner.
   Mixed fences, a shadowed alias, and an unrelated repository name each cleared an unproven occurrence.
   The independent thinker and analyst showed real imports can hide an invented export.
4. A gate must not trust a pin from the checkout under review. A forged bundle could act as an allowlist.
   Adapter argv, environment, and file access must stay inside verified inputs.

## Consolidated P1 Findings

- A new blocking pre-PR check is a policy change. It needs a separate owner decision.
- Bundle owner, hosting, platform matrix, size budget, refresh cadence, and rollback are undefined.
- The custom Python stub reader lacks evidence. The probe measured mypy only.
- Scans need limits on input, time, memory, and output. Unknown completeness must fail.

## Consolidated P2 Findings

- `decision-makers` is empty.
- Record one end-to-end time and memory budget on the same corpus.
- Attach the original Roslyn timing output. The ADR and milestone disagree.
- Record the manifest digest and adapter identity in the gate summary.

## Strategic Checklist

Every seat marked Chesterton, Path Dependence, Core vs Context, and Second-System as Fail.

## Owner Decisions After Round 1

- D24 A: repair documents first with the unchanged proof rules, replay, then narrow the ADR.
- D25 A: keep the legacy local and stdlib shortcuts. A follow-up ADR owns removal.
- D26 A: keep Phase 3 blocking in `/build` and `/test` only. Pre-PR stays advisory.
- D27 A: fix the reproduced false passes in the current scanner on this branch, test-first.
- D28 A: narrowly amend D25 to allow occurrence binding and positive member checks.
- D29 A: ship the branch with this residual tracked in issue #7501.

## Revision After Owner Decisions

The author revised the draft to the residual scope on 2026-11-20.

| Round 1 finding | Revision |
| --- | --- |
| P0 1, payoff unmeasured | Context records the `6a8c7e8c8` replay after D24 repairs. |
| P0 2, shortcut removal | Shortcuts stay. Proof applies on top of them. |
| P0 3, occurrence coverage | D27 fixed the reproduced false passes. Verification binds per occurrence. |
| P0 4, trusted pin | The pin ships in the scanner release. The checkout under review supplies no pin. |
| P1, pre-PR blocker | Removed. Pre-PR stays advisory under D26. |
| P1, scan limits | Each adapter is bounded by time, memory, and output size. |
| P1, package SDKs | Package SDKs leave the bundle. Their names stay findings. |
| P2, decision-makers | Set to `rjmurillo`. |

Open for round 2: bundle owner, hosting, refresh cadence, and rollback.
Open for round 2: the Python stub reader versus mypy.

## Next Step

Round 2 must review the revised draft with the full panel.
The change touches a rule that `/build` and `/test` gates read.
