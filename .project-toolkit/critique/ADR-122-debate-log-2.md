# ADR Debate Log: ADR-122 item 10, change-scoped admissions for issue #7493

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: [`ADR-122-debate-log.md`](ADR-122-debate-log.md)
- **Outcome**: Consensus (6 Accept after round 3; round 1 had 1 Block, 4 Disagree-and-Commit, 1 Accept)
- **Final Status**: accepted (the amendment changes no ADR status)
- **Scope**: Decision item 10, its Status, Context, Rationale, Consequences, Reversibility, and Confirmation lines, and the frontmatter `review-by`.
- **Panel**: full six-agent panel. Item 10 changes executable enforcement in the scanner and the review adapter.
- **Claims ledger**: `.project-toolkit/critique/ADR-122-claims-ledger.md`, section "Item 10 (2026-11-20, issue #7493)". The refuting seat ran before round 1 and found 5 factual errors, then 1 more, all fixed before the panel.
- **Owner decisions**: D1 and D2, choice A each, recorded in issue #7493 comment 7050456436. The panel did not debate whether to waive. It reviewed how.

## Round 1 Summary

### Key Issues Addressed

- **Gate evasion (high-level-advisor P0, independent-thinker and security P2).** The scanner split each record path into directory and name so no literal started with `scripts/`. A comment said this avoided the vendor portability check.
- **Score-only pins (independent-thinker and critic P1).** Coupling is `10 - imports` and cohesion rounds `10 - loc/120 - 0.3*(defs-1)` to 0.1. An edit that swaps an import or moves a few lines keeps both scores, so "any later edit voids a record" was false.
- **Item 8 contradiction (analyst and architect P1).** Item 8 said a comparison reports `WARN` only with exactly one record. Item 10 lets a file carry two.
- **No removal step (high-level-advisor and independent-thinker P1, architect P2).** The records go inert after merge but ship in every scanner and adapter copy. Reversibility still said "no follow-up pull request removes them."
- **Silent directory skip (architect P1, security and independent-thinker P2).** The skip printed nothing and also caught type changes.
- **Revisit trigger (architect P1).** Item 10 adds the second record shape the Consequences named as a trigger, with no recorded outcome.
- **No rollback statement for item 10 (critic P1).**
- P2: assert on scanner values in the adapter; weak conformance control; run-only ledger rows; missing evidence-loss condition in the ADR's match rule; undisclosed empty-scan behavior; cohesion described as size only; stale lines 207, 236, and 133; title scope; no validity date.

### Major Changes Made

- Commit `80f5ca22c` (2026-11-20): plain path literals and a commented entry in `scripts/validation/vendor_portability_baseline.txt`, following the #4013 false-positive pattern; base and head blob pins on every record, checked by the scanner and the adapter; the directory skip prints `SKIPPED (directory)` and leaves type changes to scoring; an `isinstance` guard replaces the adapter assert.
- A test written in this round caught a real defect: `git rev-parse --end-of-options <rev>:<path>` echoes the option as an output line. The scanner now passes `--verify --quiet`.
- ADR text: item 8's one-record rule is scoped to parser records; item 10 cites item 8 for exits 10 and 11, states mixed-kind `UNKNOWN`, and says the marker `WARN` is not machine-checked; the revisit outcome and a new trigger are recorded; Reversibility commits a follow-up pull request; the stale lines, the cohesion description, and the match rule are corrected; Status carries a scope note instead of a title change.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Disagree-and-Commit. Four sentences contradict items 8 and 9, the trigger, or Reversibility; the directory skip belongs in its own item. |
| critic | Disagree-and-Commit. "Any later edit voids a record" is false; item 10 has no rollback. |
| independent-thinker | Disagree-and-Commit. Score-only pins admit a different body; the path split evades a gate and the records never expire. |
| security | Accept. No path turns a regression outside the eight records into `WARN` or `PASS`. P2: silent skip, path split, adapter assert. |
| analyst | Disagree-and-Commit. Item 8 contradicts item 10; run-only ledger rows. |
| high-level-advisor | Block. P0: the path split is gate evasion. P1: no removal step. |

## Round 2 Summary

### Key Issues Addressed

- Every seat re-checked its round-1 findings against `80f5ca22c` and the uncommitted ADR text.
- New P2s: the follow-up kept the item 10 matching code with no records (dead code); the record shape sentence and the item 10 table omitted the blob ids; the skip sentence missed the non-changed-only mode; a stale submodule mention in the `assess.py` docstring; the follow-up had no tracking anchor; the cited debate log did not yet exist.
- The fresh analyst seat blocked on four items: the dangling debate-log citation, no review-by date, a conformance control that asserted list inequality instead of calling the check, and four ledger rows without commands.

### Major Changes Made

- The follow-up pull request removes the item 10 matching code and adapter branch too. The directory skip stays.
- The item 10 table gains base and head blob columns. The record shape, skip, and docstring sentences are corrected. Issue #7493 anchors the follow-up.
- Frontmatter `review-by: 2026-12-20`, restated in item 10's prose as the lifecycle gate requires.
- Both conformance tests call one `_copies_agree` helper; the control drifts one blob and must fail.
- The four ledger rows carry commands. This log resolves the citation.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept, conditional on this log existing. Directory skip in Consequences accepted as debt. |
| critic | Accept. All six round-1 findings resolved. |
| independent-thinker | Accept. Marker `WARN` acknowledgement accepted as debt. |
| security | Accept. The new `rev-parse` and `hash-object` calls take an in-code path after an option terminator; a failed call returns no blob and admits nothing. |
| analyst | Block. Four items, listed above. |
| high-level-advisor | Accept. P0 and P1 resolved. |

## Round 3 Summary

### Key Issues Addressed

- The analyst re-checked its four round-2 items against the working tree.

### Agent Positions

| Agent | Position |
|-------|----------|
| analyst | Accept, conditional on this log existing in the commit. All four round-2 items resolved: review-by at frontmatter and prose, `_copies_agree` control, ledger commands. No new P0 or P1. |

### Next Steps

- Commit the ADR, ledger, and this log together.
- After #7493 merges, open the follow-up pull request that removes the item 10 records, matching code, adapter branch, config key, baseline entry, and `review-by` field.
- Recorded debt: the directory skip lives in Consequences, not its own Decision item; the marker does not name the admission or machine-check the `WARN` acknowledgement.
