# ADR Debate Log: ADR-069 The Curated Context Corpus IS the Product

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: none
- **Outcome**: Consensus
- **Final Status**: accepted

ADR-069 merged on 2026-05-10 (PR #1869) as `proposed` and never had a debate.
Issue #702 flagged it as ready for review on 2026-06-17 and closed without one.
The owner asked for the record to move to accepted on panel consensus.
The change is prose and frontmatter only and touches no enforcement.
So the reduced panel (architect and critic) ran.

The five follow-up issues named in Decision item 4 were filed on 2026-11-20.
They are #7468, #7469, #7470, #7471, and #7472.
All five closed the same day with research verdicts, before round 1 began.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Needs-revision |
| critic | Needs-revision |

### Key Issues Addressed

- Both found the text called the five issues open work, but all five had closed.
- The `implemented` paragraph (draft line 166) kept `implemented: false` until each issue had an outcome. That condition was already met.
- The critic found the `implemented` paragraph misquoted ADR-073's frontmatter schema ("flips true at first merged change").
- The architect asked for `date` to follow ADR-073's schema ("last updated").
- Both flagged an unanchored count in "Why Change Now". The critic flagged a banned word in the Alternatives table.
- Both corrected a brief premise: a `## Status` section is optional for accepted records. A bare "Accepted." fails `prose-frontmatter-agree`.

### Split On `implemented`

- **architect**: true. The record's own rule is met.
- **critic**: false. ADR-073's schema line is the rule, and PR #7475 closed unmerged.

## Round 2 Summary

### Major Changes Made

- Frontmatter: `status: accepted`, `date: 2026-11-20`, `implemented: true`.
- Added a `## Status` section whose first sentence stands alone.
- Decision item 4 now says all five issues closed on 2026-11-20.
- Implementation Notes lists each issue's outcome, with paths checked by `git ls-files`.
- The `implemented` paragraph cites ADR-073's rule and the Phase 2 backfill artifact test.
- The "Why Change Now" count now says "(as of 2026-05-02)". The banned word was replaced.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Disagree-and-Commit |

### Resolution Of The Split

The critic changed to true for two reasons:

- The Phase 2 backfill log (`.project-toolkit/critique/ADR-073-phase2-backfill-debate-log.md`) chose an artifact test over ADR-073's literal rule. It recorded that choice on purpose.
- Its ADR-069 row was judged before any follow-up issue existed.

The architect added a further point. "First merged change" was already met by PR #1869 on 2026-05-10. So the literal reading cannot explain why the field is false.

### Findings Applied After The Votes

- architect P2 and critic P1: the closing sentence overstated the merged PRs. PR #7482 cites ADR-069 only to exclude it. The paragraph now rests on the artifact test alone.
- critic P1: Implementation Notes said no gate was associated. It now credits follow-up PR #7489.
- critic P0: this log must exist before the commit. It ships in the same commit as the status change.
- Editorial: the Decision opener now ends with a period, so the generated index summary reads as a sentence.

### Claims Checked

| Claim | Result |
|---|---|
| #7468 to #7472 closed 2026-11-20 between 06:29Z and 06:47Z | VERIFIED (`gh issue view`) |
| PR #7475 closed unmerged | VERIFIED (`gh pr view`) |
| PR #7489 merge commit `bf257a142` is on main at `15c13340a` (2026-11-20) | VERIFIED (`git merge-base --is-ancestor`) |
| Cited script paths exist | VERIFIED (`git ls-files`) |
| `check_adr_lifecycle.py` passes with no new violations | VERIFIED (153 violations across 123 records, none outside the baseline, 2026-11-20 at `15c13340a`) |

## Round 3 Summary

The pre-merge `/review` ran after round 2 and changed the ADR text, so the panel voted again on the text that ships.

### Key Issues Addressed

- `decision-rigor` found that the acceptance cited only supporting evidence. The #7471 verdict rests on the 2026-09-28 control ablation (`.project-toolkit/metrics/control-ablation-v0.7.0.md`), which returned `MIXED`.
- `decision-rigor` found that `true` routes any later material change to supersession, and the text did not say so.
- `analyst` and `correctness` found that the Context section still named closed #7468 as the inventory owner.
- `analyst` found the `implemented` paragraph claimed more than the verdicts said.
- `decision-rigor` found 14 live statements outside this record (2026-11-20, at `15c13340a`) that still called ADR-069 proposed. One of them failed `citation_reverse_pass.py`.

### Major Changes Made

- Implementation Notes item 4 cites the `MIXED` ablation. It says the record is accepted as a principle and its effect is unmeasured.
- A Revisit condition points at the research-frontier Program 1 falsifiable milestone.
- The `implemented` paragraph says "recorded verdict" and names the supersession consequence.
- The Context section points at Implementation Notes item 1 for the current inventory.
- The same change updates the stale status text in three skill templates, their generated copies, one skill reference, one docs page, and the roadmap.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Disagree-and-Commit |

### Dissent

The critic's recorded reservation: `implemented: true` means any later material change needs a superseding record. The principle's effect is unmeasured, so a negative Program 1 result will need a new record, not an amendment.

### Findings Applied After The Votes

- critic P2: the Revisit condition names the template path.
- architect P2: the ablation sentence says "accepted 9 of 15 tasks durably", matching the metric.
- architect P1 (the log is missing) was already resolved. This log was committed with the status change.

## Corrections From Review Round 2

The pre-merge `/review` round 2 found two factual errors in the ADR text. Both are corrections, not changes to the decision, so the panel did not vote again.

- `decision-rigor`: the ablation counts 15 runs per arm (5 tasks, 3 repeats each), not 15 tasks. Implementation Notes item 4 now says "runs".
- `correctness`: the Context catalog is called a 2026-05-02 snapshot, but PR #5887 (2026-09-22) moved one of its paths. The Context section now names that move.
- `decision-rigor` also found that three skill `reverify.json` checks still asserted `status: proposed`. They now assert `status: accepted`, and `bootstrap_drift.py check` passes for those rows.

## Next Steps

- `.project-toolkit/architecture/ADR-107-canonical-skill-contracts-and-harness-projections.md` (Related Decisions) still calls ADR-069 `proposed`. Editing ADR-107 needs its own debate log, so this change leaves it. The PR for this change names it as an open follow-up.
