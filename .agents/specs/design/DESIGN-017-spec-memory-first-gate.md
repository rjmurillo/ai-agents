---
type: design
id: DESIGN-017
title: Step 0.5 Memory-First Gate for spec pipeline
status: draft
priority: P1
related:
  - REQ-008
  - TASK-008
  - DESIGN-006
  - REQ-006
tags:
  - issue-1951
  - issue-1952
adr: []
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
---

# DESIGN-017: Step 0.5 Memory-First Gate for spec pipeline

## Requirements Addressed

- REQ-008-AC-01: Step 0.5 precedes Step 1
- REQ-008-AC-02: ProvisionalTier computed without user input
- REQ-008-AC-03: chestertons-fence invoked for target system
- REQ-008-AC-04: memory searched with minimum 3 query variants per topic
- REQ-008-AC-05: exploring-knowledge-graph depth matches ProvisionalTier
- REQ-008-AC-06: Zero-result topic emits coverage note
- REQ-008-AC-07: Forgetful MCP unavailability degrades gracefully
- REQ-008-AC-08: Discovered entities require adjudication
- REQ-008-AC-09: Blast-radius entity count meets per-mode threshold (human: 2; auto: 3) triggers halt
- REQ-008-AC-10: Supplemental traversal (Phase N) appended on tier upgrade
- REQ-008-AC-11: Metrics tally appended on every invocation
- REQ-008-AC-12: Step 9 check 9d verifies PriorArtBlock presence
- REQ-008-AC-13: Memory-First BLOCKING change types trigger halt (H6-H10)

## Design Overview

One markdown file receives prose edits: `.claude/commands/spec.md`. A new Step 0.5 section inserts between Step 0 and Step 1. Parser-based pytest helpers are added under `tests/commands/` to validate static structure and the ProvisionalTier mapping logic deterministically. No new runtime scripts, CI workflow files, or external services. All behavior is embedded as human-readable instruction in `spec.md`; Claude Code interprets the instruction at invocation time and invokes the three skills in sequence.

## Architecture

### Insertion Point

Step 0.5 inserts at the position immediately after the closing delimiter of the Step 0 block and before the Step 1 heading in `.claude/commands/spec.md`. The Step 0 block was added by DESIGN-006 / TASK-006. Step 0.5 is a new numbered section following Step 0.

### Execution Flow

```
/spec invoked
   |
   v
Step 0 (First Principles Gate) -- HALT if any H1-H5 triggers ---> session end
   |
   | (pass)
   v
Step 0.5 (Memory-First Gate)
   |-- 1. Compute ProvisionalTier from Q4 hours estimate and entity count from Q3+Q4
   |-- 2. Invoke chestertons-fence(target=Q3 path, change=Q4 wedge)
   |-- 3. Invoke memory search: 3+ queries per named entity from Q3+Q4
   |-- 4. Invoke exploring-knowledge-graph at ProvisionalTier depth
   |-- 5. Present discovered entities for adjudication
   |-- 6. If blast-radius count meets per-mode threshold (human: 2, auto: 3), emit step0_5-halt block (H11), HALT
   |-- 7. Assemble PriorArtBlock from all results
   |-- 8. Append one line to STEP-0.5-METRICS.md
   |
   | (pass or single blast-radius)
   v
Step 1 (clarification)
   |
   ...
   v
Step 9 (critic pre-mortem)
   |-- check 9d: PriorArtBlock present and non-empty -> PASS/FAIL
```

### ProvisionalTier Computation

