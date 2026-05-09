---
type: task
id: TASK-006
title: Implement Step 0 First Principles Gate in spec pipeline
status: todo
priority: P1
complexity: XS
related:
  - DESIGN-006
  - REQ-006
  - issue: 1926
blocked_by: []
blocks: []
assignee: implementer
created: 2026-05-09
updated: 2026-05-09
---

# TASK-006: Implement Step 0 First Principles Gate in spec pipeline

## Objective

Edit two markdown files (`.claude/commands/spec.md` and `src/copilot-cli/skills/spec/SKILL.md`)
to insert Step 0 First Principles gate, narrow Step 1, update Step 3 Tier 5, and add three
Step 9 critic checks. Optionally write ADR-060. No new scripts, CI, or schemas.

## In Scope

- Insert Step 0 block in `.claude/commands/spec.md` (before Step 1)
- Update Step 1 text in `.claude/commands/spec.md`
- Update Step 3 Tier 5 bullet in `.claude/commands/spec.md`
- Add three Step 0 validity checks to Step 9 in `.claude/commands/spec.md`
- Mirror all body changes to `src/copilot-cli/skills/spec/SKILL.md`
- Verify `src/copilot-cli/skills/memory/spec/skill-specification.xml` and update if needed
- Optional: write `.agents/architecture/ADR-060-spec-step0-first-principles-gate.md`
- Manual validation run (halt case + pass case)

## Out of Scope

