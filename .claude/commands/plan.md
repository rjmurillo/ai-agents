---
description: Plan how to build it. Decompose specs into milestones with dependencies and risk mitigations. Run after /spec.
allowed-tools: Task, Skill, Read, Glob, Grep
argument-hint: [spec-output-or-issue-number]
---

@CLAUDE.md

Invoke the planner and execution-plans skills.

Plan how to build: $ARGUMENTS

Use Task(subagent_type="milestone-planner") for milestone breakdown, then Task(subagent_type="task-decomposer") for atomic tasks. If no argument provided, check for recent /spec output or ask what to plan.

Evaluate across all 5 axes:

1. **Scope integrity** - Nothing unnecessary, nothing missing
2. **Dependency ordering** - Can tasks execute in the stated sequence?
3. **Risk coverage** - All P0 risks have mitigations
4. **Estimate confidence** - Complexity-based sizing (S/M/L), not time-based
5. **Reversibility** - Which steps are hard to undo?

## Principles

- **Programming by Intention**: Sergeant methods direct workflow. Each task should read like an intent, not an implementation.
- **OODA Loop**: Observe (read the spec), Orient (map to existing code), Decide (sequence tasks), Act (commit the plan). Faster loops win.
- **First Principles**: Question the requirement, try to delete the step, then optimize, then speed up, then automate. Never automate something that should not exist.

## Process

1. Read the spec or issue
2. Map sub-problems to existing code (what already exists?)
3. Break into milestones with clear exit criteria
4. Decompose milestones into atomic tasks (each independently verifiable)
5. Sequence by dependencies, flag parallel opportunities
6. Run pre-mortem on the plan itself
7. Route to Task(subagent_type="critic") for validation

## Output

Structured plan with:

- Milestones (numbered, with exit criteria)
- Tasks per milestone (atomic, with acceptance criteria)
- Dependency graph (what blocks what)
- Risk register (risk, likelihood, mitigation)
- Deferred items (explicitly out of scope for this plan)
