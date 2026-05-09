---
type: requirement
id: REQ-006
title: Add Step 0 First Principles Gate to spec pipeline
status: draft
priority: P1
category: developer-experience
epic: spec-pipeline-quality
related:
  - DESIGN-006
  - TASK-006
tags:
  - issue-1926
author: spec-agent
created: 2026-05-09
updated: 2026-05-09
revision_history:
  - 2026-05-09 v1: Initial draft from issue #1926
  - 2026-05-09 v2: Evidence section added; hedge detector tightened; speculative/aspirational defined operationally; pre-mortem checks converted to binary; ACs added for H5, auto-mode, kill criteria
---

# REQ-006: Add Step 0 First Principles Gate to spec pipeline

## Problem

`.claude/commands/spec.md` (and its Copilot CLI twin `src/copilot-cli/skills/spec/SKILL.md`) proceeds directly to problem clarification without asking whether the work should be done at all. Engineers and agents invest clarification, design, and implementation effort in features driven by aspirational demand, predicted needs, and undefined blocked users. Inserting a six-question First Principles gate as Step 0 blocks specification work unless the author demonstrates real demand before any downstream steps run.

Success metric: specifications that reach Step 1 have a named, specific blocked user or system, a documented status quo workaround, and at least one concrete observation (not a prediction).

## Evidence (retrospective audit, 2026-05-09)

The Step 0 hypothesis was tested against `.agents/retrospective/` for the prior 6 months. Nine retros document spec work that proceeded on aspirational demand, ballooned beyond the narrowest wedge, or shipped with unverified premises. Each case is mapped to which Step 0 question would have caught it.

| Case | Retrospective | Question | Quote | Cost |
|---|---|---|---|---|
| 1 | `2026-05-05-pr-1887-iteration-paradox.md` Phase 6 | Q1, Q5 | "A separate retrospective question. 'is the M2-M5 framework worth building at all if its design space misses the dominant failure modes?'. is out of scope for this retro." | 69 commits, 11+ review rounds; framework solves a real problem but not *the* problem |
| 2 | `2026-05-05-pr-1887-iteration-paradox.md` Phase 6 | Q5 | "this PR's iteration cost was driven by multi-bot-reviewer concurrency and pagination-cliff masking, not by the RCA's named failure modes... The RCA picked failure modes it could quantify; the expensive failure modes resist quantification" | RCA #1884 anchored on observable-but-non-dominant failure modes |
| 3 | `2025-12-15-drift-detection-disaster.md` | Q1 | "Inverted source of truth: Modified Claude to match templates, which is backwards" | Premise inverted from day one; user escalation, context overflow |
| 4 | `2026-01-03-adr-workflow-bypass.md` | Q1, Q5 | ADR-039 created without delegation; skipped multi-agent workflow | Orphaned 10KB file; session 128 incomplete; work repeated |
| 5 | `2026-01-03-adr-generation-quality.md` | Q5 | "Unverified release dates, pricing, phantom statistics ('290 sessions analyzed' with no evidence)" | Factual errors in architecture decisions |
| 6 | `2025-12-19-self-contained-agents.md` | Q3, Q4 | Scope ballooned 18→36 files mid-implementation; agent changes affect 4 platforms (72 files) | 18 unplanned files; repeated fix commits |
| 7 | `2025-12-24-memory-split-failure.md` | Q3, Q6 | Background agent created 16 of 49 files; no checkpoint, no kill criteria | CI blocked; manual revert |
| 8 | `2025-12-15-instruction-files-gap.md` | Q3 | CLAUDE.md mixed user+contributor content; no named target user | Re-documentation required |
| 9 | `2025-12-26-prd-planning-workflow.md` | Q3, Q5 | "11/17 tasks flagged for revision, but no iteration happened; prompts assumed 'Process-SinglePR' exists unverified" | 11 tasks shipped on unverified assumptions |

