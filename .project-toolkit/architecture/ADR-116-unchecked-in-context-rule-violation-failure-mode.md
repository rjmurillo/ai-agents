---
id: ADR-116
status: proposed
date: 2026-10-13
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-04-13
---

# ADR-116: Propose a Failure Mode for Unchecked In-Context Rule Violations

## Status

Proposed. The owner has not accepted the class, and `FAILURE-MODES.md` is unchanged until then.

## Context

`.claude/rules/retros.md` MUST 2 says each retrospective classifies its failure against `.agents/governance/FAILURE-MODES.md`. If no class matches, the retro "MUST propose a new class in a linked ADR".

Two retrospectives describe the same shape and fit no class:

1. `.project-toolkit/retrospective/2026-08-21-pr-automerge-goal-session-2.md`, Finding 2. A PR body held an em dash. The session had loaded `.claude/rules/universal.md` all session. `pr_description.py:validate_no_dashes` failed the PR at its first validation run, a CI round. One body edit fixed it.
2. `.project-toolkit/retrospective/2026-08-25-issue-5192-adr-052-036-reciprocity.md`, Finding 1. The same dash rule was broken again in a different session, across nine files. The staged-dash pre-commit job (`lefthook.yml:119`, `staged-dash-policy`) failed the first commit attempt. No CI round ran. A mechanical substitution fixed it.

Both retros cite the dash ban as MUST NOT 5. It is MUST NOT 4 now.

The nearest classes do not fit:

- FM #1 (Context Reading Failure) is defined by beginning work without reading required context. Both sessions had read the rule. The 08-21 retro stretched FM #1 to "read but not cross-applied" on its Finding 1, then said Finding 2 "does not cleanly fit".
- FM #3 (Ambiguous Instruction Inversion) needs an ambiguous instruction. The dash ban is an unambiguous MUST NOT.
- FM #9 (Confident-Incorrectness Recurrence) is defined by a wrong model of a contract that takes several correction rounds. Here the author's model of the rule was right and a mechanical edit fixed the output.

The 08-25 retro cites issue #5300 as the proposal. Issue #5300 is a request to write this ADR. A pointer to a request does not satisfy "a linked ADR". Issue #5307 finding 5 records that gap. This ADR is the proposal both retros need.

## Decision

