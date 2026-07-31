# Critique: ADR-068 / ADR-085 Factual Amendment (Issue #3218 Closure)

## Verdict
APPROVED_WITH_CONCERNS - Confidence: HIGH

## Summary

The amendment corrects ADR-068 and ADR-085 to reflect that issue #3218 closed
on 2026-07-28 because its premise was wrong. `_expand_dispatch_groups`,
`event_matcher_union`, and the dispatcher/parity/drift machinery are not
orphaned technical debt. The correction is factually necessary: those functions
are live generation paths with active consumers. Three concerns remain about
completeness, re-evaluation trigger rewording, and the downstream ADR-082
dependency reference.

## Scores by Axis

| Axis | Score | Notes |
|------|-------|-------|
| Completeness | 4/5 | All affected lines identified; one ADR-082 cascade missing. |
| Alignment | 5/5 | Amendment is purely factual correction; no scope drift. |
| Feasibility | 5/5 | Text-only changes; no code or process risk. |
| Risk Coverage | 3/5 | No guidance on what replaces #3218 as the forcing function for future simplification review. |
| Testability | 4/5 | Pass/fail is objective (issue state, code liveness); one claim needs quotation. |
| Traceability | 4/5 | REQ (issue closure) → DESIGN (ADR text) chain clear; ADR-082 link not traced. |

## Reasoning

**1. What breaks if this amendment is wrong?** If the text is left as-is, a
future contributor reads "Issue #3218 owns removal or simplification" and files
a PR deleting `_expand_dispatch_groups`, `event_matcher_union`,
`generate_dispatcher.consolidate`, and the parity tests. That PR breaks Copilot
CLI hook generation. The build script emits no valid `hooks.json` without the
dispatcher pipeline. The amendment prevents that concrete failure mode.

**2. What assumptions conflict with project constraints?** ADR-068 Status §
(line 42) says "The same change that removes or replaces the generated
dispatcher must mark this ADR deprecated or superseded and update ADR-082's
dependency." Closing #3218 as premise-invalid means no change removes the
dispatcher, so ADR-068 stays accepted. But the Re-evaluation Trigger #5
(lines 404-411) still reads as an open gate: "Issue #3218 starts
implementation." If #3218 is closed, this trigger can never fire, leaving the
decision without a live simplification forcing function. That is a constraint
gap, not a contradiction, but it must be named.

