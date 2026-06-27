---
name: plan
description: Plan how to build it. Decompose specs into milestones with dependencies and risk mitigations. Run after /spec.
argument-hint: spec-output-or-issue-number
allowed-tools: Task, Skill, Read, Write, Glob, Grep
user-invocable: true
---

<!-- Copilot CLI: project instructions (CLAUDE.md) load via the plugin instructions tree; no include directive needed. -->
Plan: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message) is empty, check for recent /spec output in the conversation. If none found, ask the user what to plan.

## If you arrived here without a spec, run the front-gate first

Planning a spec that was never gated manufactures work. If there is no `/spec` output for this work (no requirement, no design, no testable acceptance criteria), do not decompose it into milestones yet. Run `/spec` first: it applies the front-gate (the six forcing questions, the `front-gate-before-pipeline` pattern) and confirms a named blocked user, a documented status quo, and a concrete observation before any downstream step runs. Return here once the spec exists. Skip this only when the user explicitly asks to plan an ungated idea and accepts that trade-off.

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

## Copilot CLI invocation reference

This skill body uses Claude Code call syntax. Under GitHub Copilot CLI, translate as follows (verified against Copilot CLI 1.0.66-1).

### Sub-skill calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Skill(skill="execution-plans")` | `skill` tool, `skill: "execution-plans"` |

### Sub-agent calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Task(subagent_type="analyst")` | `task` tool, `agent_type: "project-toolkit:analyst"` |
| `Task(subagent_type="critic")` | `task` tool, `agent_type: "project-toolkit:critic"` |
| `Task(subagent_type="milestone-planner")` | `task` tool, `agent_type: "project-toolkit:milestone-planner"` |
| `Task(subagent_type="task-decomposer")` | `task` tool, `agent_type: "project-toolkit:task-decomposer"` |

If a referenced skill or agent is unavailable in the Copilot CLI environment, perform that step inline and note the reduced coverage.