Propose a class named **Unchecked In-Context Rule Violation**, numbered with the next free FM number at acceptance (FM #14 on 2026-10-13, because ADR-117 took FM #13), for `.agents/governance/FAILURE-MODES.md`. This record only proposes it. The taxonomy file is not edited until the owner accepts this record.

Proposed class entry, in the file's existing shape:

1. **Description.** An agent generates output that breaks a rule already loaded in its context. It runs no check of that output against the rule before it stages or submits it. The cause is the missing check, not a missing read or a wrong model of the rule. The class covers only rules a deterministic tool can test.
2. **Trigger.** A rule that a deterministic tool can test is in context, and the agent writes or stages output without running that tool first. Evidenced for one rule, the dash ban. Other testable rules (a banned-word list, a filename pattern) are extrapolation until an instance shows up. Out of class: a rejection the agent could not predict without running the tool, such as a formatter's output.
3. **Boundary against neighbors.**
   - Against FM #1: the rule was read. The failure is a missing check on the output.
   - Against FM #3: the rule has one reading.
   - Against FM #9: FM #9 is triggered by a claim of parity with a source that is not quoted. This class is triggered by writing checkable output without running the checker. If an unquoted parity claim is present, classify the case under FM #9.
   - Against FM #4 (False Completion Markers) and FM #6 (Multi-Agent Rubber-Stamping): those classes report a claim of verification that did not happen. Here the author made no claim and a gate caught the output.
4. **Evidence.** Two instances of one rule, in two sessions. One reached CI (08-21). One was stopped by a local pre-commit hook before any commit object existed (08-25). The 08-25 retro's own test says classes describe failures that reach an external gate or reviewer, so the local catch is weaker evidence than the CI one. The 08-21 retro proposed checking prose against the rule before submitting it. The 08-25 retro, Learning 1 row of its Existing Match table, records that this fix did not transfer to a later session. `.claude/rules/voice.md` (`paths: ["**"]`, `priority: critical`) does carry a Quick Self-Review question, "Did you use any banned word? Any em dash or en dash?", and the 08-25 session still broke the rule. The self-check was in context and was not run. That supports the class. Whether the cause is the missing check or the un-persisted learning is INFERRED, not measured.
5. **Detection.** A pre-commit, pre-push, or PR-validation rejection on the first attempt for a rule that was demonstrably in context. The fix diff is mechanical.
6. **Enforcement pattern.** None new. Detection already exists: `git_hook_policy.py staged-dashes` runs at commit and `pr_description.py:validate_no_dashes` runs at PR validation. The 08-25 retro's Learning 1 proposes a pre-stage check skill (`voice/pre-stage-dash-check`). Its named owner, issue #5288, is closed. The closing PR #6398 fixed the shallow-clone half (`scripts/bootstrap-vm.sh`). Its body disposes of the dash half as "already persisted. voice.md Quick Self-Review asks about em and en dashes, and universal.md MUST NOT 4 binds the rule. No change." A prompt-level self-review question is not a pre-stage check that runs a tool, and the 08-25 instance shows the question alone did not prevent the violation. A search of the tree outside the two retros and this ADR finds no pre-stage dash check. No open issue owns it. The class is detection-only until someone builds one.

Severity: Medium, the lowest tier in the FAILURE-MODES index. The 08-25 retro rates it "Low-medium". Each instance cost one extra gate round (CI in one case, a local commit retry in the other) and had no external consequence.

On acceptance, one follow-up PR adds the entry and an index row to `FAILURE-MODES.md`.

## Alternatives Considered

| Option | Verdict | Reason |
|--------|---------|--------|
| Write the ADR now as a proposal (chosen) | Chosen | MUST 2 names a linked ADR as the path for a class that does not fit. |
| Widen FM #1 to "read but not applied" | Rejected | FM #1's detection and enforcement are about session-start reading (init, handoff, required files). The dash cases read the rule and lacked an output check. Widening FM #1 would blur a class whose gates are read-time gates. |
| Reclassify both findings under FM #9 | Rejected | The 08-25 retro already rejected this fit. FM #9's fix is a corrected contract model, not a mechanical edit. |
| Reclassify under FM #3 | Rejected | FM #3 requires an ambiguous instruction. The dash ban has no permissive reading. |
| Amend `retros.md` MUST 2 to accept an open issue as the proposal | Rejected | The rule already says "linked ADR". The retros broke the rule. Loosening it removes the check. |
| Add the class to `FAILURE-MODES.md` with no ADR | Rejected | MUST 2 names an ADR for a retro whose failure fits no class. Issue #5300 asks for one. PR #5506 added FM #12 with no ADR in that PR, and ADR-105 recorded it afterward. That order is not a rule for the taxonomy. |
| Decline the class and record both instances as near-misses | Rejected | The 08-25 instance was a local catch, which the 08-25 retro's own test calls a near-miss. The 08-21 instance reached CI, so one external instance stands. MUST 2 then sends it to a linked ADR, and this ADR is the place where the owner can decide to decline. |
| Build a mechanical pre-stage check instead of a class | Out of scope | The 08-25 retro's Learning 1 proposes it. It is a separate change with its own owner decision. The class is useful without it because it gives the next retro a place to classify. |
| Leave the finding unclassified | Rejected | Two sessions now show the same rule. The 08-21 retro declined a class for "a single instance". |

## Prior Art Investigation

FM #12 (Post-Completion Continuation) appears in the `FAILURE-MODES.md` index with issue #5404 as its evidence. PR #5506 added it with no ADR in that PR. ADR-105 (`ADR-105-terminal-state-completion-contract.md`) records the class. This class follows MUST 2's ADR path because a retro, not a rule PR, is asking for it.

No existing gate measures this class, so it has no observed rate beyond the two instances.

## Rationale

MUST 2 offers one path for a class that does not fit: a linked ADR. Writing that ADR is the smallest change that makes both retros compliant. It changes no rule, gate, or taxonomy entry until the owner accepts it.

## Consequences

### Positive

- Both retros can link a real ADR, so MUST 2 holds for them.
- The class gives the next retro a place to classify this shape instead of forcing a fit.

### Negative

- The class has two instances, both for one rule, and one is a local near-miss. The dash rule may stay the only member. Trigger to revisit: the `review-by` date. A retro that finds a third instance of any rule should link this ADR.
- The existing gates already catch the violation, so the class adds naming and no control. An index row and an entry may cost more than the failures they name. The owner can decline on that basis.
- The enforcement pattern is empty until someone builds the pre-stage check.

## Impact on Dependent Components

| Component | Change |
|-----------|--------|
| `.agents/governance/FAILURE-MODES.md` | None until acceptance. Then one entry and one index row. |
| `.claude/rules/retros.md` | None. |
| The two retrospectives | Each gains an appended dated correction that links this ADR. Landed retros are not edited in place (`retros.md` MUST NOT 1). |

## Reversibility Assessment

Fully reversible. A `proposed` record can move to `rejected` by a frontmatter edit. No code, gate, or rule depends on it.

## Related Decisions

- ADR-073: ADR lifecycle frontmatter. Its status enum ties `accepted` to adr-review evidence.
- ADR-105: Terminal-state completion contract. Precedent for FM #12.

## References

- Issue #5307, finding 5.
- Issue #5300, the request this ADR answers.
- `.claude/rules/retros.md`, MUST 2 and MUST NOT 1.
- `.agents/governance/FAILURE-MODES.md`, FM #1, #3, #4, #6, #9, #12.
- Issue #5288, the closed owner of the pre-stage dash check.
- PR #6398, which closed #5288 and disposed of the dash half.
- PR #5506, which added FM #12 with no ADR in that PR.
- `.claude/rules/universal.md`, MUST NOT 4, the dash ban.
- `.claude/rules/voice.md`, Quick Self-Review.
- `lefthook.yml:119`, the `staged-dash-policy` job.
- `pr_description.py:validate_no_dashes`, the PR validation check.
- `.project-toolkit/retrospective/2026-08-21-pr-automerge-goal-session-2.md`, Finding 2.
- `.project-toolkit/retrospective/2026-08-25-issue-5192-adr-052-036-reciprocity.md`, Finding 1 and Learning 1.
