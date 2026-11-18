# ADR Debate Log: ADR-122 Scoped Parser Dependency Admission

## Summary

- **Rounds**: 5 of 10. Rounds 3 and 4 are reduced-panel amendments. Round 5 is a full-panel amendment.
- **Prior debate log**: None.
- **Outcome**: Consensus.
- **Final Status**: accepted.
- **Date**: 2026-11-16. Amended 2026-11-18 (Rounds 3 to 5).

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

## Round 5 Summary (Admission list amendment, 2026-11-18)

### Trigger

Issue #7436 moves Python coupling counting to `tree-sitter-python==0.25.0`.
Its grammar import lowers the scanner's coupling from 8.0 to 7.0, past the 0.5 tolerance.
The C# record admits only 10.0 to 8.0, so it cannot cover this transition.
The maintainer chose option A on issue #7436: one fixed list of per-grammar records.
The maintainer also approved the package add.
The amendment changes executable enforcement, so the full panel ran.

### Key Issues Addressed

- An int score in config equaled the built-in float record and reached the JSON.
  The adapter's type assert then raised instead of returning a verdict.
- Consequences ordered a C# sentence after Python lines, so "them" had the wrong subject.
- The ADR did not say unparsable Python exits 1, where the regex never failed.
- Counting by statement, not line, changed `;`-joined lines and was not disclosed.
- A consumer without the packages can never get a review `PASS` on Python changes.
- The scanner now sits at the default `coupling.min` of 7.0.
- A from-import node without a module name escaped the parser error handling.

### Changes Made

- The scanner reports the built-in record, never the config copy.
- The adapter finds the built-in record and returns `False` instead of asserting.
- The parity test compares serialized JSON, so `7` and `7.0` differ.
- Tamper tests cover both records, and the fixture deep-copies them.
- Consequences now cover Python fail-closed, `UNKNOWN` merging, the coupling floor, and the dead C# record.
- `references/python-parser.md` covers `;` counting and the invalid Python the grammar accepts.
- A from-import without a module node raises `PythonParserError`.
- Context cites the option A approval and the package approval separately.

### Agent Positions

| Agent | Position | Evidence |
|---|---|---|
| Architect | Accept. | Blocked in round 1 on the int-score crash and sentence order. Accepted the fixes. |
| Critic | Accept. | Blocked in round 1 on three disclosure edits. Accepted them verbatim. |
| Independent thinker | Accept. | Required the `UNKNOWN` merge disclosure. Accepted it on re-vote. |
| Security | Accept. | No P0 or P1. Checked all nine `uv.lock` hashes against PyPI. |
| Analyst | Accept. | Verified eight claims by reading code; found no caller of the old field name. |
| High-level advisor | Accept. | Required this Round 5 entry. Named follow-ups for the PR body. |

The panel reached consensus on the amendment.
The list design and the package add were the maintainer's decisions, not panel votes.
These votes are not GitHub approvals or merge permission.

### Follow-ups Named for the Maintainer

- The next grammar takes the scanner to 6.0, below the default `coupling.min`.
- Sibling grammars pin scores, so they must land one at a time and re-measure.
- Launching the scanner with its pinned packages would remove the manual install.

## Decision Boundaries

The admission preserves raw scores, counts, regressions, and the original diagnostic.
Only maintainer-authorized parser dependency transitions receive admission.
Each transition has one fixed record, built into the scanner and the adapter.
Other regressions, evidence loss, and new-file threshold failures remain blocking.
Valid admission becomes `WARN`, not raw `PASS`.
Duplicated fixed-contract validation remains a bounded maintenance cost.
No generic exception framework or separate cohesion exception was authorized.
The record list admits only scanner parser imports; it is not a general exception list.
These agent votes are not GitHub approvals or protected-merge permission.

## Strategic Assessment

The existing coupling gate's purpose remains valid.
This decision admits one authorized dependency trade-off without changing measurement.
Removing the configuration restores ordinary rejection.
Using a language parser avoids maintaining another C# grammar in regex.
The fixed record avoids a framework without a present consumer.
The panel accepted this bounded decision, subject to normal shipping protections.
