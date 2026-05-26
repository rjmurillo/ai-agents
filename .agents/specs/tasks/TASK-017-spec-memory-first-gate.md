---
type: task
id: TASK-017
title: Implement Step 0.5 Memory-First Gate in spec pipeline
status: todo
priority: P1
complexity: L
related:
  - DESIGN-008
  - REQ-008
tags:
  - issue-1951
  - issue-1952
blocked_by:
  - TASK-006
blocks: []
assignee: implementer
created: 2026-05-09
updated: 2026-05-09
---

# TASK-017: Implement Step 0.5 Memory-First Gate in spec pipeline

## Objective

Edit `.claude/commands/spec.md` to insert a Step 0.5 Memory-First Gate section between Step 0 and Step 1, and append check 9d to the Step 9 critic pre-mortem list. Add parser-based pytest helpers under `tests/commands/` for deterministic static validation. No new CI workflow files, runtime schemas, or external services.

## In Scope

- Insert Step 0.5 block in `.claude/commands/spec.md` after Step 0 and before Step 1
- Append check 9d to Step 9 pre-mortem list in `.claude/commands/spec.md`
- Add `tests/commands/test_spec_step0_5.py` with static structure tests
- Add or extend `tests/commands/step0_5_parser.py` with ProvisionalTier computation logic
- Manual validation run (halt case + pass case + degradation case)

## Out of Scope

- Modifying memory, chestertons-fence, or exploring-knowledge-graph skills
- (Removed; was previously listed as out-of-scope. Copilot CLI twin update for Step 0.5 + Step 9 9d is REQUIRED by byte-identity tests `test_step0_block_identical` and `test_step0_5_block_byte_identical_across_spec_and_skill`. Treat as in-scope mirror obligation, not deferred.)
- Meta-router for skill invocation
- Cross-linking to issue #1927
- Refactoring unrelated sections of `spec.md`
- Writing an ADR for this gate (deferred to follow-on if warranted)

---

## TASK-017-1: Verify prerequisite skill files exist

**Objective**: Confirm that chestertons-fence, memory, and exploring-knowledge-graph skills are present before inserting Step 0.5 prose that references them.

**Complexity**: XS (0.5 hours)

**Acceptance Criteria**:
- [ ] `.claude/skills/chestertons-fence/SKILL.md` exists and is readable.
- [ ] `.claude/skills/memory/SKILL.md` exists and is readable.
- [ ] `.claude/skills/exploring-knowledge-graph/SKILL.md` exists and is readable.
- [ ] Findings documented in the PR description (exists / path / any relevant version notes).

**Files Affected**:

| File | Action | Description |
|---|---|---|
| `.claude/skills/chestertons-fence/SKILL.md` | Read | Verify existence and note invocation interface |
| `.claude/skills/memory/SKILL.md` | Read | Verify existence; confirm line 104 "Memory-First Gate (BLOCKING)" observation |
| `.claude/skills/exploring-knowledge-graph/SKILL.md` | Read | Verify existence and note depth parameter interface |

**Implementation Notes**:
- If any skill is absent, halt and file a blocking comment on the PR before proceeding to TASK-017-2.
- Note the exact `Skill(skill="...")` invocation string for each skill as it appears in existing spec.md skill calls; use the same pattern in Step 0.5 prose.

---

## TASK-017-2: Insert Step 0.5 block in `.claude/commands/spec.md`

**Objective**: Add the Memory-First Gate as Step 0.5, positioned after the Step 0 closing delimiter and before the Step 1 heading.

**Complexity**: M (4-6 hours)

