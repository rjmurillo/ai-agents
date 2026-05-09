---
type: design
id: DESIGN-006
title: Step 0 First Principles Gate for spec pipeline
status: draft
priority: P1
related:
  - REQ-006
tags:
  - issue-1926
adr:
  - ADR-060 (optional; see Open Questions)
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
---

# DESIGN-006: Step 0 First Principles Gate for spec pipeline

## Requirements Addressed

- REQ-006-01: Step 0 precedes Step 1 (AC-1a, AC-1b)
- REQ-006-02: Hedge phrase triggers halt (AC-2)
- REQ-006-03: Speculative Observation triggers halt. operational test (AC-3)
- REQ-006-04: Aspirational Demand Reality triggers halt. operational test (AC-4)
- REQ-006-05: Unnamed blocked entity triggers halt. operational test (AC-5)
- REQ-006-06: Pass produces structured Step 0 block (AC-6)
- REQ-006-07: requirements-interview does not re-elicit Step 0 (AC-7a, AC-7b)
- REQ-006-08: Tier 5 re-validates Step 0 instead of separate simplicity challenge (AC-8)
- REQ-006-09: Critic pre-mortem runs three binary Step 0 validity checks (AC-9)
- REQ-006-10: Copilot CLI file mirrors spec.md changes (AC-10)
- REQ-006-11: Partial completion triggers halt (AC-11)
- REQ-006-12: Auto-mode honors Step 0 without bypass (AC-12)
- REQ-006-13: Kill criteria for the gate itself (AC-13)

## Design Overview

Two markdown files receive prose edits. Parser-based pytest helpers are added under `tests/commands/` (test_spec_step0.py, test_lifecycle_command_drift.py, step0_parser.py) so the gate is validated deterministically at CI time. No new runtime scripts, schemas, or CI workflow files. All
behavior is embedded as human-readable instruction in `.claude/commands/spec.md`. The same edits
are mirrored to `src/copilot-cli/skills/spec/SKILL.md` so both platforms enforce the gate.
Complexity: Tier 1 (two markdown files, trivially reversible).

## Component Architecture

### Edit 1: Insert Step 0 block in `.claude/commands/spec.md` (before Step 1, at approximately line 15)

**Purpose**: Define the First Principles gate, its six questions, pass/fail criteria, structured
output format, and HALT directive.

**Responsibilities**:
- Present six labelled questions in sequence (Q1-Q6).
- Define the pass criteria: all six fields non-empty, no hedge phrase in any field, Q1/Q3/Q5 pass their operational tests.
- Embed the canonical Hedge Phrase List as a fenced table inside Step 0 prose (copy from REQ-006 Context section verbatim). Multi-word phrases only. Include the explicit note that single-word "should," "might," "could" are not hedges (RFC 2119 conflict).
- Embed the operational tests for "speculative" (REQ-006-03), "aspirational" (REQ-006-04), and "specific" (REQ-006-05) as fenced rules. Each test must be expressed as a checkable boolean. State explicitly: "the model evaluates these tests against the author's answer; subjective judgment is replaced by the boolean conditions listed."
- Define five halt triggers (H1-H5) with IDs matching REQ-006 Context: (H1) hedge phrase match; (H2) Q5 fails speculative test; (H3) Q1 fails aspirational test; (H4) Q3 fails specificity test; (H5) partial completion.
- Embed the Halt Message Schema from REQ-006 Context (5 required fields).
- Define the HALT directive: when any trigger fires, emit the halt message per schema and do not proceed to Step 1.
- Define the structured output format when Step 0 passes: a fenced block labelled `## Step 0 First Principles` with six sub-fields (`### Q1 Demand Reality`, `### Q2 Status Quo`, `### Q3 Desperate Specificity`, `### Q4 Narrowest Wedge`, `### Q5 Observation`, `### Q6 Future-fit`), each containing the author's verbatim answer. This block becomes the first section of the PRD artifact.
- State auto-mode behavior (REQ-006-12): under auto-mode, halt with `STEP_0_REQUIRES_ELICITATION` and return to orchestrator. Free-form synthesis prohibited.
- State the kill criteria reference (REQ-006-13): "Step 0 is subject to review at 30 invocations against kill criteria documented in REQ-006-13. A tally is kept in `.agents/sessions/STEP-0-METRICS.md` (one line per invocation). Absence of the file does not block `/spec`."

