# ADR Debate Log: ADR-073 Amendment 2026-11-26, Proposed Records Need review-by

## Summary

- **Rounds**: 1 of 10 (Phase 1 independent review, then one convergence vote on the revised text)
- **Outcome**: Consensus. Convergence vote on the revised text: four Accept, two Disagree-and-Commit. No P0 in either round.
- **Final Status**: accepted. ADR-073 frontmatter stays `status: accepted`. The amendment stands with the Phase 3 edits below.
- **Panel**: full six-role panel. The amendment changes executable enforcement in `scripts/validation/check_adr_lifecycle.py`: a new check and a zero-tolerance set.
- **Review independence**: six separate subagent passes, one model family (Sonnet). Each seat got the artifact and the diff, not the author's reasoning. Treat the votes as six lenses of one family, not six independent reviewers.
- **Artifact reviewed**: `.project-toolkit/architecture/ADR-073-adr-lifecycle-frontmatter.md`, section "Amendment 2026-11-26: proposed records need a review-by date", the schema comment for `review-by`, and the last sentence of the 2026-10-13 amendment.
- **Claims ledger**: `.project-toolkit/critique/ADR-073-proposed-review-by-claims-ledger.md`.
- **Ground truth**: Phase 1 ran on branch `feat/7638-adr-review-by-ratchet` against `origin/main` at `ffc759356` (2026-11-26). The convergence vote ran after the rebase onto `8f4f1b981` (2026-11-26), which holds #7636 and #7637.
- **Owner decision under review**: issue #7638. Require `review-by` on every `proposed` record, ratcheted. Make `review-by-past-due` block or open a follow-up. The owner allowed either; the amendment chose block.

## Phase 0: Related Work

| Item | State | Relevance |
|---|---|---|
| #7638 | open | The work item. |
| #7636 | merged in PR #7691 | Flipped 17 shipped ADRs out of `proposed`, including ADR-077 with `review-by: null`. Emptied the `implemented-implies-decided` and `review-by-past-due` baselines. |
| #7637 | merged in PR #7692 | Retired six dead `proposed` ADRs and accepted ADR-022. |
| #5193 | closed | Added the three `review-by` checks this amendment extends. |
| #5273 | closed | `(check, path)` ratchet keys, which let a new check enter with its records baselined. |

## Phase 1: Independent Reviews

### architect: Disagree-and-Commit

Check names, `--write-baseline` behavior, and the config error for a live baseline match the code. P1: the debate log the ADR cites did not exist yet (resolved by this file). P1: the 21 grandfathered records never expire; state it. P2: the base-ref baseline may still list a zero-tolerance check, and that transition path is undocumented in the ADR (it is documented in `_zero_tolerance_problem`). P2: the 2026-10-13 text and the Phase 1 scope line now read as conflicting.

### critic: Disagree-and-Commit

P1: the amendment did not say `implemented-implies-decided` becomes zero-tolerance after #7636. P1: the ratchet does not drain the 21. P2: no gate-level test for a quoted date or a mixed-case status on the new check. Done-when items 3 and 4 met; 42 selected tests passed.

### independent-thinker: Disagree-and-Commit

P1: moving the date clears a past-due record with no review (date laundering). P1: every future date is a scheduled block on unrelated branches. P1: the ratchet stops growth but does not drain. P2: tension with the 2026-10-13 rule against invented dates. Strongest counter-argument: a scheduled follow-up issue surfaces the miss at no cost to unrelated authors. Record it as a consequence; do not reverse the owner's choice.

### security: Disagree-and-Commit

No bypass found. `_excess` treats every zero-tolerance violation as excess whatever the baseline holds. The live-baseline path fails closed with exit 2. `recordable` empties zero-tolerance entries on write and in the base-ref comparison. P1: ADR-077 makes the gate red until #7636 lands. P2: a near-dated new record can seed a block. P2: the clock reads local time (refuted below).

### analyst: Disagree-and-Commit

Claims 1, 3, 4, 5, 6 VERIFIED. Claim 2 partly verified: the seat had no git access to confirm ADR-077 sat in the baseline about two months. The author verified it: `origin/main:scripts/validation/adr_lifecycle_baseline.json` lists ADR-077 under `review-by-past-due`, and ADR-073 line 194 records it entering on 2026-10-13.

