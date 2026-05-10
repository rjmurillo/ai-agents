---
type: requirement
id: REQ-008
title: Add Step 0.5 Memory-First Gate to spec pipeline
status: draft
priority: P1
category: functional
epic: spec-pipeline-quality
related:
  - DESIGN-008
  - TASK-008
  - REQ-006
  - DESIGN-006
  - TASK-006
tags:
  - issue-1951
  - issue-1952
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
revision_history:
  - 2026-05-09 v1: Initial draft from issue #1951
  - 2026-05-09 v2: Resolved GAP-01 through GAP-08 from analyst review
  - 2026-05-09 v3: Q4 wedge revised per Step 9 check 9c; auto-mode blast-radius threshold raised to 3
---

# REQ-008: Add Step 0.5 Memory-First Gate to spec pipeline

## Step 0 First Principles

**Q1 Demand Reality**: Three named systems: (1) `/spec` command at `.claude/commands/spec.md` cannot enforce backward-looking gate without invoking memory skills; (2) memory skill at `.claude/skills/memory/SKILL.md` declares Memory-First Gate as BLOCKING but `/spec` never invokes it; (3) Epic #1952 explicitly lists Step 0.5 Memory-First Gate as Phase 1 child #1951.

**Q2 Status Quo**: `/spec` has Step 0 First Principles Gate only. The memory skill declares Memory-First Gate as BLOCKING but `/spec` never invokes it. Proposers either manually recall prior decisions (lossy) or skip recall entirely. A spec can pass Step 0 with concrete demand answers but still propose removing an ADR constraint without searching for the ADR.

**Q3 Desperate Specificity**: `/spec` command at `.claude/commands/spec.md`. Blocked on enforcing backward-looking elicitation between Step 0 and Step 1. Proposers have no command-driven prompt to surface prior art before clarification begins.

**Q4 Narrowest Wedge**: Add Step 0.5 section to `.claude/commands/spec.md` between Step 0 and Step 1, invoking chestertons-fence, memory, and exploring-knowledge-graph in sequence. Tier-gated depth. Includes gate infrastructure: halt criteria with machine-readable halt block (step0_5-halt), entity adjudication workflow, metrics tally (STEP-0.5-METRICS.md), and supplemental traversal hook for cross-step tier upgrades. Approximately 4-8 hours.

**Q4 Revision note (Step 9 check 9c)**: Original wedge described only the three skill invocations. Step 9 critic flagged AC-08/09/10/11 as scope beyond "three skill calls." Revised to include gate infrastructure (halt, adjudication, metrics, supplemental) because these are inherent to any blocking gate. Step 0 has equivalent infrastructure (H1-H5, STEP-0-METRICS.md).

**Q5 Observation**: the "Memory-First Gate (BLOCKING)" section in `.claude/skills/memory/SKILL.md` declares "Memory-First Gate (BLOCKING)". `.claude/commands/spec.md` has no string "memory" skill invocation. Parent Epic #1952 body cites gap. `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` documents cost pattern.

**Q6 Future-fit**: Memory grows, so traversal becomes more valuable over time. Tier-gating prevents over-exploration. No 10x liability.

## Problem

`.claude/commands/spec.md` lacks a backward-looking gate between Step 0 (demand validation) and Step 1 (clarification). A proposer whose Step 0 passes can draft a spec that violates prior ADR constraints or Chesterton's Fence invariants stored in memory. Step 0.5 closes this gap by invoking three composed skills in sequence before clarification begins.

Success metric: every spec that reaches Step 1 has a populated "## Prior Art / Constraints" section and Step 9 check 9d confirms it.

## Evidence

The gap is directly observable in two artifacts. First, the "Memory-First Gate (BLOCKING)" section in `.claude/skills/memory/SKILL.md` reads "Memory-First Gate (BLOCKING)" but the memory skill is never referenced anywhere in `.claude/commands/spec.md`. The invocation exists in the skill but the spec command never calls it. Second, `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` Phase 6 documents 69 commits and 11+ review rounds on PR #1887 where the M4 evidence rule was designed against an imagined contract instead of the canonical `validate_session_json.py:CONTRADICTION_PATTERNS` regex. That failure is precisely the failure Step 0.5 prevents: the proposer did not search for the canonical source before writing the spec.

Epic #1952 cites Step 0.5 Memory-First Gate as Phase 1 child issue #1951, confirming the gap was planned for closure.

## User Stories

