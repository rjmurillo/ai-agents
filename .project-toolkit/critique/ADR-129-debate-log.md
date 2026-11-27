# ADR Debate Log: ADR-129 An Always-On Core Rule, Admitted by Eval

**ADR**: `.project-toolkit/architecture/ADR-129-always-on-core-rule-admitted-by-eval.md`
**Claims ledger**: `.project-toolkit/critique/ADR-129-claims-ledger.md` (82 rows)
**Companion log**: `.project-toolkit/critique/ADR-105-amendment-2026-11-26-debate-log.md`
**Date**: 2026-11-26
**Panel**: full panel (architect, critic, independent-thinker, security, analyst, high-level-advisor). The change edits always-on rule membership, which pre-PR gates read.

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: none
- **Outcome**: Consensus. Six of six seats voted Accept in round 2.
- **Final Status**: accepted

## Mechanism and its limits

Each seat ran as a separate agent on `claude-sonnet-5-5` with fresh context. No seat saw another seat's report.

Round 1 ran three seats, not six: architect, critic and independent-thinker. All three asked for the same split, so the orchestrating agent revised the draft before the other three seats ran. Security, analyst and high-level-advisor first read revision 2. They never reviewed revision 1.

The analyst and security seats had no shell. They used file reads and searches, so they could not rerun `wc` or `git diff`.

Round 2 ran in two batches of three. The first batch raised only P2 items. Four sentences were added before the second batch read the record. The analyst then raised one P1 on wording. It was fixed after the vote, and no seat re-voted on that fix. The exact change is in the round 2 table.

## Pre-panel gates

| Gate | Result |
|---|---|
| Claims ledger | 58 rows before the panel, 82 after |
| Documentation accuracy | Six findings, all corrected before round 1 |
| Self-consistency | Run with the documentation accuracy pass; its contradictions are among the six findings above |
| Refuting seat (`analyst`, haiku) | Refuted the first wording of ledger row 23. Corrected. The seat was not rerun |

## Phase 0: Related work checked

| Item | State | Relevance |
|---|---|---|
| PR #7730 | Open | The change this record decides |
| PR #7724 | Merged | The earlier context caps change |
| Issue #7502 | Open | Tracks scenario coverage for uncovered rules |
| Issue #7580 | Open | ADR-127 rollout epic |
| Issues #5404, #5535 | Closed | Origin of the ADR-105 contract and its precedence order |

The Phase 0 analyst seat had no GitHub tools. The orchestrating agent ran the issue search with the repo's `list_issues.py` script.

## Round 1 Summary

### Key Issues Addressed

- All three seats: the tiered skill preambles were unbuilt and unmeasured, and did not belong in a binding Decision item.
- independent-thinker and critic: "passed" overstated a null. Six sign runs can reject a cut only at 6 of 6.
- architect and critic: Task Intent missed a gate line with no recorded waiver.
- critic and independent-thinker: the evidence is exploratory. The core was tuned on the scored scenarios.
- critic: five sections left the always-on set with no scenario, and the record did not own that.
- architect: `builder-ethos.md` still said "Always loaded", and the index row was malformed.

### Major Changes Made

- Decision item 4 (tiered preambles) became a non-binding section, `## Direction, Not Decided: Skill Preamble Tiers`. The record was renamed.
- Decision item 2 now says "did not reject", cites the mean margins and states the power limit.
- Decision item 2 gained a general exception rule and a named Task Intent exception with scope, reason and reversal trigger.
- Decision item 2 now states that the gate is one-sided. Trade-offs and Negative name the five sections as losses with no end date.
- A "Decision drivers, in priority order" subsection and three alternatives were added.
- Negative gained the exploratory limits, the 75 files and the rule-author gap. Positive gained the `.py`, `.cs` and `.ps1` ceiling drop.
- `templates/rules/builder-ethos.md` lost the "Always loaded" sentence. One `decision-question` reference lost a stale label.

### Agent Positions

| Agent | Position | Main finding |
|---|---|---|
| architect | Disagree-and-Commit | Split item 4; record the gate waiver |
| critic | Disagree-and-Commit | Evidence is exploratory; removal bears no burden |
| independent-thinker | Disagree-and-Commit | "Passed" overstates a null; split item 4 |
| security | Not run in round 1 | First read revision 2 |
| analyst | Not run in round 1 | First read revision 2 |
| high-level-advisor | Not run in round 1 | First read revision 2 |

### Next Steps

Run all six seats on revision 2.

## Round 2 Summary

### Key Issues Addressed

| Seat | Priority | Finding | Disposition |
|---|---|---|---|
| analyst | P1 | The record said four gate lines were written before the results. The report registers three; the sign rule dates from 2026-08-03 and was applied after the runs | Fixed after the vote. Decision item 2 now says so in three sentences. Ledger rows 78 and 79 |
| critic | P2 | The Task Intent reversal had no deadline | Fixed. The review date is the deadline |
| architect | P2 | Neither record said why this is an amendment and not a superseding record | Fixed in Decision item 4 and in the amendment |
| security | Low | Unattended Runs and Ownership carry security-adjacent text that leaves the always-on set | Fixed. Negative names both and what still loads |
| analyst | P2 | The Task Intent exception did not cite its sign count | Fixed. 0 to 3 with 3 ties, p=0.250 |
| high-level-advisor | P2 | The share of hourly token use is not stated | Fixed. Positive says it is not measured |
| high-level-advisor | P2 | "One revert" covers only the whole change | Fixed. Implementation Notes names the ratchet limit |
| analyst | P2 | `builder-ethos.md` line 114 called the Precedence Stack "the always-on summary" | Fixed in the template, its fixture and generated copies |
| analyst | P2 | Ledger header and missing rows | Fixed. Rows 78 to 82 added |
| analyst | P2 | `voice.md` line 21 says "Always-on, no exceptions" | Not changed. It names a tier inside the rule, not the rule's load scope |
| analyst | P2 | "75 files at d3c2d82df9" will not match the final change | Not changed. The claim names its commit |
| high-level-advisor | P2 | No note on why Ownership and the banned word list were first added | Not resolved. No history search was run |
| independent-thinker | P2 | Nothing in the tree dates the gate lines | Partly resolved. The record now cites the report as the source of that claim |

