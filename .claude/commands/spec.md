---
description: Define what to build. Transform a problem into testable requirements with acceptance criteria.
allowed-tools: Task, Skill, Read, Write, Glob, Grep
argument-hint: [problem-statement-or-issue-number]
---

@CLAUDE.md

Spec: $ARGUMENTS

If $ARGUMENTS is empty, ask the user what problem to solve. Do not proceed without a problem statement.

## Process

1. Clarify the problem (what, who, why, constraints)
2. **Run the adversarial requirements interview**: Invoke Skill(skill="requirements-interview") to walk the design tree before any further analysis. The skill grills the user on user stories, data model, integrations, failure modes, security, observability, and scope boundaries. For every question it must propose a recommended answer; if the codebase can answer it (grep the repo first), it does so without asking. Output is a structured PRD that every downstream step consumes. Carry the PRD forward unchanged through steps 3-9; do not drop sections.
3. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md`. Using the structured PRD from step 2, classify the problem as Tier 1-5 based on scope, ambiguity, cross-team dependencies, and reversibility. Return the tier number, rationale, and recommended spec depth. Use this to calibrate remaining steps:
   - Tier 1-2 (Entry/Mid): Simple acceptance criteria. Skip CVA if single use case.
   - Tier 3 (Senior): CVA analysis required. Cross-team input. Design review gate.
   - Tier 4 (Staff): Alternatives analysis mandatory. ADR required. Stakeholder alignment. Challenge: "can this be decomposed into a simpler tier?"
   - Tier 5 (Principal): Governance review. Multi-org consensus. Explicit "why not simpler?" challenge. If complexity can be driven out, do it before specifying.
4. Search for existing solutions in the codebase (grep for related patterns). Use the PRD's Integrations and Data model sections to scope the search.
4a. **Buy-vs-build gate (BLOCKING for new capabilities)**: If the PRD proposes a new capability classified as Context (per Wardley/Moore: undifferentiating support work) or introduces a new module, scanner, validator, or pipeline component, invoke Skill(skill="buy-vs-build-framework") at the **Quick tier** (Phase 1 + Phase 2 lite) before continuing to step 5. The skill must produce: (a) a one-line core-vs-context classification, (b) the existing tools/services evaluated (CodeQL, Dependabot, gh CLI, OSS Scorecard, vendor SaaS, etc.), and (c) an explicit build/buy/partner/defer recommendation. **Skip this step only for**: pure bug fixes, doc-only changes, refactors with no new capability surface, or work that extends an already-approved capability without adding a new tool/scanner/validator. Record the gate outcome in the PRD under a new `Buy-vs-build decision` section. If the recommendation is buy/partner/defer, halt the spec and route the user to the recommended path before generating REQ/DESIGN/TASK artifacts. Failure pattern this gate prevents: action-matching to implementation skills (e.g., `security-detection`) without challenging the build decision itself, as in #1843 where 9 hours were spent reimplementing a CWE-22 scanner CodeQL already provides. See `.agents/retrospective/2026-05-06-action-matching-over-decision-gating.md`.
5. **CVA analysis (conditional)**: If the complexity tier is 3-5, or Tier 1-2 with multiple use cases, invoke Skill(skill="cva-analysis"): identify commonalities across the PRD's user stories, then variabilities, then relationships. Otherwise (Tier 1-2 single-use-case), set `CVA summary: N/A (single-use-case Tier 1-2)` and proceed.
6. **Formalize the PRD into durable artifacts**: Task(subagent_type="spec-generator"). Pass every PRD section from step 2 (Problem, User stories, Data model, Integrations, Failure modes, Security, Observability, Acceptance criteria, Out of scope, Deferred, Open questions) plus the complexity tier from step 3, the buy-vs-build decision from step 4a (which may be `N/A (bug fix / doc / refactor)` for skipped runs), and the CVA summary from step 5 (which may be the `N/A` placeholder for skipped runs). The spec-generator agent writes:
   - `.agents/specs/requirements/REQ-NNN-{slug}.md` (one per requirement, EARS syntax)
   - `.agents/specs/design/DESIGN-NNN-{slug}.md`
   - `.agents/specs/tasks/TASK-NNN-{slug}.md`
   The full PRD must be passed as input so spec-generator does not re-ask questions the interview already answered. Acceptance criteria use EARS syntax (`WHEN ... THE SYSTEM SHALL ... SO THAT ...`).
7. Task(subagent_type="analyst"): You are a requirements analyst. Your job is to find gaps, ambiguities, and untestable requirements. Review every PRD section, not just acceptance criteria. For each requirement, ask: can this be verified pass/fail? Flag anything vague.
8. Invoke Skill(skill="decision-critic"): challenge assumptions before committing
9. Task(subagent_type="critic"): You are a skeptical reviewer. Run a pre-mortem: assume this spec ships and fails. What broke first? What was missing?

## Evaluation Axes

1. **Problem clarity** - Is the right problem being solved? Could a reframing yield 10x impact?
2. **Requirement testability** - Can each requirement be verified pass/fail?
3. **Completeness** - No gaps between problem statement and acceptance criteria?
4. **Traceability** - REQ to DESIGN to TASK linkage established?
5. **Feasibility** - Buildable within constraints? Existing code to leverage?

## Principles

- **CVA**: Identify commonalities first, then variabilities, then relationships. Greatest risk is the wrong abstraction.
- **YAGNI**: Only specify what is needed now. Speculative requirements create waste.
- **Separation of Concerns**: Each requirement addresses one concern. Mixed concerns signal a missing decomposition.

- **Output schema**: Include a `Buy-vs-build decision` section recording: core-vs-context classification, alternatives evaluated, recommendation (build/buy/partner/defer), and rationale. Required for any spec that introduces a new capability; mark `N/A (bug fix / doc / refactor)` otherwise.

## Output

Structured requirements document. Mirror the PRD schema produced in step 2; do not collapse to acceptance criteria alone.

- **Problem statement** (1-2 sentences)
- **User stories** (who, action, observable outcome)
- **Data model** (entities, identity, invariants, lifecycle)
- **Integrations** (external systems, failure modes, idempotency)
- **Failure modes** (retries, partial failures, conflicts, replay, schema evolution)
- **Security** (authn, authz, secrets, PII, input validation)
- **Observability** (logs, metrics, traces, alerts)
- **Acceptance criteria** (numbered, EARS syntax, each independently testable as pass/fail)
- **Out of scope** (explicit exclusions to prevent creep)
- **Deferred** (decisions punted with owners)
- **Open questions** (unresolved unknowns with owners)
- **CVA summary** (what is common, what varies, what relationships exist)
- **Buy-vs-build decision** (core-vs-context classification, alternatives evaluated, recommendation: build/buy/partner/defer, rationale; or `N/A (bug fix / doc / refactor)` when step 4a was skipped)
