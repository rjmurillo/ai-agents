---
id: ADR-118
status: accepted
date: 2026-10-13
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
review-by: 2027-04-13
---

# ADR-118: Widen FM-11 to Cover Hand-Authored Cross-Harness Instructions

## Context

`.claude/rules/retros.md` MUST 2 says each retrospective classifies its failure against `.agents/governance/FAILURE-MODES.md`. When no class matches, the retrospective proposes a new class in a linked ADR.

The retrospective for issue #4780 (`.project-toolkit/retrospective/2026-09-01-issue-4780-importer-path-resolution.md`) found that FM-11, Customer-Facing Generated Artifact Shipped Without Runtime Verification, matches the mechanism and fails the premise. FM-11's mechanism sentence: "No gate ever executes the artifact under the runtime contract of its target host." That is the #4780 defect. FM-11's opening sentence says "A generator produces an artifact." The importer, `.claude-mem/scripts/import_claude_mem_memories.py`, is hand-authored. A governance doc, `.agents/governance/MEMORY-MANAGEMENT.md`, installed it into every harness's session by recommending it with no harness qualification.

The retrospective ruled out FM-4, FM-9, and FM-10 on the record. It could not author this ADR, because `AGENTS.md` lists new ADRs under Ask First and the session was unattended. Issue #5461 is the proposal step. It offers three options: widen FM-11, add a sibling class, or reject. The owner delegated the choice for this issue on 2026-10-11.

The catalog has 13 classes. FM-12 landed through ADR-105 and FM-13 through ADR-117, so option 2 in the issue would now be FM-14.

## Decision

Widen FM-11. Keep it one class, with one mechanism, and cover both delivery paths.

1. **Definition.** An artifact installed into a customer's environment or another harness's session ships without any gate that runs it under the target host's runtime contract. A generator can produce the artifact, or a person can write it and a repository document can publish it as a cross-harness instruction.
2. **Rename.** The title and Index row drop the word "Generated". The mechanism, severity, and primary evidence do not change.
3. **Variant paragraph.** The Description gains a short paragraph for the hand-authored variant. Its delivery path is the documentation, so there is no generator and no plugin manifest to gate. The #4780 case is the worked example.
4. **Detection and enforcement.** The enforcement table keeps its rows and gains one for the hand-authored variant, the exact exit-code contract test from PR #5459. The committed-artifact gate and hook smoke stay specific to generated hooks. Detection gains two lines: a command that governance docs recommend with no harness qualification and no test where the recommending harness's files are absent, and an assertion that accepts a function's whole documented return range.
5. **Principle.** The principle sentence reads "a customer-facing artifact, generated or hand-authored, MUST be executed in its target runtime before release."
6. **Retrospective.** The #4780 retrospective gets a dated correction section citing this ADR. Per `retros.md` MUST NOT 1 it is appended, not edited in place.

No gate changes. FAILURE-MODES.md is read by people and agents during retrospectives and ADR review. No script parses its class list or its titles.

The secondary observation in #5461, that the assertion `in (0, 1)` cannot fail, is recorded as a detection line only. A taste-lint for that shape is a separate change with its own false-positive calibration. This ADR does not commit to it.

## Alternatives Considered

| Option | Verdict | Why |
|--------|---------|-----|
| A. Widen FM-11 (chosen) | Chosen | The issue marks it the cheapest option and says FM-11's detection and enforcement rows apply. The mechanism is identical, and the hook-specific rows stay scoped to hooks. The change is one premise sentence plus a variant paragraph. |
| B. Add a sibling class, now FM-14 | Rejected | Its detection and runtime-contract rows would copy FM-11's. Two classes for one mechanism split the evidence base, so a future retrospective has to guess between them. The only difference is the delivery path, which the variant paragraph states. |
| C. Reject and record that FM-11 already covers it | Rejected | FM-11's first sentence says "A generator produces an artifact." The #4780 retrospective read it literally and had to record a divergence. The next author will do the same. |

## Prior Art Investigation

- `rg -n "hand-authored|cross-harness" .agents/governance/FAILURE-MODES.md` returned no FM-11 hit on `origin/main` at `1c06583b9`.
- `rg -n "Generated Artifact Shipped"` finds the title only in FAILURE-MODES.md, the `ai-agents-failure-archaeology` skill template, and landed retrospectives and ADR-071. No script parses it.
- ADR-117 is the precedent for a taxonomy change landing with its own ADR, a reduced panel, and an appended retrospective correction.

## Rationale

The taxonomy exists so a retrospective can name a failure and point at a known remedy. For #4780 the remedy is FM-11's: run the artifact under the target host's runtime contract, with a negative control. A new class would send the author to the same remedy by a second name.

Renaming the title is part of the widening. A class titled "Generated Artifact" that claims to cover hand-authored scripts misleads the reader who scans the Index.

Severity stays Critical. The #4780 defect was a false failure on an optional dependency, not a wedged environment. The class severity covers the worst variant, the wedge, and the evidence list shows both.

## Consequences

**Positive**

- A retrospective for a hand-authored cross-harness instruction cites FM-11 with no divergence note.
- The "assertion that cannot fail" shape has a named detection line.

**Negative**

- FM-11's scope grows. A reader must now decide whether a hand-authored script is "published as a cross-harness instruction." The test is whether a repository document tells another harness to run it.
- The `ai-agents-failure-archaeology` skill table carries the new title and a third evidence row.

**Neutral**

- `FAILURE-MODES.md` "When to Read" still says "eight patterns". That text was stale before this change and is left alone.
- The `ai-agents-failure-archaeology` skill table lists FM-1 through FM-11 only. It was stale before this change and is left alone.

## Impact on Dependent Components

| Component | Impact |
|-----------|--------|
| `.agents/governance/FAILURE-MODES.md` | FM-11 title, Index row, Description, Trigger, Evidence, Detection, principle, References |
| `.project-toolkit/retrospective/2026-09-01-issue-4780-importer-path-resolution.md` | Appended correction section |
| `templates/skills/ai-agents-failure-archaeology.SKILL.md.tmpl` | FM-11 row title and evidence; rendered copy follows |
| `.claude/rules/retros.md` | None. MUST 2 is satisfied by this ADR. |
| Gates | None. No script reads the class list or titles. |

## Reversibility Assessment

High. Restoring the old FM-11 text is a documentation revert. A retrospective that cites the widened class would need a new correction section.

## Consensus

Review ran under the `adr-review` skill with the reduced panel (architect and critic). The change edits a taxonomy entry in a governance document and touches no executable enforcement or rule other gates read. The debate log is `.project-toolkit/critique/ADR-118-debate-log.md`. Both seats ran inline in one agent session, so the review is not independent. The owner's merge review is the independent check.

## References

- Issue #5461 (this decision), #4780, PR #5459
- `.agents/governance/FAILURE-MODES.md`, section 11
- `.project-toolkit/retrospective/2026-09-01-issue-4780-importer-path-resolution.md`
- `.claude/rules/retros.md` MUST 2 and MUST NOT 1
- `.claude/rules/governance.md` MUST 2 and 4
- ADR-071 (FM-11 origin), ADR-117 (precedent for a taxonomy ADR)