**Interfaces**:
- Input: `/spec` invocation with problem statement.
- Output: Step 0 block (on pass) or HALT message with failing question cited (on fail).
- Downstream: Step 0 block is referenced by Step 1 (narrowing scope), Step 2 (input context),
  Step 3 Tier 5 (re-validation), and Step 9 (validity checks).

**Six questions (canonical text)**:

| Label | Question |
|-------|----------|
| Q1 Demand Reality | Have three or more real people or systems explicitly requested this, or does real production data show the gap? Name them or cite the data. |
| Q2 Status Quo | What is the exact workaround users do today, step by step? |
| Q3 Desperate Specificity | Name the single most blocked person or system right now. What exactly are they blocked on? |
| Q4 Narrowest Wedge | What is the smallest possible deliverable that unblocks Q3, measured in hours of implementation? |
| Q5 Observation | What have you directly observed (not predicted) that proves demand? Quote or cite. |
| Q6 Future-fit | If the system grows 10x, does this feature still make sense, or does it become a liability? |

---

### Edit 2: Narrow Step 1 scope in `.claude/commands/spec.md`

**Purpose**: Step 1 previously covered general problem clarification. After Step 0, the author has
already answered the "why" questions. Step 1 narrows to constraints, edge cases, and integration
surface only.

**Responsibilities**:
- Update Step 1 prose to state that problem motivation is already captured in the Step 0 block.
- Restrict Step 1 questions to: constraints, non-functional requirements, integration touch points,
  and edge cases not already covered by the Step 0 Narrowest Wedge.
- Add a reference: "Step 0 output is the problem statement. Do not re-elicit Q1-Q6 here."

---

### Edit 3: Update Step 3 Tier 5 bullet in `.claude/commands/spec.md`

**Purpose**: Remove the standalone "why not simpler?" challenge from Tier 5 and replace it with a
reference to Step 0 re-validation.

**Before** (exact text to replace):
```
Explicit why not simpler? challenge. If complexity can be driven out, do it before specifying.
```

**After**:
```
Re-validate Step 0 Q4 (Narrowest Wedge) in the context of emerged complexity. If the wedge can
be narrowed further without losing the unblocking value, narrow it before proceeding.
```

**Rationale**: Step 0 Q4 already forces the narrowest deliverable. At Tier 5, the implementer
re-reads the Q4 answer against the now-understood complexity. This is a tighter check than the
open-ended "why not simpler?" challenge, because it has a specific answer to validate against.

---

### Edit 4: Add three Step 0 validity checks to Step 9 critic pre-mortem in `.claude/commands/spec.md`

**Purpose**: The critic's pre-mortem gains three checks that verify Step 0 claims held through
the full spec process.

**New checks to append to Step 9 pre-mortem list (each is a binary PASS/FAIL assertion, not an open question)**:

1. **Check 9a. Demand Reality drift**:
   - PASS condition: the PRD's acceptance criteria, user stories, OR success metric reference at least one entity (person, team, system, metric, ticket, file path) that was named in Q1.
   - FAIL otherwise.
   - On FAIL: cite the Q1 entities and the PRD's current entities verbatim.

2. **Check 9b. Desperate Specificity drift**:
   - PASS condition: the PRD's user stories or acceptance criteria still treat the Q3-named blocked entity as the primary unblocking target.
   - FAIL if (a) the spec's primary user shifted to a different audience, OR (b) Q3's named entity does not appear anywhere in the PRD.
   - On FAIL: cite Q3's entity and the PRD's current primary user verbatim.