**Acceptance Criteria**:
- [ ] "Step 0.5" heading appears in `spec.md` after "Step 0" heading and before "Step 1" heading (AC-01).
- [ ] Step 0.5 states its purpose: surface prior art and constraints before clarification begins.
- [ ] ProvisionalTier computation is defined inline with both mapping tables (hours_tier and entity_tier) and the max() formula (AC-02).
- [ ] Three-skill invocation sequence is defined in order: (1) chestertons-fence, (2) memory search, (3) exploring-knowledge-graph (AC-03, AC-04, AC-05).
- [ ] Skill invocations use `Skill(skill="...")` syntax consistent with other skill calls in `spec.md`.
- [ ] Degradation rule for chestertons-fence is stated: log skip in coverage notes, continue (AC-07 partial).
- [ ] Degradation rule for Forgetful MCP unavailability is stated: Serena-only search, log degradation in coverage notes, continue (AC-07).
- [ ] Degradation rule for exploring-knowledge-graph unavailability is stated: skip and log in coverage notes.
- [ ] Memory search instruction states 3+ distinct query variants per named entity from Q3+Q4 (AC-04).
- [ ] exploring-knowledge-graph depth table is present: Tier 1-2 = Phases 1-2; Tier 3 = Phases 1-4; Tier 4-5 = Phases 1-5 (AC-05).
- [ ] Zero-result coverage note rule is stated: when memory returns 0 results for a topic after 3+ queries, emit a coverage note in the "### Coverage notes" subsection (AC-06).
- [ ] Entity adjudication protocol is defined: present each discovered entity not in Q1+Q3+Q4 to the proposer; proposer assigns in-scope, out-of-scope, or blast-radius (AC-08).
- [ ] H11 halt trigger is defined: when blast-radius count meets per-mode threshold (human mode: 2 or more; auto mode: 3 or more), emit step0_5-halt block (AC-09). Mode-specific threshold matches D8 dynamic check expectation (3 entities triggers in auto mode).
- [ ] H6-H10 halt triggers are defined: spec proposes a Memory-First BLOCKING change type from `.claude/skills/memory/SKILL.md` `### Investigation Protocol` BLOCKING change-types table AND memory search returns no prior art (AC-13). Each trigger has its own deferral instruction citing the BLOCKING type. Halt-block `check` field reads `AC-13 memory-first BLOCKING change type`.
- [ ] step0_5-halt block schema is defined: five fields (trigger, check, evidence, test_failed, deferral); info-string "step0_5-halt"; H11 deferral text reads: "Revise Step 0 Q4 to name blast-radius entities or add explicit out-of-scope entries; then re-run Step 0.5." (AC-09); H6-H10 deferral text instructs the proposer to cite memory, amend the spec, or escalate (AC-13).
- [ ] PriorArtBlock output format is defined with three subsections: "### Direct prior art from memory", "### Connected context from exploring-knowledge-graph", "### Coverage notes" (all ACs).
- [ ] Supplemental traversal rule is stated: when Step 3 classifies actual tier higher than ProvisionalTier and `phases_needed(actual_tier) > phases_needed(provisional_tier)`, run the additional phases and append a `### Supplemental (Phase N)` sub-block to PriorArtBlock without replacing original content (AC-10). Trigger fires for any tier upgrade that crosses a phase boundary, not just Phase 5.
- [ ] Metrics tally directive is stated: append one line to `.agents/sessions/STEP-0.5-METRICS.md` on every completion; format `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>`; absence of file does not block `/spec` (AC-11).
- [ ] "STEP-0.5-METRICS.md" string appears in Step 0.5 prose (supports Static-3 check).

**Files Affected**:

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | Edit | Insert Step 0.5 block after Step 0 closing delimiter, before Step 1 heading |

**Implementation Notes**:
- Read the current `spec.md` before editing to identify the exact line numbers for insertion.
- Do not modify Step 0, Step 1, or any other existing step in this task; changes to Step 9 are in TASK-017-3.
- Use a horizontal rule or clear heading boundary to delimit Step 0.5 from Step 1.
- The PriorArtBlock is embedded in the PRD artifact, not emitted inline during Step 0.5 prose. State this explicitly in the prose so implementers do not misread it as a console printout.
- ProvisionalTier must be presented as a computation the model performs on the Q3+Q4 answers, not a question asked of the proposer.

---

## TASK-017-3: Append check 9d to Step 9 pre-mortem in `.claude/commands/spec.md`

**Objective**: Add a fourth Step 9 check that confirms the PriorArtBlock is present and non-empty.

**Complexity**: XS (1 hour)

