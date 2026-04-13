---
description: Plan how to build it. Decompose specs into milestones with dependencies and risk mitigations. Run after /spec.
allowed-tools: Task, Skill, Read, Write, Glob, Grep
argument-hint: [spec-output-or-issue-number]
---

@CLAUDE.md

Plan: $ARGUMENTS

If $ARGUMENTS is empty, check for recent /spec output in the conversation. If none found, ask the user what to plan.

## Process

1. Read the spec or issue
2. Map sub-problems to existing code (what already exists? use Grep/Glob to verify)
3. Task(subagent_type="milestone-planner"): You are a project planner. Break the spec into milestones with clear exit criteria. Each milestone is independently shippable. Sequence by dependencies. Flag parallel opportunities.
4. Task(subagent_type="task-decomposer"): You are a work breakdown specialist. Decompose each milestone into atomic tasks. Each task is independently verifiable with a clear done definition. Size by complexity (S/M/L), not time.
5. Invoke Skill(skill="execution-plans") to persist the plan as a versioned artifact.
6. Task(subagent_type="analyst"): You are a risk analyst. Run a pre-mortem on this plan. What fails first? What dependencies are fragile? What assumptions are untested?
7. Task(subagent_type="critic"): You are a plan reviewer. Validate: is scope complete? Can tasks execute in the stated sequence? Are estimates credible? Is anything missing?

## Evaluation Axes

1. **Scope integrity** - Nothing unnecessary, nothing missing
2. **Dependency ordering** - Can tasks execute in the stated sequence?
3. **Risk coverage** - All P0 risks have mitigations
4. **Estimate confidence** - Complexity-based sizing (S/M/L), not time-based
5. **Reversibility** - Which steps are hard to undo?

## Principles

- **Programming by Intention**: Each task should read like an intent, not an implementation detail.
- **OODA Loop**: Observe (read the spec), Orient (map to existing code), Decide (sequence tasks), Act (commit the plan). Faster loops win.
- **First Principles**: Question the requirement, try to delete the step, then optimize, then speed up, then automate. Never automate something that should not exist.

## Output

Structured plan:

- **Milestones** (numbered, with exit criteria)
- **Tasks per milestone** (atomic, with acceptance criteria and S/M/L sizing)
- **Dependency graph** (what blocks what, what can run in parallel)
- **Risk register** (risk, likelihood, impact, mitigation)
- **Deferred items** (explicitly out of scope for this plan)