### high-level-advisor: Disagree-and-Commit

P1: a date tells a reader when a record is due, not whether it binds; `implemented-implies-decided` carries that, so do not close #7638 until it is zero-tolerance. P1: blocking on the clock is the wrong default; prefer a follow-up. P1: date laundering is the largest residual risk. Recommended waiting on zero-tolerance past-due.

## Phase 2: Consolidation

| Theme | Seats | Disposition |
|---|---|---|
| `implemented-implies-decided` flip not stated | critic, high-level-advisor | Accepted. Amendment now states it joins `ZERO_TOLERANCE_CHECKS` once #7636 empties its baseline. The PR rebases on #7636 before that flip. |
| 21 grandfathered records never drain | architect, critic, independent-thinker, high-level-advisor | Accepted as a stated limit. Draining needs a decision date per record, which is the owner's call, not the gate's. |
| Date laundering | independent-thinker, high-level-advisor | Accepted as a stated limit. A horizon cap or reason field would be a new schema field, outside #7638. |
| Block vs follow-up | independent-thinker, high-level-advisor | The request allowed either. The author chose block without consulting the owner, per the issue text "rather than sitting at baseline". The counter-argument is recorded for the owner. |
| Conflict with 2026-10-13 and Phase 1 scope text | architect, independent-thinker | Accepted. Amendment states it narrows the 2026-10-13 rule and why a decision date is not an invented revisit date. |
| Seeding a block with a near date | security | Accepted as a stated limit. |
| Clock reads local time | security | Dismissed. `_utc_today` returns `datetime.now(UTC).date()`. |
| Quoted date, mixed-case status tests | critic | Accepted. Tests added. |
| Debate log missing | architect | Resolved by this file. |

## Phase 3: Resolution

Edits made to the amendment after Phase 1: the `implemented-implies-decided` sentence, the narrowing paragraph, and the "Known limits, recorded for the owner's decision" list. Two tests added to `tests/validation/test_check_adr_lifecycle.py`.

## Phase 4: Convergence

Phase 1 votes: six of six Disagree-and-Commit, no P0. Five seats asked for the limits to be recorded. The high-level-advisor seat also advised waiting on zero-tolerance past-due; the owner's request names block as an allowed outcome, so the amendment keeps it and records the dissent.

After #7636 and #7637 merged, the branch was rebased. `implemented-implies-decided` joined `ZERO_TOLERANCE_CHECKS`, and the undated set fell from 21 to 3. Each seat then voted on the revised text and the post-rebase diff.

| Agent | Position | Note |
|-------|----------|------|
| architect | Accept | Both Phase 1 P1s closed. P2: the issue cites a different gate SHA; counts match. |
| critic | Accept | Ran the gate and the test file; all passed. |
| independent-thinker | Disagree-and-Commit | Still prefers a follow-up issue to a hard block. |
| security | Accept | No bypass of the new zero-tolerance member. Asked for a test pinning membership; `test_implemented_implies_decided_is_zero_tolerance` does. |
| analyst | Accept | Verified the set membership and the three remaining records. |
| high-level-advisor | Disagree-and-Commit | Phase 1 P1 met. Still prefers a follow-up issue. |

### Dissent recorded

- independent-thinker, high-level-advisor: a scheduled follow-up issue would cost unrelated authors less than a block. The author chose block; the owner has not ruled and can reverse it.
- independent-thinker, high-level-advisor: no guard stops a date being moved without a review.
- architect, critic: the ratchet does not drain the grandfathered records. Three remain: ADR-065, ADR-087, ADR-124.

## Strategic Review

- Chesterton's Fence: PASS. The 2026-10-13 amendment's ratcheting of past-due is read and its cost (ADR-077 held two months) is the reason for the change.
- Path Dependence: PASS. Reversal is one line: remove the name from `ZERO_TOLERANCE_CHECKS` and regenerate the baseline.
- Core vs Context: N/A.
- Second-System Effect: PASS. One check and one set; no new schema field.