- Automated answering of Step 0 questions
- First Principles steps 3-5 (optimize, speed up, automate)
- Full YC office-hours skill import
- Changes to `.claude/agents/spec-generator.md` (issue #1925)
- New CI validation scripts for Step 0
- Refactoring unrelated sections of spec.md

---

## TASK-006-1: Insert Step 0 block in `.claude/commands/spec.md`

**Objective**: Add the six-question First Principles gate as Step 0, before Step 1.

**Complexity**: XS (1-2 hours)

**Acceptance Criteria**:
- [ ] Step 0 prose appears in `.claude/commands/spec.md` before the Step 1 heading (AC-1a).
- [ ] All six questions are present and labelled Q1-Q6 with canonical text from DESIGN-006.
- [ ] Pass criteria are stated: all six fields non-empty, no hedge phrase in any field, Q1/Q3/Q5 pass operational tests.
- [ ] Canonical Hedge Phrase List is embedded as a fenced table with phrases-only entries (no standalone "should," "might," "could"). Note explaining RFC 2119 exclusion is present.
- [ ] Operational tests for "speculative" (Q5), "aspirational" (Q1), and "specific" (Q3) are embedded as fenced rules with checkable boolean conditions.
- [ ] Five halt triggers are stated and numbered H1-H5 (H5 = partial completion explicitly).
- [ ] HALT directive references the Halt Message Schema (5 required fields: trigger ID, question + label, failing answer verbatim, operational test that failed, deferral instruction).
- [ ] Structured Step 0 output format is defined (fenced `## Step 0 First Principles` block with six `### Q1..Q6` sub-headings).
- [ ] Auto-mode behavior is stated: halt with `STEP_0_REQUIRES_ELICITATION` and return to orchestrator; free-form synthesis prohibited; populate from source artifact only when fields are present verbatim (AC-12).
- [ ] Kill criteria reference is present: `STEP-0-METRICS.md` tally noted; review at 30 invocations against REQ-006-13 criteria (AC-13).

**Files affected**:

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | Edit | Insert Step 0 block at approximately line 15, before Step 1 heading |

**Implementation notes**:
- Read the current file before editing to confirm insertion point.
- The Step 0 block must be a new numbered step (Step 0), visually distinct from Step 1.
- Use a horizontal rule or clear heading to delimit Step 0 from Step 1.
- Do not change Step 1 prose in this task (that is TASK-006-2).

---

## TASK-006-2: Update Step 1 in `.claude/commands/spec.md`

**Objective**: Narrow Step 1 to constraints, edge cases, and integration surface only, removing
any overlap with Step 0 questions.

**Complexity**: XS (1 hour)

**Acceptance Criteria**:
- [ ] Step 1 prose states that problem motivation is captured in the Step 0 block.
- [ ] Step 1 explicitly says: "Do not re-elicit Q1-Q6 here."
- [ ] Step 1 questions are restricted to: constraints, non-functional requirements, integration touch points, edge cases not covered by Q4 (Narrowest Wedge).
- [ ] No Step 1 question asks about demand, workarounds, blocked users, or smallest deliverable (those are Q1-Q4).

**Files affected**:

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | Edit | Update Step 1 heading section |

**Implementation notes**:
- Diff Step 1 before and after to confirm no Q1-Q6 overlap remains.

---

## TASK-006-3: Update Step 3 Tier 5 bullet in `.claude/commands/spec.md`

**Objective**: Replace the standalone "why not simpler?" challenge in the Tier 5 bullet with a
reference to Step 0 Q4 re-validation.

**Complexity**: XS (30 minutes)

**Acceptance Criteria**:
- [ ] The phrase "Explicit why not simpler? challenge. If complexity can be driven out, do it before specifying." is removed from the Tier 5 bullet.
- [ ] The replacement text reads: "Re-validate Step 0 Q4 (Narrowest Wedge) in the context of emerged complexity. If the wedge can be narrowed further without losing the unblocking value, narrow it before proceeding."
- [ ] No other Tier bullets are changed.

**Files affected**:

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | Edit | Replace Tier 5 bullet text in Step 3 section |

**Implementation notes**:
- Read the Step 3 section to find the exact current Tier 5 bullet text before editing.
- Edit must be a precise replacement; do not reformat other Tier bullets.

---

## TASK-006-4: Add Step 0 validity checks to Step 9 critic pre-mortem in `.claude/commands/spec.md`

**Objective**: Add three Step 0 validity checks to the critic pre-mortem so violations surface
before the spec ships.

**Complexity**: XS (30 minutes)

**Acceptance Criteria**:
- [ ] Step 9 pre-mortem list includes Check 9a (Demand Reality drift), Check 9b (Desperate Specificity drift), Check 9c (Narrowest Wedge drift).
- [ ] Each check is phrased as a binary PASS/FAIL assertion with explicit pass conditions, NOT an open-ended question (AC-9).
- [ ] The three checks are appended to the existing pre-mortem list without removing or reordering existing checks.
- [ ] Each FAIL emits the specific Q1/Q3/Q4 quote alongside the drifted PRD content.
- [ ] The critic SHALL NOT emit `APPROVED` while any of 9a, 9b, 9c is FAIL.

**Exact text for the three checks** (binary, with operational pass conditions):

```
- **Check 9a — Demand Reality drift**:
  - PASS: PRD acceptance criteria, user stories, OR success metric reference at least one entity (person, team, system, metric, ticket, file path) named in Q1.
  - FAIL otherwise. On FAIL: cite Q1 entities and the PRD's current entities verbatim.
- **Check 9b — Desperate Specificity drift**:
  - PASS: PRD user stories or acceptance criteria still treat the Q3-named blocked entity as the primary unblocking target.
  - FAIL if (a) the spec's primary user shifted, OR (b) Q3's named entity does not appear in the PRD. On FAIL: cite Q3's entity and the PRD's current primary user verbatim.
- **Check 9c — Narrowest Wedge drift**:
  - PASS: every PRD acceptance criterion either traces to the Q4 wedge or narrows it.
  - FAIL if any AC adds scope beyond Q4 without a documented wedge revision. On FAIL: cite Q4 verbatim and list the AC entries that exceed the wedge.
- **Critic verdict gate**: if any of 9a/9b/9c is FAIL, the critic emits a blocking finding and cannot return APPROVED.
```

**Files affected**:

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | Edit | Append three checks to Step 9 pre-mortem list |

---

## TASK-006-5: Mirror all changes to `src/copilot-cli/skills/spec/SKILL.md`

**Objective**: Apply identical body changes to the Copilot CLI twin.

**Complexity**: XS (1 hour)

**Acceptance Criteria**:
- [ ] `src/copilot-cli/skills/spec/SKILL.md` contains the Step 0 block (identical text to `.claude/commands/spec.md`).
- [ ] Step 1 update is mirrored.
- [ ] Step 3 Tier 5 bullet replacement is mirrored.
- [ ] Step 9 three validity checks are mirrored.
- [ ] SKILL.md frontmatter (name, version, description, and any other fields) is preserved unchanged.
- [ ] The body diff between the two files is zero for the edited sections.

**Files affected**:

| File | Action | Description |
|---|---|---|
| `src/copilot-cli/skills/spec/SKILL.md` | Edit | Mirror all four body changes from TASK-006-1 through TASK-006-4 |

**Implementation notes**:
- Read `src/copilot-cli/skills/spec/SKILL.md` before editing to confirm structure.
- If the file structure differs materially from `spec.md`, adapt placement but preserve identical question and directive text.
- After editing, compare the two files' Step 0 sections side-by-side to confirm no drift.

---

## TASK-006-6: Verify `src/copilot-cli/skills/memory/spec/skill-specification.xml`

**Objective**: Determine whether this file duplicates spec body content and update if yes.

**Complexity**: XS (30 minutes)

**Acceptance Criteria**:
- [ ] File has been read and its content categorized as one of: (a) does not duplicate spec body, no update needed; (b) duplicates spec body, updated to reflect Step 0 gate.
- [ ] Decision and rationale are documented in the PR description.

**Files affected**:

| File | Action | Description |
|---|---|---|
| `src/copilot-cli/skills/memory/spec/skill-specification.xml` | Read, conditionally edit | Check for spec body duplication; update if yes |

**Implementation notes**:
- If the file is a schema or metadata file (not prose instructions), no update is likely needed.
- If the file contains step-by-step spec instructions, treat it as a third sync target and apply the same changes.

---

## TASK-006-7 (Optional): Write ADR-060

**Objective**: Record the architectural decision to add a blocking front gate to the spec pipeline.

**Complexity**: XS (1 hour)

**Acceptance Criteria**:
- [ ] File exists at `.agents/architecture/ADR-060-spec-step0-first-principles-gate.md`.
- [ ] Status: Proposed.
- [ ] Context section explains the problem (aspirational demand reaching downstream spec steps).
- [ ] Decision section states the six-question First Principles gate as Step 0.
- [ ] Consequences section lists: one additional conversation turn per invocation; halt on invalid demand saves all downstream cost.
- [ ] Alternatives considered: post-hoc critic-only validation; non-halting demand checklist in Step 1.

**Files affected**:

| File | Action | Description |
|---|---|---|
| `.agents/architecture/ADR-060-spec-step0-first-principles-gate.md` | Create | New ADR |

---

## TASK-006-8: Manual validation run (13 test cases)

**Objective**: Prove the halt cases, pass cases, and edge cases work in practice. See DESIGN-006 Testing Strategy section "Dynamic verification" for the full T1-T13 catalog.

**Complexity**: S (2-3 hours; 13 invocations)

**Acceptance Criteria**:
- [ ] **T1** Q3 hedge ("stakeholders want") → H1 halt, quote present.
- [ ] **T2** Q5 RFC 2119 "should" with citation → PASS (single word "should" is not a hedge).
- [ ] **T3** Q5 speculative ("users find this slow") → H2 halt.
- [ ] **T4** Q5 with citation (issue link, retro line ref) → PASS.
- [ ] **T5** Q1 aspirational ("users would want this") → H3 halt.
- [ ] **T6** Q1 with three named teams + ticket numbers → PASS.
- [ ] **T7** Q3 generic ("engineers in general") → H4 halt.
- [ ] **T8** Q3 specific (named individual + system + frequency) → PASS.
- [ ] **T9** All six fields valid → structured `## Step 0 First Principles` block as first PRD section, six `### Q1..Q6` subheads.
- [ ] **T10** PRD acceptance criteria reference different blocked entity than Q3 → Check 9b FAIL, critic blocking finding.
- [ ] **T11** Q1-Q3 answered, Q4-Q6 empty → H5 halt listing Q4, Q5, Q6.
- [ ] **T12** Auto-mode with bare issue body → `STEP_0_REQUIRES_ELICITATION` halt with all six question numbers.
- [ ] **T13** Auto-mode with issue body containing all six structured fields verbatim → PASS, fields populated verbatim.
- [ ] Static-1 lint check (grep `Step 0` before `Step 1`; `Q1-Q6` and `Step 0` in Step 2; `Re-validate Step 0 Q4` AND no `why not simpler?` in Tier 5; `STEP-0-METRICS.md` OR `kill criteria` in Step 0) passes.
- [ ] Static-2 diff check: edited sections of `.claude/commands/spec.md` and `src/copilot-cli/skills/spec/SKILL.md` are byte-identical.
- [ ] Evidence (session transcripts) attached to the issue or PR.

**Files affected**:

None (validation only; evidence documented in PR description).

---

## Testing Requirements

Tier 1 complexity. No automated test suite required. Verification is manual per TASK-006-8.

If the implementer chooses to add an automated smoke test:
- A pytest or Pester test that asserts the Step 0 block text appears in `spec.md` before any Step 1 heading text is sufficient.
- Place under `tests/commands/` if created.

## Effort Estimate

| Task | Complexity | Hours |
|---|---|---|
| TASK-006-1 (Insert Step 0; includes hedge phrase list, operational tests, halt schema, kill criteria ref) | XS | 2-3 |
| TASK-006-2 (Update Step 1) | XS | 1 |
| TASK-006-3 (Update Step 3 Tier 5) | XS | 0.5 |
| TASK-006-4 (Update Step 9 with binary checks) | XS | 1 |
| TASK-006-5 (Mirror SKILL.md) | XS | 1 |
| TASK-006-6 (Verify XML) | XS | 0.5 |
| TASK-006-7 (ADR-060, optional) | XS | 1 |
| TASK-006-8 (13 dynamic + 2 static validation) | S | 2-3 |
| **Total** | **XS-S** | **9-11** |

## Revision History

- **v1 (2026-05-09)**: Initial draft from issue #1926.
- **v2 (2026-05-09)**: Updated after analyst, decision-critic, and critic pre-mortem review surfaced 5 CRITICAL gaps. Changes:
  - REQ-006 Evidence section added citing 9 retros (PR #1887 Phase 6 is the strongest single citation).
  - REQ-006-02 hedge detector tightened: phrases only (not single words); `should`/`might`/`could` removed to avoid RFC 2119 collision; canonical phrase list expanded to 21 entries.
  - REQ-006-03 / 04 / 05 operational tests added: speculative, aspirational, specific are now defined with checkable boolean conditions.
  - REQ-006-09 pre-mortem checks converted from open questions to binary PASS/FAIL with explicit pass conditions.
  - REQ-006-11 partial completion AC added (gap from v1).
  - REQ-006-12 auto-mode behavior added (gap from v1).
  - REQ-006-13 kill criteria for Step 0 itself added (addresses critic's "no kill criteria" finding).
  - AC count: 10 → 13. ACs split static/dynamic where both apply.
  - DESIGN-006 Edit 1 expanded with hedge phrase list, operational tests, halt message schema, kill criteria reference.
  - DESIGN-006 Edit 4 expanded with binary check phrasing.
  - DESIGN-006 Testing Strategy expanded from 8 manual checks to 13 dynamic + 2 static with coverage tracker.
  - TASK-006-8 expanded from 2 cases to 13 + lint integration.
  - Effort estimate updated 6.5-7.5h → 9-11h.
