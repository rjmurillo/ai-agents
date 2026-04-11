---
description: Define what to build. Transform a problem into testable requirements with acceptance criteria.
allowed-tools: Task, Skill, Read, Glob, Grep
argument-hint: [problem-statement-or-issue-number]
---

@CLAUDE.md

Invoke the cva-analysis and decision-critic skills.

Define what to build for: $ARGUMENTS

Use Task(subagent_type="spec-generator") to produce requirements. If no argument provided, ask what problem to solve.

Evaluate across all 5 axes:

1. **Problem clarity** - Is the right problem being solved? Could a reframing yield 10x impact?
2. **Requirement testability** - Can each requirement be verified pass/fail?
3. **Completeness** - No gaps between problem statement and acceptance criteria?
4. **Traceability** - REQ to DESIGN to TASK linkage established?
5. **Feasibility** - Buildable within constraints? Existing code to leverage?

## Principles

- **CVA**: Identify commonalities first, then variabilities, then relationships. Greatest risk is the wrong abstraction.
- **YAGNI**: Only specify what is needed now. Speculative requirements create waste.
- **Separation of Concerns**: Each requirement addresses one concern. Mixed concerns signal a missing decomposition.

## Process

1. Clarify the problem (what, who, why, constraints)
2. Search for existing solutions in the codebase (grep for related patterns)
3. Apply CVA: what is common across use cases? What varies?
4. Write requirements as testable acceptance criteria
5. Run pre-mortem: what fails first?
6. Run decision-critic: challenge assumptions before committing

## Output

Structured requirements with:

- Problem statement (1-2 sentences)
- Acceptance criteria (numbered, testable)
- Out of scope (explicit exclusions)
- Open questions (unresolved unknowns)
