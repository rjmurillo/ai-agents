---
description: Route to planning agents based on task complexity. Supports --arch for architecture and --strategic for roadmap planning.
argument-hint: <task description> [--arch | --strategic]
model: sonnet
---

# /1-plan — Planning Phase

Route to planning agents based on task complexity and scope.

## Purpose

Break down work into actionable plans before implementation. Selects the appropriate planning agent(s) based on the nature of the request.

## Variants

| Variant | Agent(s) | Use When |
|---------|----------|----------|
| `/1-plan` | planner | Default — task breakdown, milestone sequencing |
| `/1-plan --arch` | architect | Design decisions, ADR creation, structural changes |
| `/1-plan --strategic` | roadmap → high-level-advisor | Epic-level planning, priority arbitration |

## Actions

1. **Analyze task scope** — Determine complexity (single-agent vs. multi-agent)
2. **Select planning agent** — Route based on variant or auto-detect from task description
3. **Generate plan** — Produce milestones, dependencies, and acceptance criteria
4. **Critic validation** — For multi-agent plans, invoke critic agent for plan review
5. **Output plan** — Structured plan ready for `/2-impl`

## Agent Routing Decision Tree

```text
Is this a design/architecture decision?
  YES → architect (Tier 1: Expert)
  NO ↓
Is this epic-level or cross-cutting?
  YES → roadmap → high-level-advisor (Tier 1: Expert)
  NO ↓
Is this a task breakdown?
  YES → planner (Tier 2: Manager)
  NO → planner (default)
```

## MCP Integration

Maps to Agent Orchestration MCP (ADR-013):

- `get_routing_recommendation(task_description)` — determines which agent to invoke
- `invoke_agent(name, prompt)` — dispatches to selected planning agent
- `track_handoff(from="user", to=agent, context)` — preserves routing decision

**Fallback**: Direct `Task()` invocation with appropriate `subagent_type`.

## Output

The planning phase produces:

- **Plan document** — Milestones with acceptance criteria
- **Dependency graph** — What blocks what
- **Agent assignments** — Which agents handle which milestones
- **Estimated complexity** — Simple / medium / complex per milestone

## Sequence Position

```text
/0-init → ▶ /1-plan → /2-impl → /3-qa → /4-security → /9-sync
```

## Dependencies

- Agent Orchestration MCP Phase 1 (ADR-013) — structured agent invocation
- Requires `/0-init` to have been run in the current session

## Examples

```text
/1-plan Implement user authentication with OAuth2
/1-plan --arch Design the caching layer for API responses
/1-plan --strategic Prioritize Q2 security hardening vs. new features
```