**Acceptance Criteria**:
- [ ] Step 9 pre-mortem list contains "Check 9d. Prior Art / Constraints elicitation" appended after "Check 9c" (AC-12).
- [ ] Check 9d is phrased as a binary PASS/FAIL assertion with explicit pass conditions (consistent with checks 9a/9b/9c).
- [ ] PASS condition: PRD contains "## Prior Art / Constraints" section with at least one sub-section that has evidence content or a justified coverage note.
- [ ] FAIL condition: section absent, or all sub-sections are empty with no coverage note.
- [ ] On FAIL: critic emits blocking finding; critic cannot return APPROVED while check 9d is FAIL.
- [ ] No existing checks (9a, 9b, 9c) are reordered or removed.

**Exact text for check 9d**:

```
- **Check 9d. Prior Art / Constraints elicitation**:
  - PASS: the PRD contains a "## Prior Art / Constraints" section with at least one sub-section
    ("### Direct prior art from memory", "### Connected context from exploring-knowledge-graph",
    or "### Coverage notes") that has either evidence content or a justified coverage note.
  - FAIL: the section is absent, or all sub-sections are empty with no coverage note.
  - On FAIL: surface as a blocking finding. The critic cannot return APPROVED while check 9d is FAIL.
```

**Files Affected**:

| File | Action | Description |
|---|---|---|
| `.claude/commands/spec.md` | Edit | Append check 9d to Step 9 pre-mortem list after check 9c |

**Implementation Notes**:
- Read Step 9 section before editing to confirm check 9c location.
- Append only; do not reformat or reorder existing checks.

---

## TASK-017-4: Add static validation tests

**Objective**: Add parser-based pytest tests that verify the structural requirements of the Step 0.5 insertion without requiring a live `/spec` invocation.

**Complexity**: S (2-4 hours)

**Acceptance Criteria**:
- [ ] `tests/commands/test_spec_step0_5.py` exists with at minimum the following test cases:
  - [ ] **S1**: "Step 0.5" heading appears in `spec.md` after "Step 0" heading and before "Step 1" heading.
  - [ ] **S2**: ProvisionalTier mapping tables (hours_tier and entity_tier) appear in the Step 0.5 section.
  - [ ] **S3**: "STEP-0.5-METRICS.md" string appears in the Step 0.5 section.
  - [ ] **S4**: "check 9d" and "Prior Art / Constraints" appear in the Step 9 section.
  - [ ] **S5**: "step0_5-halt" info-string appears in the Step 0.5 section.
  - [ ] **S6**: "H11" appears in the Step 0.5 section.
  - [ ] **S7**: All three skill names (chestertons-fence, memory, exploring-knowledge-graph) appear in the Step 0.5 section.
- [ ] `tests/commands/step0_5_parser.py` exists with a `compute_provisional_tier(q4_text, entity_count)` function that implements the mapping logic and is tested independently.
- [ ] Tests pass without a live Claude Code or MCP server; they operate on the file text only.
- [ ] Tests follow the AAA (Arrange, Act, Assert) pattern.
- [ ] Test names describe the behavior under test, not the implementation.

**Files Affected**:

| File | Action | Description |
|---|---|---|
| `tests/commands/test_spec_step0_5.py` | Create | Static structure tests for Step 0.5 insertion |
| `tests/commands/step0_5_parser.py` | Create | ProvisionalTier computation helper module |

**Implementation Notes**:
- Tests read `.claude/commands/spec.md` from a path relative to the repo root; use `pathlib.Path` for portability.
- `compute_provisional_tier` takes a raw Q4 text string and an entity count integer. It extracts an hours estimate from the text using simple pattern matching (look for numbers adjacent to "hour", "day", or "week" tokens; convert days to 8 hours, weeks to 40 hours). Returns an integer 1-5.
- Keep the parser module minimal. The production implementation is the model following prose instructions, not this module. The module's purpose is to provide a deterministic reference for test assertions.

---

## TASK-017-5: Manual validation run

**Objective**: Prove the halt case, pass case, and degradation case work in practice before merging.

**Complexity**: S (2-3 hours; 14 invocations per DESIGN-008 Testing Strategy)

