# Retrospective: an adversarial pass refuted 19 of 36 agent-proposed rewrites

**Date**: 2026-09-07
**Scope**: Issue #5574 Stage 2 tail, PR #5647, branch `chore/5574-forgetful-stage2-tail`
**Failure mode classification**: #4, False completion markers, and #10, silent defaults. Both caught before shipping, by a verification stage rather than by review.

## What happened

Acceptance criterion 1 of #5574 requires `git grep -il forgetful` over nine trees
to return nothing. It matched 68 files. A classification workflow read all 51
authored sources (the other 17 are generated mirrors) and bucketed each one,
proposing 36 rewrites. A second, adversarial stage was told to refute each
proposal rather than agree with it.

It refuted 19 of 36. The 17 survivors shipped.

## The measurement

| Outcome | Count | Share |
|---|---|---|
| Rewrite proposed | 36 | |
| Rewrite refuted on inspection | 19 | 53% |
| Rewrite confirmed and shipped | 17 | 47% |

Refutation grounds. Several refutations cite more than one independent
ground, so each is counted once under its primary ground and the column sums
to 19.

| Primary ground | Count | Example |
|---|---|---|
| Replacement introduces an unsupported or false claim | 9 | Three book references gained an exclusivity the original never made |
| Miscited the line it quoted | 2 | Quoted a line number that is blank; the text was one line lower |
| Arithmetic or count wrong | 2 | A count the proposal called decisive was off by roughly 72 percent |
| Misread the gate it cited | 1 | Called a portability baseline "lower is better" in the wrong direction |
| Record misread as a live instruction | 1 | Provenance prose about the decommission itself |
| Would break the artifact | 1 | A replacement injected a word into an eval fixture's prompt |
| Replacement duplicates content already in the file | 1 | Restated a bullet the References section already carried |
| The instruction contradicted itself | 1 | Said "replace lines 414-418 with exactly these five lines", then supplied six |
| Wrong remedy: the target is dead code | 1 | A constant defined and never referenced; delete it rather than reword it |

## Impact

| Area | Severity | Effect |
|---|---|---|
| Agent instruction accuracy | High | Twelve authored surfaces named a server the harness can no longer reach, two of them untrusted-content preambles and two of them MCP tool grants |
| Trust in agent-proposed edits | High | 19 of 36 proposals were wrong, and every one of them cited a verbatim quote and a line number |
| Acceptance criterion integrity | Medium | AC1 cannot reach zero while the guards and frozen run records that must contain the token to do their job still match it |
| Retrospective accuracy | Medium | The grounds table first shipped summing to 15 against a stated 19, the defect class this campaign exists to remove |

## Root cause, five whys

1. Why were 19 proposals wrong? Each was written by an agent that had read the
   target file but not the things that constrain it.
2. Why did that not show up as low confidence? Because a proposal citing a
   verbatim quote and a line number reads as verified whether or not the quote
   is accurate.
3. Why is the quote sometimes inaccurate? Because reading a file to classify it
   and reading it to transcribe a line are different acts, and the first does
   not force the second.
4. Why did the classifier not catch its own error? Nothing in a single pass
   disagrees with it. A proposal is self-consistent by construction.
5. Why did the adversarial pass catch it? Because refuting requires re-opening
   the file, and its default verdict on uncertainty was REFUTED rather than
   CONFIRMED.

Root cause: **a self-consistent proposal carries no signal about its own
accuracy.** The only thing that separates a correct edit from a confidently
wrong one is a second read with an opposing default.

## What went well

- **The adversarial default was the load-bearing choice.** Instructing the
  verifier to default to REFUTED under uncertainty, rather than to agree, is
  what turned it from a rubber stamp into a filter. A confirming reviewer would
  have passed most of the 19.
- **Requiring a verbatim quote made the miscitations findable.** Two proposals
  quoted blank lines. That is invisible in prose and obvious against `sed -n`.
- **Re-verifying before editing caught what both passes missed.** One shipped
  edit narrowed "Agent memory (Serena, Forgetful) has two data streams". Reading
  the sub-bullets showed the two streams are memory content and operational
  metadata, not the two backends, so the sentence survived. Neither the
  classifier nor the verifier had checked that.

## What to improve

- **A behavioral claim about a state string needs the same evidence as a claim
  about code.** Across four check-ins this session I reported that a PR's
  `mergeable_state: blocked` meant a required review was outstanding. It did
  not; it was one unresolved review conversation, and resolving it flipped the
  state to `clean` with no review appearing. I inferred a cause from a state
  name and then repeated it as fact. Enumerate the blockers before naming one.
- **Do not quote a mention count as a worst case without re-measuring.** I
  carried "ADR-007, 30 mentions" as the largest architecture surface. It is
  ADR-037 at 72. The number was correct about ADR-007 and wrong about the
  ranking, which is the more useful claim.
- **A grep-returns-nothing acceptance criterion needs an exclusion list from
  the start.** AC1 cannot be satisfied while a decommission guard test whose
  job is to contain the token, and frozen eval run records, both match it.
  That was recorded as an open question on #5624 before this session and is
  still unanswered; 16 of the remaining 45 matches are in that class, the
  newest being a retired-name routing row in a migration script that a
  reviewer correctly asked me to put back.

## Remediation

| Action | Where | Status |
|---|---|---|
| Rewrite the 17 confirmed live surfaces and ship no refuted proposal | This PR, #5647 | Done |
| Restore the `forgetful-` routing row with its reason recorded inline | `scripts/restructure_memories.py` | Done, #5647 |
| Recount the refutation grounds from run data, one primary ground each | This retro | Done, #5647 |
| Decide the AC1 rescope: a recorded exclusion list, or drop the grep-returns-nothing form | Issue #5574, comment 5575524584 | Open, owner |
| Decide the orphan prompt that sits outside AC1 scope | Issue #5643 | Open, owner |
| Supersede the memory ADRs rather than editing them; ADR-037 is the largest at 72 mentions | Issue #5574 Stage 3 | Open, blocked on #5647 |
| A live three-tier memory table still presents the retired backend as a current tier | `.agents/governance/MEMORY-MANAGEMENT.md` | Not filed, Open, no owner |

## Evidence

- Workflow run `wf_45dc623d-ff0`: 12 agents, 0 errors, 51 files classified.
- Ratchets re-run rather than assumed: markdown portability 343 against
  baseline 343, exec portability 615 against baseline 623, vendor portability
  18 tracked offenders, all exit 0.
- Affected suites after the fixture edits: 167 passed, exit 0.
- `pre_pr.py`: all validations passed, exit 0, zero FAIL lines.
- AC1 count: 68 before, 45 after. The 45th is deliberate: review found that
  removing a `forgetful-` routing row from a one-time migration script would
  misroute historical records on the un-migrated tree the script exists to
  process, so the row was restored with that reason recorded inline.
