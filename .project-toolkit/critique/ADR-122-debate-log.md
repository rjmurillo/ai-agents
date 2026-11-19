# ADR Debate Log: ADR-122 Scoped Parser Dependency Admission

## Summary

- **Rounds**: 6 of 10. Rounds 3 and 4 are reduced-panel amendments. Rounds 5 and 6 are full-panel amendments.
- **Prior debate log**: None.
- **Outcome**: Consensus.
- **Final Status**: accepted.
- **Date**: 2026-11-16. Amended 2026-11-18 (Rounds 3 to 6).

## Round 1 Summary

### Key Issues Addressed

The panel reviewed the fixed admission, failure boundaries, authorization, and rollback.
Security blocked because the working-tree review scope was not enumerable.
That vote did not identify a vulnerability in the inspected excerpts.

### Major Changes Made

No policy expansion followed the panel review.
The author prepared a complete implementation diff, including the new governance artifacts.

### Agent Positions

| Agent | Position | Review identifier |
|---|---|---|
| Architect | Accept. | `93fa6ab5-9267-452b-8f5b-5307064356ab` |
| Critic | Accept. | `818dba6c-7d44-48f4-bb0f-613136adaa54` |
| Independent thinker | Accept. | `cf54899a-9119-44bc-ab06-5790e4ba662d` |
| Security | Block. Complete implementation scope was unavailable. | `33bfa1a7-ce89-48b3-98f5-7a636f968693` |
| Analyst | Accept. | `63e703de-c810-4852-b4c9-5f47d4b1b300` |
| High-level advisor | Accept. | `45c25671-8b4a-454c-a3e1-bd3b557507c0` |

## Round 2 Summary

### Key Issues Addressed

Security received the complete implementation diff against the reference revision below.
The diff included the new ADR and claims ledger.

- Reference revision: `5ac4f739ee088a2a50bea7395763c378d0d1ffd7` (2026-11-16).
- Diff SHA-256: `16251c6665fbaa0c3fbbdc8a25d1c50d6feb0a03bde8d6c086a77851c1637006`.

The author independently computed that digest.
Security read the complete artifact but did not recompute its digest.
Security found no P0 or P1 issue and voted Accept.
The other seats' unchanged Round 1 votes remain recorded above.
No seat claimed to rerun the recorded test commands.

### Major Changes Made

Only review evidence and ADR lifecycle metadata changed after the security vote.
The executable admission contract remained unchanged.

### Agent Positions

| Agent | Position | Evidence |
|---|---|---|
| Architect | Accept. | Carried unchanged from Round 1. |
| Critic | Accept. | Carried unchanged from Round 1. |
| Independent thinker | Accept. | Carried unchanged from Round 1. |
| Security | Accept. | `d2d1d352-8b2c-4056-b486-7d73e14b030e` |
| Analyst | Accept. | Carried unchanged from Round 1. |
| High-level advisor | Accept. | Carried unchanged from Round 1. |

## Round 3 Summary (Reversibility amendment, 2026-11-18)

### Trigger

Review axes on PR #7412 found no retirement step for the admission.
The amendment adds removal text under `### Reversibility`.
It changes no executable enforcement, so a reduced panel ran.

### Key Issues Addressed

- The first draft said the admission could never match again. That was false.
- The scanner compares against the merge base, so an older base still matches.
- The first draft's removal list left out tests, docs, the template, and copies.
- The follow-up had no checkable trigger.

### Changes Made

- The text now says the admission matches only when the merge base predates the merge.
- It lists the removal scope, including the skill template and every plugin copy.
- It names a `git branch -r --no-contains` check before removal.
- It marks the record deprecated after removal.

### Agent Positions

| Agent | Position | Evidence |
|---|---|---|
| Architect | Accept. | Accepted the revised text in the re-vote. |
| Critic | Accept. | Its two required edits were applied verbatim. |

The panel reached consensus on the amendment.
These votes are not GitHub approvals or merge permission.

## Round 4 Summary (Permanence ruling, 2026-11-18)

### Trigger

On 2026-11-18, the maintainer ruled the parser dependencies permanent design.
No sunset, retirement issue, or fixed date applies.
The ruling replaces the Round 3 retirement plan.
JavaScript, TypeScript, Python, and PowerShell get the same parser approach later.
The amendment changes no executable enforcement, so a reduced panel ran.

### Changes Made

- Status and Context record the ruling and state that no time bound applies.
- Decision items 6 and 7 record permanence and the follow-on languages.
- Item 7 says a later parser import needs its own admission decision.
- Rationale adds the rejected option to exclude parser packages from coupling.
- Consequences state the install need, exit 1 for any scan with C#, and `UNKNOWN`.
- Consequences state that ADR-121 rule 2 scans only module-load imports.
- Reversibility drops the Round 3 removal steps and their trigger.

### Agent Positions

| Agent | Position | Evidence |
|---|---|---|
| Architect | Accept. | Its two required edits were applied verbatim. Factual claims checked against code. |
| Critic | Accept. | Its four required edits were applied verbatim. |

The panel reached consensus on the amendment.
The ruling itself was the maintainer's decision, not a panel vote.
These votes are not GitHub approvals or merge permission.

## Round 5 Summary (TypeScript admission, 2026-11-18)

### Trigger