### Deferred P1 items, with justification

- Scenarios for the five unmeasured sections. Not written in this change. Issue #7502 tracks them, and the review date of 2027-02-26 covers them. New eval runs compete for the quota this change exists to save. The critic and the high-level-advisor judged the deferral justified.
- A rerun of the shipped core on the `voice`, `builder-ethos` and `universal` pools, and the `gpt-5.6-sol` arm. Not run, for the same reason. Both are listed under Negative.

### Major Changes Made

- Three sentences on gate provenance in Decision item 2.
- One paragraph on amendment against supersession in Decision item 4.
- One Negative bullet on security-adjacent text.
- Small additions named in the table above.

### Agent Positions

| Agent | Position | Note |
|---|---|---|
| architect | Accept | Every round 1 finding is fixed in the files |
| critic | Accept | Six findings resolved; both deferrals justified |
| independent-thinker | Accept | Still holds that a one-sided gate is a weak spot; treats it as a recorded decision |
| security | Accept | Voted "approve with two low findings"; no always-on security rule is lost |
| analyst | Accept | Verified fifteen claims; the P1 is a precision fix, not a block |
| high-level-advisor | Accept | Verdict: ship now; more runs would spend the quota the change protects |

### Dissent kept on record

- independent-thinker: the gate protects measured text and lets unmeasured text leave. The record states this and the owner decides it, but it stays a weak spot.
- security: an unattended agent with no skill loaded no longer reads "halt only that branch" for Ask First items. Risk scored 3 of 10.

### Strategic review

| Lens | Assessment |
|---|---|
| Chesterton's Fence | PASS with a gap. ADR-105's reason for an always-on contract is kept. No one traced why Ownership and the banned word list were first added |
| Path dependence | PASS. Rollback is one revert. Putting one rule back alone must fit the lowered ceilings |
| Core against context | Not applicable |
| Second-system effect | PASS. The unbuilt tier design was removed from the Decision |

### Gate escapes

None. No seat in either round reported a factual finding that duplicated a VERIFIED ledger row. In round 1 the critic marked "partials may include partials" as unverified; ledger row 47 already cited the code, and the claim held.

### Noticed outside this record

`templates/rules/core.md` line 33 names `security.md` as a source of mandatory policy. No rule of that name exists under `templates/rules/`. The same sentence stood in `builder-ethos.md` at 8104f11665 (2026-11-26), so this change did not add it. It is recorded here for the owner's decision.

### Next Steps

None for this debate. The preamble tiers need their own record, with a byte ceiling per tier, the tier of each template, an eval threshold, a test for restated `core` text and a render choice.

## Amendment 2026-11-27: scoped exception for the measured candidate

**Trigger**: CodeRabbit review of PR 7730 found that the voice and builder-ethos pools measured the seven-clause candidate, not the shipped `core`.
**Change**: ADR-129 section 2 gains `Exception: measured candidate differs from shipped core`, with scope, reason and a reversal trigger. No decision text changes.
**Panel verdicts**: Unavailable. No independent architect or critic reviewed this amendment.

- Architecture check (author): The exception names its scope, evidence gap, and reversal trigger.
- Critic check (author): The candidate scores cannot certify the shipped text. The scheduled rerun decides whether the cut stands.

No paid eval was run for this amendment. The gap stays open until the rerun.

## Amendment 2026-11-27: Unattended Runs status consistency

**Trigger**: CodeRabbit review of PR 7730 found two inconsistent answers for Unattended Runs: the shipped `core` included it, while Trade-offs and Negative listed it among sections leaving the always-on set. The same review found that the shortened rule text dropped the Ask First branch halt.

**Change**: ADR-129 now names Unattended Runs as a scoped exception with scope, reason, and reversal trigger. The unmeasured-section counts name the four sections that still leave the always-on set. The risk note keeps the security-adjacent classification and states that the branch halt remains in `core`. This amends the record's consistency, not the eval gate.

**Reduced panel**:

| Seat | Verdict | Evidence |
|---|---|---|
| architect | Accept | The exception has the same scope, reason, and reversal shape as the two exceptions already in the record. Decision item 1 now names all four sections in the shipped rule. |
| critic | Accept with note | The exception is argument-backed, not measured. That is explicit in the record, and issue #7502 plus the review date bound the reversal. |

**Dissent kept on record**: The critic note is the dissent. Unmeasured admission is a deliberate exception, not evidence of behavior lift.

Amendment implementation note: the panel accepted the compressed wording after the byte-reserve check.

Final byte-reserve check: reduced panel accepted the one-character compression.
