# ADR Debate Log: ADR-127 Workflow Skills Are Script Drivers, and Evals Gate Every Skill Rewrite

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: none
- **Outcome**: Consensus (2 Accept, 4 Disagree-and-Commit, 4 dissents recorded)
- **Final Status**: accepted
- **Panel**: full six seats. The record defines an executable gate, so the AGENTS.md trigger applies.
- **Claims ledger**: `.project-toolkit/critique/ADR-127-claims-ledger.md` (50 rows)
- **Date**: 2026-11-25

## Pre-panel gates

| Gate | Result |
|---|---|
| Claims ledger | VERIFIED. 27 rows at the refuting seat, 32 at panel start, 50 after round 2. |
| Refuting seat | Ran once (`analyst`, Haiku). 25 rows confirmed, 2 not reproduced without a shell. One finding outside the ledger: a citation to a spec file that is not in this tree. Fixed before the panel. |
| Documentation accuracy | Phase 4 ran once (Sonnet). 7 findings, 2 High. Fixed before the panel. |
| Self-consistency | FAILED on the first draft. The panel found three conflicts the author's pass missed. Re-run VERIFIED on the round 1 revision. |

The two High documentation findings changed the decision.
The draft pointed the eval at the template. The runner would have fed raw partial tags and skipped `references/`.
The draft also called the grade deterministic. It is a label match on a sampled model reply.

## Phase 0: related work

- Issue search on four queries found no open issue or PR on this topic (2026-11-25).
- Closed and related: #6579 (validation-gated skill evolution), #6657 (map, GPS, or hybrid skill design), #6290 (route eval scoring).
- ADR-057's 2026-07-22 amendment keeps eval enforcement advisory. It records 108 commits touching eval-scoped prompts against 1 with evidence.
- A `ship` and `push-pr` design draft sits unmerged on branch `refactor/ship-push-pr-pr-creation`. It carries three open owner decisions.

## Round 1 Summary

### Positions before changes

| Agent | Position | Blocking concerns |
|---|---|---|
| architect | Block | Lifecycle gate red (review date in frontmatter only). ADR-057 listed as kept while decision 9 contradicted its text. |
| critic | Block | The gate cannot see a rewrite regress. The scenario freeze could not be checked. |
| independent-thinker | Block | Vacuous baseline. Freeze against retire inside decision 7. |
| security | Block | Result lines could be forged by a newline in a value. The grant rationale rested on argparse alone. |
| analyst | Block | The gate passes at 0 to 0. No scenario floor. |
| high-level-advisor | Block | The gate is hollow for `ship`. Reviewer-only enforcement has a 108 to 1 record. |

### Key Issues Addressed

- **Hollow gate (4 seats, P0).** All 8 `ship` scenarios test steps that move into scripts.
  New result-line scenarios would fail on the prose base. A failing base cannot regress in the runner.
- **Freeze against retire (3 seats).** Scenarios were frozen at the first scored run, yet retirable in the rewrite.
- **Result-line forgery (security, P0).** A PR title holding a newline and `NEXT:` could forge a control line.
- **Grant rationale (security, P0).** "Argparse rejects unknown flags" does not bound values, paths, or abbreviations.
- **ADR-057 (architect, P0).** ADR-057 says "Do not add a new blocking gate". The draft called ADR-057 kept.
- **Lifecycle gate (architect, P0).** `check_adr_lifecycle.py` reported `review-by-prose-date: 12 -> 13`.
- **Kind collision (architect, critic).** A two-value "kind" collided with ADR-110's `metadata.capability.kind`.
- **Trigger mismatch (architect, critic, analyst).** "Rewrite" was defined by intent. Decision 9 gated "each changed driver".
- **Misread evidence (independent-thinker).** The gstack call figure is planned against actual with a driver present.
- **Path (critic).** 17 templates have no rendered file under `src/claude/skills/`.
- **No exit (high-level-advisor, architect).** No stop signal, no measure of success, no reversibility view.

### Major Changes Made

- Decision 1 declares `metadata.shape` with a mechanical predicate, separate from ADR-110.
- Decision 3 adds argument hardening and a grant that names each script.
- Decision 4 adds single-line values, a declared reason vocabulary, codes 1 to 4 only, and a missing-terminal-line rule.
- Decision 6 has a script verify the brief hash and the reply's commit.
- Decision 7 defines one trigger, a floor of 8 scenarios with 6 passing on base, shape-neutral scenarios, and an after-side floor.
  Retirement moves into the scenario commit. Every run's output is committed.
- Decision 8 adds tests for forged lines, caps, option injection, and call budget.
- Decision 9 has the check recompute the verdict and verify four identities. It admits the residual forgery risk.
  The pilot may merge on reviewer enforcement. No second gated change merges before the check.
  The check's change amends ADR-057 through `adr-review`.
- Decisions 12 and 13 add the pilot, its measures, stop signals, and reversibility.
- Context rewords the gstack figure. Caps cite their sources and are marked provisional.

### Feedback not incorporated, with reasons