Coverage: Q1 surfaces 3 cases; Q3 surfaces 4 cases; Q4 surfaces 3 cases; Q5 surfaces 3 cases; Q6 surfaces 1 case; Q2 surfaces 1 case (PR #1897 same-root-cause contradiction). Every case has at least one Step 0 question that, asked before specification, would have caught the failure or narrowed the scope.

The strongest single citation is PR #1887 Phase 6: the retro itself names the question Step 0 asks ("is the framework worth building at all if its design space misses the dominant failure modes?") and explicitly defers it as out of scope. That deferral landed after 69 commits. Step 0 makes the deferral impossible.

## Requirement Statements

### REQ-006-01: Step 0 precedes Step 1

WHEN `/spec` is invoked
THE SYSTEM SHALL present Step 0 before Step 1, with all six forcing questions (Demand Reality, Status Quo, Desperate Specificity, Narrowest Wedge, Observation, Future-fit)
SO THAT no clarification work begins on unvalidated demand.

### REQ-006-02: Hedge phrase triggers halt

WHEN any Step 0 answer contains a hedge phrase from the canonical list (Section: Hedge Phrase List) as a case-insensitive **word-boundary** match
THE SYSTEM SHALL halt and cite the specific question that failed and quote the matched phrase
SO THAT premature specs are blocked at the gate without false-positive halts on RFC 2119 requirement language.

The hedge check applies only to author-supplied answers, not to system-generated prompt text or instruction quotations. The list is mostly multi-word phrases plus a few unambiguous single-word entries (`probably`, `eventually`, `someday`). Single words "should," "might," and "could" in isolation are excluded from the list because they conflict with RFC 2119. The hyphenated technical term `eventually-consistent` is exempted via a suffix-table lookup (`HEDGE_TECHNICAL_SUFFIXES` in `tests/commands/step0_parser.py`).

### REQ-006-03: Speculative Observation triggers halt (operational test)

WHEN Question 5 (Observation) is speculative as defined by the operational test below
THE SYSTEM SHALL halt and cite Question 5 as the failing gate
SO THAT specs driven by prediction are blocked.

**Operational test for "speculative" (all three conditions must be false for Q5 to pass)**:
1. The answer contains a direct quote (text in `"..."` or fenced block) from a ticket, message, comment, log, or document.
2. The answer cites a metric, log entry, file path, commit SHA, PR number, or named artifact.
3. The answer names a specific person, team, or system that described the problem.

If none of (1), (2), (3) is present, Q5 is speculative.

### REQ-006-04: Aspirational Demand Reality triggers halt (operational test)

WHEN Question 1 (Demand Reality) is aspirational as defined by the operational test below
THE SYSTEM SHALL halt, cite Question 1 as the failing gate, and document the deferral in the session output
SO THAT aspirational demand does not consume specification resources.

**Operational test for "aspirational" (any one of the three conditions makes Q1 aspirational)**:
1. The answer names fewer than three specific requesters (people, teams, systems, or data sources). Q1 explicitly asks for three or more; a single named requester or "two teams" is not enough.
2. The answer uses future tense or conditional mood about demand existence (examples: "users would want," "if customers start," "when we have," "would be useful").
3. The answer is generic ("users in general," "engineers," "the team," "stakeholders," "developers").

### REQ-006-05: Unnamed blocked entity triggers halt (operational test)

WHEN Question 3 (Desperate Specificity) does not name a specific blocked entity as defined by the operational test below
THE SYSTEM SHALL halt and cite Question 3 as the failing gate
SO THAT premature specs are blocked.

**Operational test for "specific" (the answer must satisfy at least one)**:
1. A named individual ("Alice on the Payments team").
2. A named team ("the Bleu/Delos rotation," "the SRE on-call").
3. A uniquely identified system or component with a version, environment, or instance qualifier ("the auth service in prod-east," "the GraphQL pagination in `get_pr_review_threads.py`").

Generic categories ("users," "engineers," "the mobile app users") fail this test.

### REQ-006-06: Pass produces structured Step 0 block

WHEN Step 0 passes (all six fields non-empty and no hedge language in any field)
THE SYSTEM SHALL produce a structured block containing all six fields as the first section of the PRD
SO THAT downstream steps consume validated demand context.

### REQ-006-07: requirements-interview does not re-elicit Step 0 questions

WHEN Step 2 (requirements-interview) runs
THE SYSTEM SHALL receive Step 0 output
AND SHALL NOT re-elicit any of the six Step 0 questions
SO THAT authors are not asked the same questions twice.

### REQ-006-08: Tier 5 re-validates Step 0 instead of separate simplicity challenge

WHEN the complexity tier is Tier 5
THE SYSTEM SHALL re-validate Step 0 outputs in the context of emerged complexity instead of running a separate "why not simpler?" check
SO THAT Step 0 is the single gate for this question across all tiers.

### REQ-006-09: Critic pre-mortem runs three binary Step 0 validity checks

WHEN Step 9 (critic pre-mortem) runs
THE SYSTEM SHALL execute three binary checks against the final PRD and emit PASS or FAIL for each
SO THAT Step 0 violations surface before the spec ships.

**Check 9a (Demand Reality drift)**:
- PASS: the PRD's acceptance criteria, user stories, OR success metric reference at least one entity (person, team, system, metric, ticket) that was named in Q1.
- FAIL otherwise.

**Check 9b (Desperate Specificity drift)**:
- PASS: the PRD's user stories or acceptance criteria still treat the Q3-named blocked entity as the primary unblocking target.
- FAIL if the spec's primary user shifted to a different audience, OR Q3's named entity no longer appears in the PRD.

**Check 9c (Narrowest Wedge drift)**:
- PASS: the PRD's scope (acceptance criteria + user stories) is bounded by the Q4 wedge. every requirement traces to or narrows the wedge.
- FAIL if any acceptance criterion adds scope beyond the wedge without the wedge being formally widened in a documented revision.

If any of 9a, 9b, 9c FAILs, the critic SHALL surface the failure as a blocking finding with the specific Q1/Q3/Q4 quote that drifted.

### REQ-006-10: Copilot CLI file mirrors spec.md changes

WHEN `.claude/commands/spec.md` is updated
THE SYSTEM SHALL also update `src/copilot-cli/skills/spec/SKILL.md` with the same body changes
SO THAT both platforms stay in sync.

The body delta applied to `src/copilot-cli/skills/spec/SKILL.md` SHALL be byte-identical to the delta applied to `.claude/commands/spec.md` for the four edited sections (Step 0 insertion, Step 1 narrowing, Step 3 Tier 5 replacement, Step 9 pre-mortem additions). Frontmatter is preserved unchanged.

### REQ-006-11: Partial completion triggers halt

WHEN fewer than all six Step 0 questions have non-empty answers
THE SYSTEM SHALL halt and cite the missing question numbers
SO THAT incomplete Step 0 blocks do not propagate downstream.

### REQ-006-12: Auto-mode honors Step 0 without bypass

WHEN `/spec` is invoked under auto-mode (no human elicitation possible)
THE SYSTEM SHALL halt and return to the orchestrator with reason `STEP_0_REQUIRES_ELICITATION`, naming each question that needs an answer
SO THAT auto-mode invocations cannot bypass Step 0 by default.

The auto-mode halt MAY be resolved by populating Step 0 answers from the source artifact (issue body, PR description) when the source artifact contains the required structured fields. Free-form synthesis of Step 0 answers by the agent is prohibited.

### REQ-006-13: Kill criteria for the gate itself

WHEN Step 0 has been live for 30 invocations
THE SYSTEM SHALL be reviewed against the kill criteria below; if any criterion fires, the gate is loosened or removed in a follow-up PR
SO THAT a gate that produces more friction than value is not retained indefinitely.

**Kill criteria (any single criterion is sufficient grounds to revisit)**:
1. False-positive rate: ≥30% of halts are followed by re-invocation with cosmetic word changes that do not alter the underlying answer's meaning.
2. Bypass rate: ≥20% of `/spec` invocations skip Step 0 via documented exception.
3. Author abandonment: ≥3 spec sessions in a 7-day window are abandoned at Step 0 without a follow-up invocation.
4. No catches: 30 consecutive Step 0 evaluations pass on first attempt with no halts triggered (gate may be set too loose; not a kill but a recalibration trigger).

Measurement: a tally is kept in `.agents/sessions/STEP-0-METRICS.md` (one line per invocation: timestamp, pass/fail, halt reason if any). Tally is review-only; absence of the file does not block `/spec`.

## Context

The spec pipeline (`.claude/commands/spec.md`) currently opens with problem clarification (Step 1). Engineers and AI agents frequently skip "why are we doing this?" and proceed directly to "what should it do?". First Principles thinking. applied as a gate, not a retrospective. forces the author to answer six specific questions before spending any downstream resources. The gate pattern mirrors Elon Musk's five-step algorithm (question the requirement first) and the YC "desperate specificity" heuristic.

### Hedge Phrase List (canonical, REQ-006-02)

Multi-word phrases only. Single words "should," "might," "could" are excluded because they conflict with RFC 2119 requirement language. Substring match is case-insensitive. Applied only to author answers, not to system prompts or quoted instruction text.

| Phrase | Why it hedges |
|---|---|
| `would be nice` | aspirational |
| `would be useful` | aspirational |
| `would be helpful` | aspirational |
| `we believe` | belief, not observation |
| `we expect` | prediction, not observation |
| `we anticipate` | prediction, not observation |
| `we predict` | prediction, not observation |
| `we hope` | aspiration |
| `we assume` | assumption, not evidence |
| `stakeholders want` | unnamed audience |
| `users want` | unnamed audience |
| `customers want` | unnamed audience |
| `should we` | self-questioning, not commitment |
| `might be useful` | speculation |
| `might be needed` | speculation |
| `could be useful` | speculation |
| `probably` (standalone word) | hedging |
| `eventually` | indefinite future |
| `someday` | indefinite future |
| `down the road` | indefinite future |
| `nice to have` | low-priority aspiration |

Authors who need RFC 2119 "should" semantics in a Step 0 answer are using the wrong field; Step 0 is for evidence and demand, not for requirement strength.

### Halt Triggers (canonical)

1. **H1**: any answer contains a phrase from the Hedge Phrase List (REQ-006-02).
2. **H2**: Question 5 (Observation) fails the speculative test (REQ-006-03).
3. **H3**: Question 1 (Demand Reality) fails the aspirational test (REQ-006-04).
4. **H4**: Question 3 (Desperate Specificity) fails the specificity test (REQ-006-05).
5. **H5**: Partial completion. fewer than all six questions answered (REQ-006-11).

### Halt Message Schema

When any trigger fires, the halt message MUST contain:
1. The trigger ID (H1-H5).
2. The failing question number and label (e.g., `Q3 Desperate Specificity`).
3. The author's failing answer (verbatim, or the matched hedge phrase).
4. The operational test that failed (the rule from REQ-006-02 through REQ-006-05 that was violated).
5. A single-line deferral instruction (e.g., "Re-invoke `/spec` after naming a specific blocked entity.").

### Auto-mode Behavior

Auto-mode invocations cannot bypass Step 0. If no human is available for elicitation, the agent SHALL halt with reason `STEP_0_REQUIRES_ELICITATION` and return to the orchestrator. The agent MAY populate Step 0 from the source artifact (issue body, PR description) only when the source artifact contains the required structured fields verbatim; free-form synthesis is prohibited (REQ-006-12).

## Acceptance Criteria

Each AC is split into static (file-level) and dynamic (session-level) checks where both apply. Static checks are verifiable by `diff` or `grep`; dynamic checks are verifiable by running `/spec` end-to-end.

- [ ] **AC-1a (static)**: The Step 0 heading appears in `.claude/commands/spec.md` before any "Step 1" heading. Verifiable by byte-offset comparison.
- [ ] **AC-1b (dynamic)**: When `/spec` is invoked, the model presents Q1-Q6 to the author before any Step 1 prose. Verifiable by session transcript inspection.
- [ ] **AC-2**: When any Step 0 answer contains a hedge phrase from the canonical list (REQ-006-02), the halt message contains H1 plus the failing question number, the matched phrase quoted verbatim, and the deferral instruction.
- [ ] **AC-3**: When Q5 fails the operational speculative test (REQ-006-03), the halt message contains H2 plus Q5, the failing answer, and the specific test condition that failed (no quote, no citation, no named person).
- [ ] **AC-4**: When Q1 fails the operational aspirational test (REQ-006-04), the halt message contains H3 plus Q1, the failing answer, and the specific condition that failed (no named entity, future tense, OR generic category).
- [ ] **AC-5**: When Q3 fails the operational specificity test (REQ-006-05), the halt message contains H4 plus Q3, the failing answer, and the specific test branch that failed.
- [ ] **AC-6 (dynamic)**: When Step 0 passes, the PRD artifact's first section is `## Step 0 First Principles` with six labelled subfields (`### Q1 Demand Reality`, `### Q2 Status Quo`, etc.) each containing the author's verbatim answer.
- [ ] **AC-7a (static)**: `.claude/commands/spec.md` Step 1 prose (item "1. Clarify the problem") contains the directive "Do not re-elicit Q1-Q6 here." (or semantically equivalent text grep-verifiable as `Q1-Q6` in Step 1).
- [ ] **AC-7b (static)**: `.claude/commands/spec.md` Step 1 prose references the Step 0 block by name (grep `Step 0` in Step 1 paragraph).
- [ ] **AC-8 (static)**: `.claude/commands/spec.md` Tier 5 bullet does NOT contain the phrase "why not simpler?" AND DOES contain the phrase "Re-validate Step 0 Q4". Both verifiable by grep.
- [ ] **AC-9**: Step 9 prose contains three labelled checks (Check 9a, 9b, 9c) each phrased as a binary PASS/FAIL assertion per REQ-006-09. Each check has explicit pass conditions.
- [ ] **AC-10 (static)**: The body delta applied to `src/copilot-cli/skills/spec/SKILL.md` is byte-identical to the delta applied to `.claude/commands/spec.md` for the four edited sections. Verifiable by `diff` of the two files restricted to the edited sections.
- [ ] **AC-11**: When fewer than 6 of the Step 0 fields are answered, the halt message contains H5 plus the list of missing question numbers.
- [ ] **AC-12 (dynamic)**: When `/spec` is invoked under auto-mode without a human, the agent halts with `STEP_0_REQUIRES_ELICITATION` reason and lists each unanswered question. Free-form synthesis of answers is prohibited.
- [ ] **AC-13**: Step 0 instruction text in `.claude/commands/spec.md` references the kill criteria in REQ-006-13 (grep `STEP-0-METRICS.md` OR `kill criteria`).

## Rationale

Specifications are expensive. A spec that proceeds on aspirational demand consumes clarification time (Step 1-2), design time (Step 3-7), and review time (Step 9) before anyone discovers the work should not be done. Blocking at Step 0 costs one conversation turn and saves all downstream effort when the gate fires. The gate is applied symmetrically to human invocations and auto-agent invocations, ensuring the process controls hold regardless of the invoker.

### Why not narrow to a single question

A reviewer challenge: ship Q3 alone with one halt trigger; expand if observed value warrants. This was rejected because the retrospective evidence (9 cases) shows different questions catch different failure modes:
- Q3 alone would catch cases 6, 7, 8, 9 (4 of 9).
- Q1+Q3+Q5 would catch cases 1, 2, 3, 4, 5, 6, 8, 9 (8 of 9).
- All six are needed to catch case 1 (PR #1887, where Q1+Q5 are both load-bearing).

The kill criteria in REQ-006-13 provide the wedge-narrowing escape valve: if 30 invocations show ≥30% false positives or no catches, the gate is loosened or removed. The wedge is in the kill criteria, not in the question count.

### Why operational tests over judgment

The first review of REQ-006 v1 flagged "speculative" and "aspirational" as undefined and untestable. The operational tests in REQ-006-03, REQ-006-04, and REQ-006-05 replace judgment with checkable conditions: presence of a quote, presence of a citation, presence of a named entity, presence of future tense. These are model-checkable without subjective interpretation. The cost is occasional false positives on edge cases (a Q1 answer that names a system but uses future tense for the impact); the benefit is reproducibility across authors and agents.

## Dependencies

- `.claude/commands/spec.md` must exist and be editable (it does).
- `src/copilot-cli/skills/spec/SKILL.md` must exist and be editable (verify at implementation start).
- No new scripts, CI changes, or external services required.
- Optional: ADR-060 to record the architectural decision of a blocking front gate on the spec pipeline.
