# ADR Debate Log 3: ADR-125 Owner-Comment Approval Retired

## Summary

- **Prior debate log**: [2](ADR-125-debate-log-2.md), closed.
- **Rounds**: 1.
- **Panel**: full, six seats. The change removes an executable verifier.
- **Claims ledger**: [ADR-125 claims ledger](ADR-125-claims-ledger.md), last section.

## Change under review

The owner directed on 2026-11-24 that the owner-comment approval protocol be removed.
Branch `chore/evict-owner-approval` deletes the verifier, its test, and the procedure page.
The amendment "Owner-comment approval retired" records that change at `6bbb4fc52e`.

## Round 1

All six seats voted Disagree-and-Commit. Each accepted the owner's direction.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Critic, independent-thinker, security | P1 | "No person can approve past the gate" overstated the control; the gate now runs the branch's own assessor and config | Consequences now name the self-attesting gate, the review control, and no trusted CI run |
| Architect, critic, analyst, advisor | P1/P2 | Original Decision and Consequences, first amendment item 7, and line 119 read as live | Retirement pointers added at each spot |
| Advisor | P1 | "Cleared shared-import and shorter-file drops on its own" contradicted 5 unadmitted rows | Why now says 69 of 74 rows |
| Advisor, independent-thinker | P1 | Escape hatch unclear | Change item 4 names a code fix or a reviewed rule with an ADR amendment; item 5 points to ADR-122's process |
| Analyst | P1 | Ledger cited `verdict.py:787-788`, the doc-accuracy branch | Now cites 717-718, the code-quality branch |
| Critic, independent-thinker | P2 | Alternatives missed a trusted-assessor run and a waiver file | Both added |
| Advisor | P2 | No revisit trigger; reversal named no commit | Two revisit triggers added; reversal names `8d7c067f1a` |
| Critic | P2 | Count with no SHA or date | Consequences anchor the rows at `0a101a596` (2026-11-24) |
| Analyst, critic | P2 | Owner quote is not in the tree | Ledger marks the row session-sourced |
| Architect | P1 | Debate log missing | This log |

## Deferred

- The title keeps "Require Exact Approval". Renaming churns every citation.
  The pointers under Decision, Alternatives, and Consequences carry the change. P2, deferred.
- A CODEOWNERS entry or CI check for `assess.py` and `.qualityrc.json` would enforce the review control.
  The ruleset disables code-owner review, so it would not bind today. Flagged for the owner, not added.
- `implemented: false` stays. The admissions are implemented, but status edits belong to the
  review that closes with consensus; no seat asked to flip it.

## Verdict

Consensus: six of six Disagree-and-Commit. All P1 findings were fixed in place.
The fixes narrow claims and add pointers; no decision changed, so no new round was opened.
The direction was the owner's, so no seat could block it; votes judged the record, not the choice.

## Post-consensus review edits

The `/review` run on `4d53aa61dc` re-read the fixed text with eleven axes.
Ten axes found the index row showed the pointer, not the decision; the pointer now follows item 1.
The correctness pass found two retired passages with no pointer; both now carry one.
Four axes noted the review control is unenforced; Consequences now say it is advisory.
No decision changed, so no new round was opened.

Round 2 of `/review` found one more retired line, on the verifier reading config, with no pointer.
It now carries one. No decision changed.

## PR #7538 review edit

Devin Review found the reversal line named only the verifier.
It now names all four pieces to restore. No decision changed.