**3. Strongest counterargument to the amendment?** One could argue that closing
#3218 is premature and a rescoped issue (acknowledging liveness but reviewing
whether direct registration would be simpler for the one-shim case) is better
than closure + amendment. The steelman: closing the issue and amending two ADRs
locks in the current dispatcher complexity without a successor review
mechanism. The amendment should address this by either (a) replacing trigger #5
with a new trigger condition, or (b) explicitly recording that the one-shim
value question is now owned by a different mechanism (e.g., re-evaluation
trigger #2, which fires when the manifest grows beyond one shim).

## Critical Findings

### 1. ADR-068 Re-evaluation Trigger #5 becomes dead letter

**Where**: ADR-068 lines 404-411.
**What**: Trigger #5 says "Issue #3218 starts implementation." With #3218
closed as premise-invalid, this trigger can never fire. The blocking clause
("It must complete before the next feature change that adds or removes a
vendored registration") becomes vacuous.
**Impact**: No forcing function remains to review dispatcher complexity before
new registrations are added. A contributor could add five new shims without
ever triggering a simplification review.
**Recommendation**: Replace trigger #5 with a reworded trigger that names the
actual review condition (e.g., "A contributor proposes removing or replacing
the consolidated dispatcher with direct host registrations" or "The active
manifest inventory changes"). Do not simply delete the trigger; that removes
the guard entirely.

### 2. ADR-068 "Live GitHub verification" paragraph is stale

**Where**: ADR-068 lines 416-421.
**What**: The paragraph reads "Live GitHub verification on 2026-07-22 confirms
that ... #3218 remains open. The latter owns retirement of orphaned dispatcher
machinery. ... Retirement is planned but not complete." Every clause in this
paragraph is now false: #3218 is closed, the machinery is not orphaned, and
retirement is not planned.
**Impact**: A reader who trusts the verification paragraph will believe
retirement is imminent and may defer investments in the dispatcher (test
coverage, documentation, performance measurement).
**Recommendation**: Update the paragraph to record the 2026-07-28 closure,
the reason (premise invalid: machinery is live), and remove the "orphaned"
and "retirement" characterizations. Preserve the old text as a historical
note (e.g., `> Historical: prior to 2026-07-28, this paragraph stated ...`).

### 3. ADR-085 §5 and §6 Confirmation still scope #3218 as an open work item

**Where**: ADR-085 lines 293-328 (Decision 5 "Component-level machinery
retirement (#3218)") and the §6 Confirmation paragraph referencing "#3218
rescope."
**What**: Decision 5 says "#3218 evaluates the dispatcher, translation
adapters, parity checks, and drift checks as separate components." The
Confirmation says "#3218 must derive its consumer list from every active source
registration." Both treat #3218 as an open obligation.
**Impact**: The ADR-085 Impact table (line 470) still lists `Issue #3218 |
Direct | Evaluate dispatcher...` as a required update. A contributor tracking
#3218 dependency will find a closed issue that the ADR says is required. This
creates a governance gap: ADR-085 demands work that no issue tracks.
**Recommendation**: Amend Decision 5 to record #3218 closure and state that
the evaluation concluded with "premise invalid: components are live generation
paths." Amend the Impact table row to say "Closed (premise invalid); machinery
confirmed live." If a successor review is desired, open a new issue and
reference it.

### 4. ADR-082 cascade not addressed

**Where**: ADR-068 line 42 ("update ADR-082's dependency") and ADR-082 Status
(references ADR-068's dispatcher as a dependency).
**What**: ADR-068 says the change that removes the dispatcher must update
ADR-082. The amendment establishes that removal is not planned, but ADR-082
may also contain references to #3218 as a planned retirement. The amendment
scope does not include ADR-082.
**Impact**: ADR-082 could still describe #3218 as owning retirement of
machinery it depends on, creating the same stale-reference problem in a third
document.
**Recommendation**: Search ADR-082 for #3218 references and include any
necessary corrections in the same amendment. A factual correction that fixes
two of three documents ships drift in the third.

### 5. ADR-068 Alternatives table and Negative Consequences repeat stale framing

**Where**: ADR-068 line 292 ("Issue #3218 owns removal or simplification of
the now-low-value dispatcher machinery") and line 324 ("Issue #3218 owns
removal or simplification").
**What**: Both lines characterize the dispatcher as "now-low-value" and assign
ownership to #3218. The low process-savings finding remains valid, but the
issue no longer owns removal. The machinery is a live generation path whose
parity tests validate generated surfaces.
**Impact**: A reader of the Alternatives or Consequences sections gets the
opposite message from the Status section if only the Status is amended.
Internal contradiction within one ADR undermines trust in the document.
**Recommendation**: Remove or reword the "now-low-value" characterization.
Replace "#3218 owns removal or simplification" with a statement that the
machinery is retained as a live generation path. A footnote recording the
prior characterization preserves debate history.

## Semantic Updates (Exact Locations)

The following table lists every location that must change, the current text's
semantic error, and the required correction direction. Exact wording is the
author's responsibility; the table names the gap.

| File | Line(s) | Current semantic | Required correction |
|------|---------|------------------|---------------------|
| ADR-068 | 38-42 | "#3218 owns removal or simplification" | #3218 closed; machinery is live; no retirement planned |
| ADR-068 | 292 | "#3218 owns removal or simplification of the now-low-value dispatcher machinery" | Machinery is a live generation path; remove "low-value" and stale ownership |
| ADR-068 | 324 | "#3218 owns removal or simplification" | Same as line 292 |
| ADR-068 | 404-411 | Re-evaluation trigger #5 gates on #3218 implementation | Reword trigger to a condition that can actually fire |
| ADR-068 | 416-421 | "Live GitHub verification ... #3218 remains open ... Retirement is planned" | Record 2026-07-28 closure; remove "orphaned" and "retirement" language |
| ADR-085 | 293-303 | Decision 5 scopes #3218 as evaluating components for retirement | Record closure; components confirmed live |
| ADR-085 | 305-328 | Section 6 Confirmation: "#3218 must derive its consumer list" | Evaluation complete; consumer list confirmed active |
| ADR-085 | 441 | Negative: "#3218 remains open for a component-level cost and consumer review" | #3218 is closed; review concluded premise-invalid |
| ADR-085 | 470 | Impact table: #3218 row says "Evaluate dispatcher..." | Closed; machinery confirmed live |
| ADR-085 | 483 | Implementation Notes: "#3218 remains responsible for component-level retirement" | #3218 closed; no retirement responsibility |
| ADR-082 | TBD | Potential #3218 references (not audited in this amendment scope) | Must audit and correct in same amendment |

## Debate Log Preservation

The amendment must not delete or rewrite existing debate-log text in
`.agents/critique/ADR-068-debate-log.md` or
`.agents/critique/ADR-085-debate-log.md`. Those records are historical.
Amendment rationale should appear as a new dated section appended to each
debate log, not as edits to prior vote records.

## Approval Conditions

1. All five ADR-068 locations and all four ADR-085 locations listed above are
   corrected in the same commit.
2. ADR-082 is searched for #3218 references; any found are corrected in the
   same commit.
3. Re-evaluation trigger #5 in ADR-068 is replaced with a trigger that can
   actually fire (not gated on a closed issue).
4. Debate logs are preserved; amendment rationale is appended, not overwritten.

## Recommendation

Audit ADR-082 for #3218 references, then apply all ten corrections (plus any
ADR-082 hits) in a single atomic commit with a new dated debate-log appendix
in each affected ADR's debate log.

## Vote

**Accept**: the factual correction is necessary and the five concerns above
are addressable within the same amendment scope.