1. As the `/spec` command, when Step 0 passes, I invoke Step 0.5 before Step 1 so that prior art is surfaced before clarification begins.
2. As a proposer using `/spec`, when Step 0.5 completes, I see a structured "## Prior Art / Constraints" block so that I can make informed decisions about ADR constraints and connected entities before writing requirements.
3. As an orchestrator agent invoking `/spec` in auto-mode, when Step 0.5 runs, the three searches execute automatically and halt only when human judgment is required, so that automated workflows are not unnecessarily blocked by mechanical searches.
4. As Step 9 (skeptical critic), when validating the PRD, I find a non-empty "## Prior Art / Constraints" section so that I can confirm backward-looking elicitation occurred.

## Data Model

### Step05Gate

Per-invocation entity. State transitions: PENDING to RUNNING to PASS or HALT. Invariant: HALT fires when any halt criterion is satisfied. Fields: invocation timestamp, ProvisionalTier computed at start, final state, trigger ID if HALT, check ID if HALT.

### step0_5-halt block

Value object. Five fields: `trigger` (H6-H11), `check` (AC ID), `evidence` (proposer-supplied), `test_failed` (the criterion that triggered halt), `deferral` (instruction for the proposer). Info-string: "step0_5-halt". Emitted in the session output when any of the six halt triggers fires. Not persisted beyond the session.

### PriorArtBlock

Value object embedded in the PRD. Three required subsections: "### Direct prior art from memory" (results from memory search), "### Connected context from exploring-knowledge-graph" (entities discovered), "### Coverage notes" (topics with zero hits, Forgetful degradation log). Absence of any subsection fails Step 9 check 9d. A coverage note satisfies the non-empty requirement for a subsection that produced no results.

### ProvisionalTier

Integer 1 through 5. Computed as max(hours_tier(Q4), entity_tier(Q3+Q4)). Determined at the start of Step 0.5 without user input.

Hours extraction from Q4 free-text: the agent looks for a numeric estimate followed by "hour", "hours", "h", "hr", "hrs", "day", "days", "week", or "weeks" (case-insensitive). Days multiply by 8. Weeks multiply by 40. If no numeric estimate is found, ProvisionalTier defaults to Tier 2.

Hours mapping (upper bounds are strict less-than, so 8h falls in Tier 3, not Tier 2): less than 2 hours = Tier 1; 2 hours to less than 8 hours = Tier 2; 8 hours to less than 40 hours = Tier 3; 40 hours to less than 160 hours = Tier 4; 160 hours or more = Tier 5.

Entity count mapping: 1 entity = Tier 1; 2-3 entities = Tier 2; 4-7 entities = Tier 3; 8-15 entities = Tier 4; more than 15 entities = Tier 5.

**Cross-reference**: Step 0 halt criteria H1-H5 are defined in DESIGN-006. If those criteria change, AC-01's precondition ("Step 0 passes") changes accordingly.

### STEP-0.5-METRICS.md

Singleton file at `.agents/sessions/STEP-0.5-METRICS.md`. One tally line per invocation. Format per line: `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>`. Rotate at 100 entries. Absence of the file does not block `/spec`. Used to evaluate kill criteria at 30 invocations.

## Integrations

### chestertons-fence

Invoked via `Skill(skill="chestertons-fence")` with `target` set to the Q3 system path and `change` set to the Q4 wedge description. Purpose: surfaces git archaeology and ADR/PR history for the target system. Failure mode: if the skill is unavailable, log the skip in coverage notes and continue. Idempotent.

### memory / search_memory.py

Invoked for each topic derived from Step 0 Q3+Q4 named entities, using at minimum 3 distinct query variants per topic. Runs through the memory skill interface.

**Topic definition** (search scope): one topic per distinct named entity, file, or system component mentioned in the proposer's Q3 and Q4 answers.