ProvisionalTier is computed at the start of Step 0.5 from two inputs available without user input: the Q4 hours estimate (extracted from the proposer's Q4 answer) and the entity count (count of named entities in Q3+Q4 answers).

Hours mapping table:

Upper bounds are strict less-than. 8h falls in Tier 3 (range `8 to less than 40 hours`), not Tier 2.

| Q4 estimate | Tier |
|---|---|
| Less than 2 hours | 1 |
| 2 to less than 8 hours | 2 |
| 8 to less than 40 hours | 3 |
| 40 to less than 160 hours | 4 |
| 160 hours or more | 5 |

Entity count mapping table:

| Named entities in Q3+Q4 | Tier |
|---|---|
| 1 | 1 |
| 2-3 | 2 |
| 4-7 | 3 |
| 8-15 | 4 |
| More than 15 | 5 |

**Canonical fallback rule** (single source of truth, matches REQ-008 hours extraction rule): when Q4 contains no parseable numeric hours estimate, set `hours_tier = 2`, then compute `ProvisionalTier = max(hours_tier, entity_tier)`. The agent records the omission in the PriorArtBlock coverage notes so implementers see that hours parsing failed; the fallback does NOT skip the `max()` step or use `entity_tier` alone.

### Knowledge-Graph Depth by Tier

| ProvisionalTier | exploring-knowledge-graph phases |
|---|---|
| 1-2 | Phases 1-2 (shallow: direct references) |
| 3 | Phases 1-4 (medium: transitive references) |
| 4-5 | Phases 1-5 (deep: full traversal) |

## Component Architecture

### Edit 1: Insert Step 0.5 block in `.claude/commands/spec.md` (after Step 0, before Step 1)

**Purpose**: Define the Memory-First Gate, its three-skill sequence, ProvisionalTier computation, halt triggers H6-H11 (H6-H10 per REQ-008 AC-13 mirror the documented BLOCKING change types in `.claude/skills/memory/SKILL.md` under the `### Investigation Protocol` BLOCKING change-types table; H11 per REQ-008 AC-09 covers blast-radius count), PriorArtBlock output format, and metrics tally directive.

**Responsibilities**:

- State the gate's purpose: surface prior art and constraints before clarification begins.
- Define ProvisionalTier computation (inline mapping tables as specified in REQ-008 Data Model). State that the computation is automatic and does not require user input.
- Define the three-skill invocation sequence:
  1. chestertons-fence with target=Q3 path and change=Q4 wedge.
  2. memory search: 3+ distinct query variants per named entity from Q3+Q4.
  3. exploring-knowledge-graph at depth matching ProvisionalTier.
- Define degradation behavior for each skill: if chestertons-fence is unavailable, log skip and continue; if Forgetful MCP is unavailable, degrade to Serena-only and log; if exploring-knowledge-graph is unavailable, skip and log.
- Define the entity adjudication step: present each discovered entity not in Q1+Q3+Q4 to the proposer; proposer assigns one of (in-scope, out-of-scope, blast-radius).
- Define halt trigger H11: when the blast-radius count meets or exceeds the per-mode threshold (human mode: 2; auto mode: 3, per REQ-008 AC-09), emit a step0_5-halt block with canonical deferral text "Revise Step 0 Q4 to name blast-radius entities or add explicit out-of-scope entries; then re-run Step 0.5." (capitalized R, terminating period; sole canonical form, mirrored verbatim by REQ-008 AC-09 line 191 and TASK-008 line 93).
- Define the step0_5-halt block schema: five fields (trigger, check, evidence, test_failed, deferral); info-string "step0_5-halt".
- Define zero-result coverage note: when memory returns 0 results for a topic after 3+ queries, emit a coverage note naming the topic in the "### Coverage notes" subsection.
- Define the PriorArtBlock output format: a markdown section "## Prior Art / Constraints" with three required subsections: "### Direct prior art from memory", "### Connected context from exploring-knowledge-graph", "### Coverage notes". This block is appended to the PRD immediately after the Step 0 block.
- Define the supplemental traversal rule: when Step 3 classifies actual tier as higher than ProvisionalTier and `phases_needed(actual_tier) > phases_needed(provisional_tier)`, run the additional phases and append a `### Supplemental (Phase N)` sub-block to the existing PriorArtBlock. The original content is preserved; do not replace it. The trigger fires for tier upgrades that cross any phase boundary, not only tier 4+ (e.g., provisional=2 actual=3 runs Phases 3-4; provisional=3 actual=4 runs Phase 5 alone).
- Define the metrics tally directive: on every Step 0.5 completion (pass or halt), append one line to `.agents/sessions/STEP-0.5-METRICS.md` with format `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>`. Absence of the file does not block `/spec`.

**Interfaces**:
- Input: Step 0 block (Q1-Q6 answers from the proposer).
- Output: PriorArtBlock embedded in the PRD (on pass) or step0_5-halt block (on H11 halt).
- Downstream: PriorArtBlock is read by Step 9 check 9d.

**Auto-mode behavior**: In auto-mode (no human available for adjudication), the three mechanical searches run automatically. Entity adjudication halts only when human judgment is required. If all discovered entities are clearly in-scope or out-of-scope by name match to Q1+Q3+Q4, auto-mode continues without halting. If adjudication is ambiguous, auto-mode emits the discovered entities and waits for the orchestrator.

---

### Edit 2: Add Step 9 check 9d in `.claude/commands/spec.md`

**Purpose**: The critic's pre-mortem gains a fourth check that confirms backward-looking elicitation occurred. This check adds to the existing checks 9a, 9b, 9c introduced by DESIGN-006 Edit 4.

**New check to append to Step 9 pre-mortem list**:

```
- **Check 9d. Prior Art / Constraints elicitation**:
  - PASS: the PRD contains a "## Prior Art / Constraints" section with at least one sub-section
    ("### Direct prior art from memory", "### Connected context from exploring-knowledge-graph",
    or "### Coverage notes") that has either evidence content or a justified coverage note.
  - FAIL: the section is absent, or all sub-sections are empty with no coverage note.
  - On FAIL: surface as a blocking finding. The critic cannot return APPROVED while check 9d is FAIL.
```

**Rationale**: An empty PriorArtBlock is operationally equivalent to skipping Step 0.5. The check makes that observable at critic time and prevents the gap from reaching merge.

---

## Sequence Diagram

```
proposer         spec.md         chestertons-fence   memory       exploring-kg
   |                |                   |               |               |
   |-- /spec ------>|                   |               |               |
   |<-- Step 0 -----|                   |               |               |
   |-- answers ---->|                   |               |               |
   |                |-- compute tier -->|               |               |
   |                |-- invoke -------->|               |               |
   |                |<-- fence results -|               |               |
   |                |-- 3+ queries per entity --------->|               |
   |                |<-- memory results ----------------|               |
   |                |-- invoke at ProvisionalTier depth --------------->|
   |                |<-- entity graph ----------------------------------|
   |<-- adjudicate entities (if any new ones) ---|                     |
   |-- adjudication -->|                         |                     |
   |                |-- check blast-radius count  |                     |
   |                |   threshold (human=2, auto=3)|                    |
   |                |                             |                     |
   |                | [HALT branch: count >= threshold]                 |
   |                |-- emit step0_5-halt H11 ----->|                   |
   |<-- step0_5-halt deferral text ---|            |                   |
   |                |-- append metrics tally (fail|H11|AC-09) --->     |
   |                |-- STOP; do not proceed to Step 1                  |
   |                |                             |                     |
   |                | [PASS branch: count < threshold]                  |
   |                |-- assemble PriorArtBlock    |                     |
   |                |-- append metrics tally (pass|none|none) --->      |
   |<-- PriorArtBlock + proceed to Step 1 --------|                    |
```

## Edit Sites

The following sections of `.claude/commands/spec.md` are added or modified.

### New section: Step 0.5 (insert after Step 0 closing delimiter, before Step 1 heading)

Full prose of Step 0.5 gate including:
- Stated purpose
- ProvisionalTier computation (inline mapping tables)
- Three-skill invocation sequence with degradation rules
- Entity adjudication protocol
- H11 halt trigger and step0_5-halt block schema
- Zero-result coverage note rule
- PriorArtBlock output format (three subsections)
- Supplemental traversal rule (`### Supplemental (Phase N)` sub-block)
- Metrics tally directive

### Modified section: Step 9 pre-mortem list (append check 9d after check 9c)

Check 9d as defined in Edit 2 above.

## Output Schema

### PriorArtBlock (embedded in PRD)

```markdown
## Prior Art / Constraints

### Direct prior art from memory

<one or more memory search results, keyed by topic entity>
<or: coverage note if 0 results after 3+ queries>

### Connected context from exploring-knowledge-graph

<entities discovered beyond Q1+Q3+Q4, with adjudication decisions>
<or: "No new entities discovered." if graph traversal found nothing beyond named entities>
<or: coverage note if Forgetful was unavailable>

### Coverage notes

<one entry per: topic with 0 memory hits, skill unavailability, Forgetful degradation>
<or: "None." if no degradation occurred and all topics returned results>
```

### step0_5-halt block (emitted on H6-H11)

Canonical fenced format (info-string `step0_5-halt`, exactly 5 fields in this order: `trigger`, `check`, `evidence`, `test_failed`, `deferral`; one `key: value` pair per line; the `parse_halt_block` helper at `tests/commands/step0_5_parser.py` enforces this shape):

````
```step0_5-halt
trigger: H11
check: AC-09
evidence: <proposer-supplied entity adjudication list>
test_failed: blast-radius count >= per-mode threshold (human: 2; auto: 3)
deferral: Revise Step 0 Q4 to name blast-radius entities or add explicit out-of-scope entries; then re-run Step 0.5.
```
````

### STEP-0.5-METRICS.md line format

Canonical UTC timestamp form `YYYY-MM-DDTHH:MM:SSZ` (no offset, no fractional seconds; the `parse_tally_line` helper enforces this exact shape):

```
<YYYY-MM-DDTHH:MM:SSZ> | <pass|fail> | <trigger-or-none> | <check-or-none>
```

Example pass line: `2026-05-09T14:32:00Z | pass | none | none`

Example halt lines:
- `2026-05-09T14:35:12Z | fail | H11 | AC-09` (blast-radius)
- `2026-05-09T14:42:08Z | fail | H6 | AC-13 memory-first BLOCKING change type` (memory-first)

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Implementation medium | Markdown prose edits to spec.md | No scripts, schemas, or CI changes needed. Consistent with DESIGN-006 approach. Tier 2 complexity. |
| Skill invocation protocol | `Skill(skill="...")` calls in instruction prose | Consistent with how the spec pipeline invokes other skills (requirements-interview, decision-critic). No meta-router added. |
| ProvisionalTier computation | Inline in spec.md prose with mapping tables | Tables are small, stable, and need to be visible to the proposer. External reference adds indirection without benefit (OQ-01 resolved inline). |
| Degradation policy | Continue on skill unavailability, log in coverage notes | Availability failure should not block demand validation. Proposer gets visibility via coverage notes. |
| Halt trigger set | H6-H11 (six triggers) | H6-H10 mirror the documented BLOCKING change types in `.claude/skills/memory/SKILL.md` under the `### Investigation Protocol` BLOCKING change-types table: H6 (remove ADR constraint with no memory hit), H7 (bypass protocol with no memory hit), H8 (delete >100 lines with no memory hit), H9 (refactor complex code with no memory hit), H10 (change validator/linter/hook/shared infra with no prior-art citation). H11 (blast-radius count) handles spec scope underspecification. The five memory-first triggers honor the BLOCKING contract memory/SKILL.md declares; without them the gate becomes advisory rather than blocking. Coverage notes still apply when search runs and finds nothing for non-BLOCKING change types. |
| Entity adjudication | Proposer assigns in-scope/out-of-scope/blast-radius | Adjudication requires judgment the model cannot supply alone. Auto-mode resolves unambiguous cases by name match and waits only on ambiguous ones. |
| Metrics tally | Append-only flat file at .agents/sessions/ | Consistent with STEP-0-METRICS.md approach from DESIGN-006. No database or structured store needed at this volume. |
| Step 9 check | Check 9d binary PASS/FAIL | Consistent with checks 9a/9b/9c from DESIGN-006. Binary assertions are auditable; open questions are not. |
| Copilot CLI twin | Updated as part of M4 implementation | Required to keep `tests/commands/test_spec_step0.py` byte-identity tests passing. Mirrored Step 0.5 + Step 9 9d into `src/copilot-cli/skills/spec/SKILL.md`. |

## Security Considerations

No new auth boundary or secret surface. No PII expected.

**Topic input is author-controlled and crosses a process boundary.** The gate passes proposer-supplied entity names to `search_memory.py` via subprocess invocation. This is a CWE-78 OS Command Injection surface unless the invocation uses an argv vector (not shell string concatenation). REQ-008 AC-04 and the corresponding spec.md prose mandate argv-vector subprocess (`shell=False`) and a topic-rejection regex `[^\w\-\./ ]` as a fallback when argv is unavailable. Treat topic strings as untrusted input; do not interpolate them into shell commands.

Step 0.5 invokes existing skills that already have their own security posture. Halt-block PII/secret redaction for proposer-supplied answers is deferred to #1975.

## Testing Strategy

### Static checks (grep / diff)

**Static-1 (AC-01)**: Assert that "Step 0.5" heading appears in `.claude/commands/spec.md` after the "Step 0" heading and before the "Step 1" heading. Verifiable by line-order check.

**Static-2 (AC-02)**: Assert that the ProvisionalTier mapping tables appear in the Step 0.5 section. Verifiable by grep for both mapping table headers.

**Static-3 (AC-11)**: Assert that "STEP-0.5-METRICS.md" appears in the Step 0.5 section. Verifiable by grep.

**Static-4 (AC-12)**: Assert that "check 9d" and "Prior Art / Constraints" appear in the Step 9 section. Verifiable by grep.

### Dynamic verification (run `/spec` end-to-end against scripted inputs)

**D1 (AC-01)**: Step 0 passes; assert Step 0.5 executes before proposer sees Step 1 questions.

**D2 (AC-02)**: Q4 = "4-6 hours"; Q3+Q4 entity count = 2. Assert ProvisionalTier = max(2, 2) = 2. Assert exploring-knowledge-graph runs at Phases 1-2.

**D3 (AC-03)**: Assert chestertons-fence is invoked with the Q3 path as target and Q4 wedge as change description.

**D4 (AC-04)**: Q3 names entity "spec.md". Assert at least 3 distinct memory queries for "spec.md" topic.

**D5 (AC-06)**: Memory returns 0 results for a topic. Assert coverage note present in PriorArtBlock "### Coverage notes" subsection.

**D6 (AC-07)**: Simulate Forgetful MCP unavailable. Assert Serena-only search runs, degradation logged in coverage notes, Step 0.5 completes without halting.

**D7 (AC-08)**: Graph traversal discovers entity "ADR-060" not in Q1+Q3+Q4. Assert proposer is prompted to adjudicate "ADR-060".

**D8 (AC-09)**: Proposer marks 3 entities as blast-radius. Assert step0_5-halt block emitted with trigger H11, deferral text present.

**D9 (AC-09 non-halt)**: Proposer marks 1 entity as blast-radius. Assert no halt; proposer proceeds to Step 1.

**D10 (AC-11)**: Step 0.5 passes. Assert one new line appended to `STEP-0.5-METRICS.md` with ISO-8601 timestamp and `pass`.

**D11 (AC-11 halt)**: H11 fires. Assert one new line appended with `fail | H11 | AC-09`.

**D12 (AC-12)**: Spec reaches Step 9. Assert PRD contains "## Prior Art / Constraints" section with at least one non-empty subsection. Check 9d reports PASS.

**D13 (AC-12 fail)**: Manually remove PriorArtBlock from PRD. Assert Step 9 check 9d reports FAIL as a blocking finding.

**D14 (AC-10)**: Q4 estimate = "3 days" (24 hours, Tier 3); entity count = 3 (Tier 2). ProvisionalTier = max(3, 2) = 3. Step 3 classifies tier as 4. Assert Phase 5 runs; "### Supplemental (Phase 5)" appended; original three subsections preserved. (Note: 2 weeks = 80 hours falls in Tier 4 via hours_tier alone, which would not exercise the AC-10 trigger condition; 3 days keeps the example targeting a tier upgrade across the Phase 4 → Phase 5 boundary.)

### Coverage tracker

| AC | Static check | Dynamic test |
|---|---|---|
| AC-01 | Static-1 | D1 |
| AC-02 | Static-2 | D2 |
| AC-03 | | D3 |
| AC-04 | | D4 |
| AC-05 | | D2 |
| AC-06 | | D5 |
| AC-07 | | D6 |
| AC-08 | | D7 |
| AC-09 | | D8, D9 |
| AC-10 | | D14 |
| AC-11 | Static-3 | D10, D11 |
| AC-12 | Static-4 | D12, D13 |
| AC-13 | | D15-D19 (one per H6-H10 trigger; tracked manual in #1972 LLM eval harness) |

## Open Questions

| ID | Question | Recommendation | Owner |
|---|---|---|---|
| OQ-01 | ProvisionalTier computation inline vs external reference. | Inline. Resolved: mapping tables are small and visible to proposer. | rjmurillo |
| OQ-02 | Which example spec for AC-12 end-to-end validation test. | Issue #1953. | Implementer |
