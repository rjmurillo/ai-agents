# ADR Debate Log: ADR-069 The Curated Context Corpus IS the Product

## Summary

- **Rounds**: 2 of 10
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

### Claims Checked

| Claim | Result |
|---|---|
| #7468 to #7472 closed 2026-11-20 between 06:29Z and 06:47Z | VERIFIED (`gh issue view`) |
| PR #7475 closed unmerged | VERIFIED (`gh pr view`) |
| PR #7489 merge commit `bf257a142` is on main at `15c13340a` (2026-11-20) | VERIFIED (`git merge-base --is-ancestor`) |
| Cited script paths exist | VERIFIED (`git ls-files`) |
| `check_adr_lifecycle.py` passes with no new violations | VERIFIED (153 violations across 123 records, none outside the baseline, 2026-11-20 at `15c13340a`) |

## Next Steps

This debate closed at round 2 with consensus. Edits made after that vote are debated in `.project-toolkit/critique/ADR-069-debate-log-2.md`.