**Acceptance Criteria**:
- [ ] **D1** (AC-01): Step 0 passes; Step 0.5 executes before proposer sees Step 1 questions.
- [ ] **D2** (AC-02, AC-05): Q4 = "4-6 hours"; entity count = 2. ProvisionalTier = 2; exploring-knowledge-graph runs Phases 1-2.
- [ ] **D3** (AC-03): chestertons-fence invoked with Q3 path as target and Q4 wedge as change description.
- [ ] **D4** (AC-04): Entity "spec.md" named in Q3. At least 3 distinct memory queries issued for topic "spec.md".
- [ ] **D5** (AC-06): Memory returns 0 results for a topic. Coverage note present in "### Coverage notes" subsection.
- [ ] **D6** (AC-07): Forgetful MCP simulated unavailable. Serena-only search runs; degradation logged in coverage notes; Step 0.5 completes.
- [ ] **D7** (AC-08): Graph traversal discovers entity not in Q1+Q3+Q4. Proposer prompted for adjudication.
- [ ] **D8** (AC-09 halt): Proposer marks 3 entities as blast-radius. step0_5-halt block emitted with H11; deferral text present.
- [ ] **D9** (AC-09 non-halt): Proposer marks 1 entity as blast-radius. No halt; proposer proceeds to Step 1.
- [ ] **D10** (AC-11 pass): Step 0.5 passes. One new line appended to `STEP-0.5-METRICS.md` with ISO-8601 and "pass".
- [ ] **D11** (AC-11 halt): H11 fires. One new line appended with "fail | H11 | AC-09".
- [ ] **D12** (AC-12 pass): PRD reaches Step 9. "## Prior Art / Constraints" section present with at least one non-empty subsection. Check 9d PASS.
- [ ] **D13** (AC-12 fail): PriorArtBlock manually removed from PRD. Step 9 check 9d FAIL emitted as blocking finding.
- [ ] **D14** (AC-10): Q4 estimate implies Tier 3; Step 3 classifies Tier 4. Phase 5 runs; "### Supplemental (Phase 5)" appended; original subsections preserved.
- [ ] Static-1: "Step 0.5" heading order check passes (grep or line-offset assertion).
- [ ] Static-2: "STEP-0.5-METRICS.md" appears in Step 0.5 section (grep).
- [ ] Static-3: "check 9d" and "Prior Art / Constraints" appear in Step 9 section (grep).
- [ ] Evidence (session transcript excerpts or screenshots) attached to the issue or PR comment.

**Files Affected**:

None (validation only; evidence documented in PR description).

---

## Testing Requirements

Static checks are encoded in `tests/commands/test_spec_step0_5.py` and run in the existing pytest suite. Dynamic spot-checks (D1-D14) require live `/spec` invocations and are documented as supplemental evidence in the PR description. Both layers are required before the PR is marked ready for review.

The ProvisionalTier reference implementation in `step0_5_parser.py` is tested with at minimum (boundaries are strictly less-than per REQ-008 hours mapping):
- `compute_provisional_tier("6 hours", 1)` returns 2. Hours: 6 falls in 2 to <8 = Tier 2. Entity: 1 = Tier 1. max(2, 1) = 2.
- `compute_provisional_tier("3 days", 5)` returns 3. Hours: 3 days = 24 hours, falls in 8 to <40 = Tier 3. Entity: 5 = Tier 3. max(3, 3) = 3.
- `compute_provisional_tier("vague description with no number", 10)` returns 4. Hours: no numeric match, defaults to Tier 2. Entity: 10 = Tier 4. max(2, 4) = 4.
- `compute_provisional_tier("2 weeks", 2)` returns 4. Hours: 2 weeks = 80 hours, falls in 40 to <160 = Tier 4. Entity: 2 = Tier 2. max(4, 2) = 4.

## Effort Estimate

| Task | Complexity | Hours |
|---|---|---|
| TASK-017-1 (Verify skill files exist) | XS | 0.5 |
| TASK-017-2 (Insert Step 0.5 block) | M | 4-6 |
| TASK-017-3 (Append check 9d) | XS | 1 |
| TASK-017-4 (Static validation tests) | S | 2-4 |
| TASK-017-5 (14 dynamic + 3 static validation) | S | 2-3 |
| **Total** | **L** | **9.5-14.5** |

## Revision History

- **v1 (2026-05-09)**: Initial draft from issue #1951.