The TOPIC SOURCE for memory and chestertons-fence searches is intentionally narrower than the ADJUDICATION SOURCE for AC-08 auto-mode classification. Topics drive what to search (the thing being changed plus the blocked target); adjudication compares discovered entities against Q1+Q3+Q4 because Q1 names known-good demand sources (requesters, declared dependencies) that should auto-resolve `in-scope`. The two scopes serve different purposes; the asymmetry is by design, not a bug. Normalization rule (applied in order): (1) strip leading path separators (`/`, `\`) and leading dots (`.`); (2) lowercase the string; (3) trim leading and trailing whitespace; (4) collapse internal separator runs (whitespace, `-`, `_`) to a single hyphen so `spec pipeline`, `spec-pipeline`, and `spec_pipeline` all normalize to `spec-pipeline`. For example, `.claude/commands/spec.md` normalizes to `claude/commands/spec.md` (rule 1 strips the leading dot); this is a different topic from `spec-pipeline`. The agent lists the derived topics explicitly in the Step 0.5 preamble before running any searches. Auto-mode adjudication (AC-08) compares discovered entity names against Q answers using the same normalization.

If Forgetful MCP is unavailable, degrade to Serena-only search and log the degradation in coverage notes. If a topic returns 0 results after 3+ distinct queries, emit a coverage note for that topic. Idempotent.

### exploring-knowledge-graph

Invoked via `Skill(skill="exploring-knowledge-graph")` at depth matching ProvisionalTier. Tier 1-2: Phases 1-2 (shallow). Tier 3: Phases 1-4 (medium). Tier 4-5: Phases 1-5 (deep). If Forgetful MCP is unavailable, skip and log in coverage notes. Idempotent.

## Failure Modes

| Failure | Behavior |
|---|---|
| Forgetful MCP unavailable | Degrade to Serena-only memory search, skip exploring-knowledge-graph, log degradation in coverage notes, continue without halting |
| chestertons-fence unavailable | Log skip in coverage notes, continue |
| memory returns 0 hits for a topic | Emit coverage note per topic; not a halt trigger |
| ProvisionalTier underestimates actual | After Step 3 classifies actual tier as higher, run additional knowledge-graph phases per the AC-10 trigger formula and append results as a `### Supplemental (Phase N)` sub-block to PriorArtBlock; original content preserved |
| Proposer marks 2+ entities as blast-radius | H11 halt; proposer revises Q4 or adds explicit out-of-scope entries, then re-runs Step 0.5; on re-run the PriorArtBlock is rebuilt from scratch; STEP-0.5-METRICS.md appends a second tally line |
| Spec proposes a Memory-First BLOCKING change type and search returns no prior art | H6-H10 halt per AC-13 (matched against the "Investigation Protocol" change-type table in `.claude/skills/memory/SKILL.md`); proposer cites prior art or revises the proposal, then re-runs Step 0.5 |
| Proposer ignores halt and proceeds to Step 1 | Step 9 check 9d FAIL; spec REJECTED |
| METRICS.md reaches 100 entries | Rotate: rename to STEP-0.5-METRICS-YYYYMMDD.md, create fresh file with header; absence of rotation does not block /spec |

## Security

Internal system data only. Proposers MUST NOT include secrets, credentials, or PII in Q3+Q4 entity names; halt-block redaction for inadvertent inclusion is tracked as a hardening follow-on in #1975 (Sec F4).

**Topic input is author-controlled, not trusted.** Q3+Q4 entity names flow into topic strings that the agent passes to `search_memory.py` (AC-04). Spec.md mandates argv-vector subprocess invocation (`subprocess.run([..., topic], shell=False)`) to defend against CWE-78 OS Command Injection because topic normalization does not strip shell metacharacters. If the agent cannot use argv-vector invocation in its environment, the spec requires rejecting any topic matching `[^\w\-\./ ]` and emitting a coverage note.

The gate makes no external network calls beyond the existing memory skill infrastructure.

## Observability

- `STEP-0.5-METRICS.md`: one tally line per invocation; format `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>`.
- Step 9 check 9d: verifies that the PRD contains a "## Prior Art / Constraints" section with at least one sub-section that has evidence content or a justified coverage note.
- Session logs show memory search queries and results appearing before any requirement decisions.

## Acceptance Criteria

### AC-01: Step 0.5 precedes Step 1

WHEN a `/spec` invocation's Step 0 passes,
THE SYSTEM SHALL invoke Step 0.5 before Step 1,
SO THAT backward-looking context is surfaced before clarification begins.

### AC-02: ProvisionalTier computed without user input

WHEN Step 0.5 begins,
THE SYSTEM SHALL compute ProvisionalTier as max(hours_tier(Q4), entity_tier(Q3+Q4)) using the defined mapping tables,
SO THAT knowledge-graph depth is calibrated without user input.

### AC-03: chestertons-fence invoked for target system

WHEN Step 0.5 begins,
THE SYSTEM SHALL invoke chestertons-fence with target=Q3 system path and change=Q4 wedge description,
SO THAT git archaeology and ADR/PR history for the target system is surfaced.

### AC-04: memory searched with minimum 3 query variants per topic

WHEN Step 0.5 begins,
THE SYSTEM SHALL invoke memory via search_memory.py for each topic derived from Step 0 Q3+Q4 named entities using at minimum 3 distinct query variants per topic,
SO THAT relevant prior decisions, episodes, and causal patterns are identified.

### AC-05: exploring-knowledge-graph depth matches ProvisionalTier

WHEN Step 0.5 begins,
THE SYSTEM SHALL invoke exploring-knowledge-graph at depth matching ProvisionalTier (Tier 1-2: Phases 1-2; Tier 3: Phases 1-4; Tier 4-5: Phases 1-5),
SO THAT connected entities not named in Step 0 are discovered.

### AC-06: Zero-result topic emits coverage note

WHEN memory returns 0 results for a topic after at minimum 3 distinct queries,
THE SYSTEM SHALL emit a coverage note for that topic in PriorArtBlock,
SO THAT absence of evidence is distinguished from evidence of absence.

### AC-07: External skill or MCP unavailability degrades gracefully

WHEN Forgetful MCP is unavailable OR chestertons-fence skill is unavailable,
THE SYSTEM SHALL log the unavailability in coverage notes and continue without halting (Forgetful unavailable: degrade to Serena-only for memory, skip exploring-knowledge-graph; chestertons-fence unavailable: log skip),
SO THAT connectivity or skill failures do not block the gate.

### AC-08: Discovered entities require adjudication

WHEN exploring-knowledge-graph discovers an entity or project not named in Step 0 Q1+Q3+Q4,
THE SYSTEM SHALL present it to the proposer for adjudication (in-scope, out-of-scope, or blast-radius),
SO THAT the proposer explicitly acknowledges or excludes discovered connections.

**Auto-mode adjudication rule**: when running in auto-mode (no human present), the agent performs case-insensitive string matching of the discovered entity name against the normalized Q1+Q3+Q4 answers. A match resolves the entity as in-scope. No match resolves it as blast-radius (conservative). This makes auto-mode deterministic and auditable. A human proposer may override blast-radius classifications that the auto-mode conservatively assigned.

**Auto-mode blast-radius threshold**: in auto-mode, the blast-radius halt threshold is 3 entities (not 2). This reduces false halts for automated pipelines where Tier 3+ traversals commonly discover 2+ unmatched entities. Human-mode retains the 2-entity threshold from AC-09.

### AC-09: Two or more blast-radius entities trigger halt (H11)

WHEN the proposer marks 2 or more discovered entities as blast-radius (human mode) OR the auto-mode adjudication resolves 3 or more entities as blast-radius,
THE SYSTEM SHALL emit a step0_5-halt block with trigger H11 and deferral "Revise Step 0 Q4 to name blast-radius entities or add explicit out-of-scope entries; then re-run Step 0.5.",
SO THAT specs with underspecified blast radius cannot proceed to Step 1.

### AC-10: Supplemental traversal appended on tier upgrade

WHEN Step 3 classifies the actual tier higher than ProvisionalTier AND `phases_needed(actual_tier) > phases_needed(provisional_tier)`,
THE SYSTEM SHALL run the additional knowledge-graph phases and append results as a `### Supplemental (Phase N)` sub-block to PriorArtBlock without replacing the original subsections,
SO THAT deeper context is added without discarding shallower results.

The trigger formula is the canonical AC source. `phases_needed(T) = 2` if T<=2, `4` if T=3, `5` if T>=4. Examples: provisional=2, actual=3 fires Phases 3-4 as supplemental; provisional=2, actual=4 fires Phases 3-5; provisional=3, actual=4 fires Phase 5 alone; provisional=2, actual=2 does not fire.

### AC-11: Metrics tally appended on every invocation

WHEN Step 0.5 completes (pass or halt),
THE SYSTEM SHALL append one line to `.agents/sessions/STEP-0.5-METRICS.md` with format `<ISO-8601> | <pass|fail> | <trigger-or-none> | <check-or-none>`,
SO THAT kill criteria can be evaluated at 30 invocations.

### AC-12: Step 9 check 9d verifies PriorArtBlock presence

WHEN Step 9 check 9d runs,
THE SYSTEM SHALL verify that the PRD contains a "## Prior Art / Constraints" section with at least one sub-section having either evidence content or a justified coverage note,
SO THAT backward-looking elicitation is confirmed before spec approval.

**Build-time guard (implementation-only)**: spec.md Step 9 check 9d FAIL clause adds a third condition (c) detecting the partial-implementation guard token `step0.5:incomplete-without-2b` inside the Step 0.5 block. This is NOT part of the AC-12 contract; it is a transient safety check covering the M2 commit 2A/2B split. Once 2B has landed and the guard string is removed from the Step 0.5 body, condition (c) is structurally inert (the guard cannot fire). The token continues to appear in the 9d documentation prose so the runtime check has a name to match; the prose itself is OUTSIDE the Step 0.5 block boundary that condition (c) scopes to.

### AC-13: Memory-First BLOCKING change types trigger halt (H6-H10)

WHEN the spec proposes any of the BLOCKING change types documented in the "Investigation Protocol" change-type table in `.claude/skills/memory/SKILL.md` AND the corresponding memory search returns no relevant prior art,
THE SYSTEM SHALL emit a step0_5-halt block with the matching trigger and a `check` field naming this AC:
- H6: remove an ADR constraint with no memory hit for the constraint name
- H7: bypass a documented protocol with no memory hit for the protocol name plus "why"
- H8: delete more than 100 lines of existing code with no memory hit for the component plus "purpose"
- H9: refactor a component flagged complex (cyclomatic > 10) with no memory hit for the component plus "edge case"
- H10: change behavior of a validator, linter, hook, or shared infrastructure component without prior-art citation in PriorArtBlock,
SO THAT specs that propose changes to load-bearing systems without consulting memory cannot proceed.

These five triggers honor the BLOCKING contract the "Memory-First Gate (BLOCKING)" section in `.claude/skills/memory/SKILL.md` declares. Coverage notes apply only when memory search runs against a non-BLOCKING change type and finds nothing. AC-09 (H11 blast-radius) is unaffected by this AC.

## Out of Scope

- Auto-classification heuristics beyond ProvisionalTier
- Modifying the memory skill, chestertons-fence skill, or exploring-knowledge-graph skill bodies
- Meta-router for skill invocation
- Cross-linking to front-gate-before-pipeline (issue #1927)
- (Removed; was previously listed as out-of-scope. Step 0.5 + Step 9 9d MUST mirror into `src/copilot-cli/skills/spec/SKILL.md` byte-identically per the existing `tests/commands/test_spec_step0.py::test_step0_block_identical` invariant and `test_spec_step0_5.py::test_step0_5_block_byte_identical_across_spec_and_skill`. Mirror is enforced by tests, not deferred.)
- Enforcing Step 0.5 compliance outside the `/spec` command

## Deferred

- Machine-readable auto-mode halt protocol (`STEP_0_5_REQUIRES_ELICITATION`). Owner: rjmurillo.
- Kill criteria review schedule for Step 0.5 itself. Owner: rjmurillo.
- Entity name normalization alias table for query generation. Owner: follow-on issue.

## Open Questions

| ID | Question | Recommendation | Owner |
|---|---|---|---|
| OQ-01 | Should ProvisionalTier computation be inline in spec.md or reference an external document? | Inline. The mapping tables are small and change infrequently. External reference adds indirection without benefit. | rjmurillo |
| OQ-02 | Which example spec should be used for the AC-12 end-to-end validation run? | Issue #1953 (the next planned spec). | Implementer |

## CVA Summary

N/A. Single use case at Tier 1-2 complexity. No variability identified that warrants abstraction.

## Rationale

Step 0 (REQ-006) validates that the spec addresses real demand. Step 0.5 validates that the spec does not collide with prior decisions already captured in memory. These are distinct gates: passing Step 0 means the demand is real; passing Step 0.5 means the proposer has searched for constraints that would change the design. A proposer who passes Step 0 but skips memory search can propose removing an ADR constraint without knowing the constraint exists. PR #1887 demonstrates the cost: 69 commits and 11 review rounds on a spec designed against an imagined contract.

The three-skill composition (chestertons-fence for git history, memory for episodic and causal patterns, exploring-knowledge-graph for connected entities) covers the three distinct prior-art failure modes: (1) code was changed for a reason the proposer does not know; (2) a prior decision was made that the proposer did not recall; (3) a connected entity exists that the proposer did not name in Step 0. Each skill addresses one failure mode. Composing them in sequence keeps the implementation in a single spec.md insertion point.

## Dependencies

- `.claude/commands/spec.md` must exist and be editable (it does; REQ-006 / TASK-006 added Step 0 to it).
- `.claude/skills/memory/SKILL.md` must exist (it does; no changes to this file).
- `.claude/skills/chestertons-fence/SKILL.md` must exist (verify at implementation start).
- `.claude/skills/exploring-knowledge-graph/SKILL.md` must exist (verify at implementation start).
- Step 0 gate (REQ-006 / DESIGN-006 / TASK-006) must already be present in `spec.md`; Step 0.5 inserts after it.
- No new CI workflow files or external services required.