Issue #7435 adds the TypeScript parser under item 7.
The scanner's own coupling moves from 8.0 to 7.0, which the C# record does not admit.
The maintainer approved the package add and its own admission on 2026-11-18.
The amendment changes executable enforcement in the scanner and review adapter.

### Changes Made

- Status records the amendment.
- Decision item 8 adds the fixed TypeScript record and its exact transition.
- Item 8 states that each record admits only its own transition.

### Agent Positions

| Agent | Position | Evidence |
|---|---|---|
| Architect | Revise, then accept. | Item 8 matched the code. Its seven edits to stale C#-only lines were applied. |
| Security | Accept. | No admission bypass found. Parse failures exit 1. The package is pinned and hashed in `uv.lock`. |

Security raised two low findings, recorded and not acted on here.
Admission keys on path, scores, and imports, not on content.
A revert and reintroduction re-admits the transition, as Reversibility already states.
`.mts` and `.cts` files stay unmapped, as before this change.

| Agent | Position | Evidence |
|---|---|---|
| Critic | Revise, then accept. | Five of six edits applied verbatim. The title rename was declined; Context names item 8 instead. |
| Independent-thinker | Revise, then accept. | Its item 8 text on the admission table and record chaining was applied verbatim. |

The critic noted the quote did not appear on the issue.
It now appears verbatim in issue #7435 comment 6994828821.
The independent-thinker noted the scanner's own coupling now sits at the 7.0 floor.
The next parser import drops it to 6.0, below "reasonable". The amendment records this as a known cost.

| Agent | Position | Evidence |
|---|---|---|
| Analyst | Revise, then accept. | Every factual claim verified against code and tests. One count corrected from two files to three. |
| High-level-advisor | Revise, then accept. | The revisit trigger moved to "before a third record lands", so it can fire. |

The high-level-advisor also proposed that siblings fitting item 8 need no further amendment.
That edit was declined: it pre-admits later transitions, which item 7 forbids.
Each sibling keeps its own maintainer admission decision.

All six panel agents accept the amendment as revised.

A PR review then noted that item 8 did not order exit codes before records.
Item 8 now states that exits 10 and 11 report `FAIL` before any record is read.
This matches `adapt_local_axis_verdict` and changes no enforcement.
These votes are not GitHub approvals or merge permission.

## Round 6 Summary (Python admission, 2026-11-18)

### Trigger

Issue #7436 adds the Python parser under item 7.
After item 8, the scanner's own coupling moves from 7.0 to 6.0, which no earlier record admits.
The maintainer approved the package add and its own admission on 2026-11-18.
The quote appears verbatim in issue #7436 comment 6995934831.
The amendment changes executable enforcement in the scanner and review adapter.

### Changes Made

- Status and Context name item 9.
- Item 9 adds the fixed Python record: base 7.0, head 6.0, four exact imports.
- Item 8's two-record wording now covers every record.
- Consequences record that item 9 reached the third-record revisit trigger.
- The new trigger is a drifted record copy or a grammar that needs another record shape.
- Consequences add Python fail-closed scans, the `UNKNOWN` review result, and the 6.0 coupling floor.

### Agent Positions

| Agent | Position | Evidence |
|---|---|---|
| Architect | Revise, then accept. | Item 9 matched the code. Its three edits to stale two-record text and the trigger were applied. |
| Security | Accept. | No admission bypass. The package is pinned and hashed. |

Security noted two malformed node shapes that left a file unscored instead of exiting 1.
Both now raise the Python parser error, with a test.

| Agent | Position | Evidence |
|---|---|---|
| Critic | Revise, then accept. | The quote is verbatim. Its edit attributing the record shape to the coordinator was applied. |
| Independent-thinker | Revise, then accept. | The fifth-record trigger would certainly fire, so it was replaced. The Python reference now names the TypeScript package. |

The independent-thinker and the architect noted that no test compared the adapter's records with the scanner's.
A direct field-for-field test now does, and it fails when either copy drifts.

| Agent | Position | Evidence |
|---|---|---|
| Analyst | Accept. | Verified scores, imports, record equality, exit paths, and import placement against code. |
| High-level-advisor | Revise, then accept. | Required this Round 6 entry and the corrected round count. |

The high-level-advisor noted that JavaScript and PowerShell take the scanner to 5.0, then 4.0.
Those two records cannot both chain from 6.0, so they merge one at a time.
These are recorded as follow-ups, not changes here.

All six panel agents accept the amendment as revised.
These votes are not GitHub approvals or merge permission.

## Decision Boundaries

The admission preserves raw scores, counts, regressions, and the original diagnostic.
Only the maintainer-authorized parser dependency transition receives admission.
Other regressions, evidence loss, and new-file threshold failures remain blocking.
Valid admission becomes `WARN`, not raw `PASS`.
Duplicated fixed-contract validation remains a bounded maintenance cost.
No generic exception framework or separate cohesion exception was authorized.
These agent votes are not GitHub approvals or protected-merge permission.

## Strategic Assessment

The existing coupling gate's purpose remains valid.
This decision admits one authorized dependency trade-off without changing measurement.
Removing the configuration restores ordinary rejection.
Using a language parser avoids maintaining another C# grammar in regex.
The fixed record avoids a framework without a present consumer.
The panel accepted this bounded decision, subject to normal shipping protections.
