---
id: ADR-117
status: accepted
date: 2026-10-13
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
review-by: 2027-04-13
---

# ADR-117: Add FM-13, State Conflation in a Boolean Guard, to the Failure Taxonomy

## Context

`.claude/rules/retros.md` MUST 2 says each retrospective classifies its failure against `.agents/governance/FAILURE-MODES.md`. When no class matches, the retrospective proposes a new class in a linked ADR.

The retrospective for issue #5097 (`.project-toolkit/retrospective/2026-08-17-issue-5097-aggregator-cancelled-guard.md`) filed its root cause under FM-10, Silent Defaults and Guard-Clause Suppression. A Copilot review of PR #5103 disputed that (issue #5139), and the retrospective's correction section retracted the citation. The reason: FM-10 requires that the execution succeeds and the failure is invisible. The `always()` aggregators did the opposite. Their failures were loud red check runs. A `cancelled` result was reported as `failure`, and both were real signals.

The catalog had 12 classes when this ADR was written (issue #5145 counted 11, then FM-12 landed through ADR-105). None describes the shape: two non-equivalent input states collapsed onto one boolean guard, each surfaced correctly as far as the guard can tell.

Issue #5145 asks for an ADR that either adds a class or records why the existing classes suffice. It marks the proposal as a starting point and leaves the decision to the owner. The owner delegated that decision for this issue on 2026-10-11.

## Decision

Add one class to `FAILURE-MODES.md`, FM-13, State Conflation in a Boolean Guard.

1. **Definition.** A single boolean condition decides an outcome from an input that holds two or more non-equivalent states, so at least one state is reported as another. The outcome is surfaced, not hidden.
2. **Falsifiable distinguisher from FM-10.** Ask whether a reader of the output knows something went wrong. If yes, the incident is not FM-10. FM-10 stays the class for suppression, where the call site cannot know the operation did not do what its name claims.
3. **Remedy.** Make each distinguishable state an explicit branch with its own outcome, and test the guard with one row per input state.
4. **Evidence.** Three incidents with one shared shape: issue #1168 (`skipped` read as not passing), issues #5097 and #5103 (`cancelled` read as `failure`), and issue #5104 (a cancelled upstream read as a failed scan). Its retrospective, `2026-09-01-issue-5104-codeql-cancellation-guard.md`, already says no class fits and points at #5145.
5. **Cross-reference.** FM-10 gains a short "Not this class: loud conflation" pointer so a reader who lands on FM-10 finds the neighbor.
6. **Retrospective.** The #5097 retrospective gets a dated correction section citing FM-13. Per `retros.md` MUST NOT 1 it is appended, not edited in place.

No gate changes. FAILURE-MODES.md is read by people and agents during retrospectives and ADR review. No script parses its class list.

## Alternatives Considered

| Option | Verdict | Why |
|--------|---------|-----|
| A. Add FM-13 as a new class (chosen) | Chosen | The issue recommends it. Three incidents share the shape. FM-10 and FM-4 each fail a stated test for it. |
| B. Record that the 12 classes suffice | Rejected | The retrospective already had to retract FM-10. Leaving the gap makes the next author repeat the miscategorization, or invent a class in a retro with no ADR. |
| C. Widen FM-10 to cover loud conflation | Rejected | FM-10's evidence, detection table, and remedy all assume suppression. Widening it removes the property that makes it testable: the failure is invisible. |
| D. Fold the shape into FM-4 (False Completion Markers) | Rejected | FM-4 is about an agent's own success narration. A CI gate's verdict logic is a different layer. |

## Prior Art Investigation

- `rg -n "conflation|boolean guard" .agents/governance/FAILURE-MODES.md` returned nothing on `origin/main` at `65d769846`.
- The retrospective's correction section already tested FM-4 and FM-10 and rejected both.
- Issue #1168 predates the #5097 retrospective by months and has the same shape in the opposite direction (`skipped` instead of `cancelled`). The shape is not a one-off.

## Rationale

The taxonomy exists so a retrospective can name a failure and point at a known remedy. A class that matches only by stretching its definition sends the author to the wrong remedy. FM-10's remedy is "stop suppressing." Applied to the `always()` bug it would add logging to a failure that was already loud, and leave the conflation in place.

FM-11 and FM-12 each rest on one primary retrospective or issue. FM-13 cites three incidents.

Severity is Medium. The outcome is visible, so a reader can reach the cause. The cost measured in #5097 was three spurious failure webhooks from one routine supersede, each a wake for subscribed agents. #1168 blocked merges until an admin override.

## Consequences

**Positive**

- A retrospective for a loud conflation has a class to cite and a remedy to apply.
- The FM-10 / FM-13 split is testable with one question.

**Negative**

- The catalog grows from 12 to 13 entries. Readers scan one more row.
- Issue #1168 predates the retrospective practice and has no retrospective. Its evidence is the issue text.

**Neutral**

- `FAILURE-MODES.md` "When to Read" still says "eight patterns". That text was stale before this change and is left alone.

## Impact on Dependent Components

| Component | Impact |
|-----------|--------|
| `.agents/governance/FAILURE-MODES.md` | New Index row, new section 13, FM-10 pointer |
| `.project-toolkit/retrospective/2026-08-17-issue-5097-aggregator-cancelled-guard.md` | Appended correction section |
| `.claude/rules/retros.md` | None. MUST 2 is satisfied by this ADR. |
| Gates | None. No script reads the class list. |

## Reversibility Assessment

High. Removing FM-13 is a documentation revert. A retrospective that cites it would need a new correction section.

## Consensus

Review ran under the `adr-review` skill with the reduced panel (architect and critic). The change adds a taxonomy entry to a governance document and touches no executable enforcement or rule other gates read. The debate log is `.project-toolkit/critique/ADR-117-debate-log.md`. Both seats ran inline in one agent session, so the review is not independent. The owner's merge review is the independent check.

## References

- Issue #5145 (this decision), #5097, #5103, #5139, #1168, #5104
- `.agents/governance/FAILURE-MODES.md`, sections 10 and 13
- `.claude/rules/retros.md` MUST 2 and MUST NOT 1
- `.claude/rules/governance.md` MUST 2 and 4
- ADR-105 (precedent: FM-12 landed with its ADR)