3. **Check 9c. Narrowest Wedge drift**:
   - PASS condition: every PRD acceptance criterion either traces to the Q4 wedge or narrows it.
   - FAIL if any acceptance criterion adds scope beyond the Q4 wedge without a documented wedge revision.
   - On FAIL: cite Q4 verbatim and list the AC entries that exceed the wedge.

If any of 9a, 9b, 9c FAILs, the critic emits the failure as a blocking finding with the cited Q1/Q3/Q4 quote and the drifted PRD content. The critic's verdict cannot be APPROVED while any Step 0 check is FAIL.

---

### Edit 5: Mirror all body changes to `src/copilot-cli/skills/spec/SKILL.md`

**Purpose**: The Copilot CLI twin must enforce the same gate.

**Responsibilities**:
- Apply identical prose insertions and replacements to `src/copilot-cli/skills/spec/SKILL.md`.
- Preserve SKILL.md frontmatter unchanged (name, version, description fields).
- Verify that the diff between the two files' bodies is zero after editing.

---

### Optional Edit 6: Write ADR-060

**Purpose**: Record the architectural decision to add a blocking front gate to the spec pipeline.

**Location**: `.agents/architecture/ADR-060-spec-step0-first-principles-gate.md`

**Content outline**:
- Status: Proposed
- Context: Specs proceeding on aspirational demand; downstream cost of undiscovered invalid demand.
- Decision: Insert a six-question First Principles gate as Step 0 before clarification begins.
- Consequences: One additional conversation turn per spec invocation; specs that should not be
  written are halted before any downstream cost is incurred.
- Alternatives considered: Post-hoc demand validation (critic only); demand checklist embedded in
  Step 1 without halt semantics.

---

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Implementation medium | Markdown prose edits | No scripts, schemas, or CI changes needed. Tier 1 complexity. |
| Halt enforcement | Instruction-level (prose directive) | The spec command is interpreted by Claude Code; the gate is enforced by the model following the instruction, not by a validator. Consistent with how all other spec steps are enforced. |
| Hedge phrase check | Case-insensitive multi-word phrase list | Simple, deterministic, author-visible. No regex. Multi-word only. single-word "should," "might," "could" excluded to avoid RFC 2119 collision (rejected substring approach from v1 after review). |
| "Speculative," "aspirational," "specific" definitions | Operational tests with checkable boolean conditions | Replaces subjective judgment with reproducible model-checkable rules. Rejected v1's undefined terminology after review flagged 3 CRITICAL gaps (analyst report 2026-05-09). |
| Pre-mortem check format | Binary PASS/FAIL with explicit pass conditions | Replaces open-ended questions with assertions. Rejected v1 phrasing after review flagged 3 checks were not testable. |
| Kill criteria | False-positive rate, bypass rate, abandonment, no-catches at 30 invocations | The gate is itself subject to its own logic. if it fails to deliver value, it is removed. Wedge-narrowing applies to Step 0 itself. |
| Step 0 output format | Fenced markdown block with Q1-Q6 labels | Machine-readable by downstream agents; human-readable in PRD artifact. |
| Copilot CLI sync | Manual mirror at implementation time | No build tooling for cross-file sync exists. Diff check at PR review is the verification mechanism. |

## Security Considerations

No new attack surface. No secrets, PII, or auth boundary changes. This is a process-level prose
edit to two markdown instruction files. The gate does not execute code, make network calls, or
read system state.

## Testing Strategy

Parser-based automated tests under `tests/commands/` (Tier 1 complexity); LLM-dependent cases remain documented manual spot-checks. The static checks below are encoded in the same pytest module:

### Static checks (grep / diff)