| Feedback | Seat | Why not |
|---|---|---|
| Split the record into shape and gate | architect | The seat accepted one record if ADR-057 is amended with the check. Decision 9 commits to that. |
| Make the pilot a gate on starting other threads | high-level-advisor | The owner's plan starts threads after the audit. The record puts the wait on merge, not on start. Recorded as dissent and put to the owner. |
| Add "the locator runs `python3 -I`" | security | ADR-121 owns the locator text. The seat did not hold it as blocking. |
| A rule that retiring every scenario fails | high-level-advisor | The 6-of-8 base-passing floor already forces carried scenarios. The seat agreed. |

### Agent Positions after round 1

| Agent | Position |
|---|---|
| architect | Accept |
| critic | Disagree-and-Commit |
| independent-thinker | Disagree-and-Commit |
| security | Disagree-and-Commit |
| analyst | Disagree-and-Commit |
| high-level-advisor | Disagree-and-Commit |

## Round 2 Summary

Round 1 reached consensus. The seats also named small factual and wording defects.
Fixing them changed the text, so the changed lines went back for a vote.

### Key Issues Addressed

- The runner already records the model. "Records none of the four" was wrong by one (analyst).
- A script could hide a consequential-tier action from ADR-112's command-text deny rules (security).
- A moving `origin/main` could change the carried set after the freeze (critic).
- A trivial skill edit could reopen rerun-until-green (analyst).
- The after-side floor lives outside the runner (independent-thinker).
- The 30 percent bar had no method and no source (high-level-advisor, independent-thinker).
- An absence claim about gstack was unscoped (independent-thinker).
- Three ledger rows cited the wrong lines (critic, analyst).

### Major Changes Made

- Decision 3 item 8: a script never runs a consequential-tier action under ADR-112.
- Decision 7: the base is the commit the first run records. At most three first runs per change.
  The reviewer reads the after-side floor until the check lands. Gap-audit rows carry stable ids.
- Decision 9: "The runner records the model today and none of the other three."
- Decision 12: tool calls are the median of three clean runs. The 30 percent bar is labeled provisional.
- Ledger rows 48 to 50 added. Rows 15, 38, and 42 corrected.

### Agent Positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Condition: this log lands in the same change. It does. |
| critic | Disagree-and-Commit | See dissent 1. |
| independent-thinker | Disagree-and-Commit | See dissent 2. |
| security | Accept | Open note: `PYTHONPATH` is not named in decision 3 item 6. |
| analyst | Disagree-and-Commit | See dissent 3. |
| high-level-advisor | Disagree-and-Commit | See dissent 4. |

## Correction after the round 2 vote

Setting `status: accepted` armed the `cited-paths-exist` lifecycle check.
It rejected two gstack file paths cited in decision 4 item 9, because no such file is tracked here.
The sentence now points to audit rule B2, which holds the same two citations.
No rule, number, or decision changed. The seats voted on the rule, not on the citation form.
`check_adr_lifecycle.py` passes after the change.

## Dissent recorded

1. **critic.** The pilot is the hardest case and gets the weakest check.
   All 8 `ship` scenarios retire. The author writes the new ones. A reviewer reads the after-side floor by hand.
2. **independent-thinker.** The floor of 8 scenarios rests on an analogy to ADR-111 rule 2.
   No measurement from this repository supports it.
3. **analyst.** A carried scenario that falls from 3 of 3 to 2 of 3 still passes.
   The gate has no after-side floor for carried scenarios.
4. **high-level-advisor.** Fix threads start before the pilot reports.
   If the pilot misses the 30 percent bar, that parallel work is sunk cost, and sunk cost argues against stopping.

## Strategic review (high-level-advisor)

| Check | Round 1 | After revision |
|---|---|---|
| Chesterton's Fence | FAIL | Addressed: Historical Rationale states what prose does better. |
| Path Dependence | FAIL | Addressed: decision 13. |
| Core vs Context | PASS | PASS |
| Second-System Effect | FAIL | Mitigated, not removed: decision 12 pilot and stop signals. Dissent 4 stands. |

## Gate escapes

A gate escape is a panel finding the pre-panel gates should have caught.

| Escape | Found by |
|---|---|
| Ledger row 1 verified a quote's bytes, not its meaning. The reading was backwards. | independent-thinker |
| Ledger row 18 verified one ADR-057 quote and missed the sentence beside it that forbids a blocking gate. | architect, analyst |
| Self-consistency was marked VERIFIED while decision 7 contradicted itself. | critic, independent-thinker, architect |
| Row 14 verified the eval command on `ship` only. The path fails for 17 templates. | critic |
| The ledger's gate table omitted `check_adr_lifecycle.py`, which failed. | architect |
| The argparse grant claim had no ledger row. | security |

Six escapes in one record. The author's self-consistency pass is the weakest of the pre-panel gates here.

## Not verified by the panel

- Ledger rows 34, 37, 46, and 50 cite the gstack clone. Only the independent-thinker seat read it.
- No eval was run. Row 14 and row 45 are dry-run outputs.
- No seat checked how the frontmatter validators treat an unknown `metadata.shape` key. The Impact table defers that to the pilot.

## Next Steps

1. Write the gap audit with a stable id per row.
2. Put the three open `ship` decisions and dissent 4 to the owner.
3. Run the `ship` and `push-pr` pilot.
4. Land the decision 9 check with the ADR-057 amendment before a second gated change merges.
