---
description: Define what to build. Transform a problem into testable requirements with acceptance criteria.
allowed-tools: Task, Skill, Read, Write, Glob, Grep
argument-hint: [problem-statement-or-issue-number]
---

@CLAUDE.md

Spec: $ARGUMENTS

If $ARGUMENTS is empty, ask the user what problem to solve. Do not proceed without a problem statement.

## Process

### Step 0: First Principles Gate (blocking, runs before Step 1)

Before any clarification work, answer six forcing questions. The gate exists because every retro citing wasted spec work in the last six months traces to a question this gate forces upfront — the strongest single citation is `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` Phase 6, where the retro itself names the question this gate asks ("is the framework worth building at all if its design space misses the dominant failure modes?") and explicitly defers it as out of scope. That deferral landed after 69 commits.

The six questions, asked in order:

| Label | Question |
|-------|----------|
| **Q1 Demand Reality** | Have three or more real people or systems explicitly requested this, or does real production data show the gap? Name them or cite the data. |
| **Q2 Status Quo** | What is the exact workaround users do today, step by step? |
| **Q3 Desperate Specificity** | Name the single most blocked person or system right now. What exactly are they blocked on? |
| **Q4 Narrowest Wedge** | What is the smallest possible deliverable that unblocks Q3, measured in hours of implementation? |
| **Q5 Observation** | What have you directly observed (not predicted) that proves demand? Quote or cite. |
| **Q6 Future-fit** | If the system grows 10x, does this feature still make sense, or does it become a liability? |

Write the answers as a structured block (the `## Step 0 First Principles` block) with six `### Q1..Q6` subheads, each containing the author's verbatim answer. This block becomes the first section of the PRD produced in Step 6 and is consumed unchanged by Steps 1, 2, 3, and 9. Do not paraphrase; downstream steps depend on the verbatim answers.

After writing the block, evaluate it against the gate logic in the next subsection.

---

1. Clarify the problem (what, who, why, constraints)
2. **Run the adversarial requirements interview**: Invoke Skill(skill="requirements-interview") to walk the design tree before any further analysis. The skill grills the user on user stories, data model, integrations, failure modes, security, observability, and scope boundaries. For every question it must propose a recommended answer; if the codebase can answer it (grep the repo first), it does so without asking. Output is a structured PRD that every downstream step consumes. Carry the PRD forward unchanged through steps 3-9; do not drop sections.
3. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md`. Using the structured PRD from step 2, classify the problem as Tier 1-5 based on scope, ambiguity, cross-team dependencies, and reversibility. Return the tier number, rationale, and recommended spec depth. Use this to calibrate remaining steps:
   - Tier 1-2 (Entry/Mid): Simple acceptance criteria. Skip CVA if single use case.
   - Tier 3 (Senior): CVA analysis required. Cross-team input. Design review gate.
   - Tier 4 (Staff): Alternatives analysis mandatory. ADR required. Stakeholder alignment. Challenge: "can this be decomposed into a simpler tier?"
   - Tier 5 (Principal): Governance review. Multi-org consensus. Explicit "why not simpler?" challenge. If complexity can be driven out, do it before specifying.
4. Search for existing solutions in the codebase (grep for related patterns). Use the PRD's Integrations and Data model sections to scope the search.
5. **CVA analysis (conditional)**: If the complexity tier is 3-5, or Tier 1-2 with multiple use cases, invoke Skill(skill="cva-analysis"): identify commonalities across the PRD's user stories, then variabilities, then relationships. Otherwise (Tier 1-2 single-use-case), set `CVA summary: N/A (single-use-case Tier 1-2)` and proceed.
6. **Formalize the PRD into durable artifacts**: Task(subagent_type="spec-generator"). Pass every PRD section from step 2 (Problem, User stories, Data model, Integrations, Failure modes, Security, Observability, Acceptance criteria, Out of scope, Deferred, Open questions) plus the complexity tier from step 3 and the CVA summary from step 5 (which may be the `N/A` placeholder for skipped runs). The spec-generator agent writes:
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