- **Static-1 (AC-1a, AC-7a, AC-7b, AC-8, AC-13)**: a shell one-liner that asserts: `Step 0` heading appears before `Step 1` heading in `.claude/commands/spec.md`; `Q1-Q6` and `Step 0` appear in the Step 1 paragraph (the "Clarify the problem" item, where the "Do not re-elicit Q1-Q6 here" directive lives); `why not simpler?` is absent from the Tier 5 bullet AND `Re-validate Step 0 Q4` is present; `STEP-0-METRICS.md` OR `kill criteria` appears in Step 0 prose.
- **Static-2 (AC-10)**: `diff` of the four edited sections between `.claude/commands/spec.md` and `src/copilot-cli/skills/spec/SKILL.md` returns zero.

### Dynamic verification (run /spec end-to-end against scripted inputs)

Each test case provides specific Step 0 answers and asserts the expected outcome.

**T1 (AC-2 hedge phrase)**: Q3 answer = "stakeholders want a faster gate." Expect: H1 halt, message cites Q3 and quotes "stakeholders want."

**T2 (AC-2 RFC 2119 non-trigger)**: Q5 answer = "The system should fail fast per ADR-007; observed 3 timeouts in PR #1234." Expect: PASS. single word "should" alone is not a hedge.

**T3 (AC-3 speculative)**: Q5 answer = "users find this slow." Expect: H2 halt, no quote, no citation, no named person.

**T4 (AC-3 non-speculative)**: Q5 answer = "Issue #1887 retro line 305 says framework misses dominant failure modes." Expect: PASS. citation present.

**T5 (AC-4 aspirational)**: Q1 answer = "users would want this." Expect: H3 halt, future tense + generic.

**T6 (AC-4 non-aspirational)**: Q1 answer = "Three teams (Bleu, Delos, Calc) escalated KeyVault deploy failures in #1700, #1820, #1850." Expect: PASS.

**T7 (AC-5 generic)**: Q3 answer = "engineers in general." Expect: H4 halt.

**T8 (AC-5 specific)**: Q3 answer = "Felix on the Bleu/Delos rotation, blocked on KeyVault deploys, three times last week." Expect: PASS.

**T9 (AC-6 pass-through)**: All six fields valid. Expect: structured `## Step 0 First Principles` block as first PRD section, with six `### Q1..Q6` subheads.

**T10 (AC-9 binary)**: Tier 3+ spec where PRD acceptance criteria reference a different blocked entity than Q3. Expect: Check 9b FAILs, critic emits blocking finding with both entities cited.

**T11 (AC-11 partial)**: Q1, Q2, Q3 answered; Q4-Q6 empty. Expect: H5 halt listing Q4, Q5, Q6 as missing.

**T12 (AC-12 auto-mode)**: `/spec` invoked auto-mode with no human, source artifact lacks Step 0 fields. Expect: `STEP_0_REQUIRES_ELICITATION` halt with all six question numbers.

**T13 (AC-12 auto-mode populated)**: `/spec` invoked auto-mode with source artifact containing all six Step 0 fields. Expect: PASS, fields populated verbatim.

### Coverage tracker

| AC | Static check | Dynamic test |
|---|---|---|
| AC-1a | Static-1 |. |
| AC-1b |. | T9 |
| AC-2 |. | T1, T2 |
| AC-3 |. | T3, T4 |
| AC-4 |. | T5, T6 |
| AC-5 |. | T7, T8 |
| AC-6 |. | T9 |
| AC-7a, AC-7b | Static-1 |. |
| AC-8 | Static-1 |. |
| AC-9 |. | T10 |
| AC-10 | Static-2 |. |
| AC-11 |. | T11 |
| AC-12 |. | T12, T13 |
| AC-13 | Static-1 |. |

## Open Questions

| Question | Owner | Resolution trigger |
|---|---|---|
| ADR-060: Is a blocking front gate on the spec pipeline architecturally significant enough to warrant a record? Lean yes. | Implementer | Decision at implementation start; write ADR-060 if yes. |
| Does `src/copilot-cli/skills/memory/spec/skill-specification.xml` duplicate spec body content requiring a mirror update? | Implementer | Read file at implementation start; update if yes. |
