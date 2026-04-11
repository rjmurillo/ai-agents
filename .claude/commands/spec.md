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
2. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md`. Classify the problem as Tier 1-5 based on scope, ambiguity, cross-team dependencies, and reversibility. Return the tier number, rationale, and recommended spec depth. Use this to calibrate remaining steps:
   - Tier 1-2 (Entry/Mid): Simple acceptance criteria. Skip CVA if single use case.
   - Tier 3 (Senior): CVA analysis required. Cross-team input. Design review gate.
   - Tier 4 (Staff): Alternatives analysis mandatory. ADR required. Stakeholder alignment. Challenge: "can this be decomposed into a simpler tier?"
   - Tier 5 (Principal): Governance review. Multi-org consensus. Explicit "why not simpler?" challenge. If complexity can be driven out, do it before specifying.
3. Search for existing solutions in the codebase (grep for related patterns)
4. Invoke Skill(skill="cva-analysis"): identify commonalities across use cases, then variabilities, then relationships
4. Write requirements as testable acceptance criteria
5. Task(subagent_type="analyst"): You are a requirements analyst. Your job is to find gaps, ambiguities, and untestable requirements. For each requirement, ask: can this be verified pass/fail? Flag anything vague.
6. Invoke Skill(skill="decision-critic"): challenge assumptions before committing
7. Task(subagent_type="critic"): You are a skeptical reviewer. Run a pre-mortem: assume this spec ships and fails. What broke first? What was missing?

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

Structured requirements document:

- **Problem statement** (1-2 sentences)
- **Acceptance criteria** (numbered, each independently testable as pass/fail)
- **Out of scope** (explicit exclusions to prevent creep)
- **Open questions** (unresolved unknowns with owners)
- **CVA summary** (what is common, what varies, what relationships exist)
