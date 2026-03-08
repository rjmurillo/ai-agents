---
description: Execute implementation with optional multi-agent coordination. Supports --full (sequential) and --parallel modes.
argument-hint: <task description> [--full | --parallel]
allowed-tools:
  - Edit
  - Write
  - Read
  - Grep
  - Glob
  - Bash
  - Agent
  - mcp__serena__*
model: opus
---

# /2-impl — Implementation Phase

Execute implementation with optional multi-agent coordination.

## Purpose

Produce code changes, configurations, or artifacts described in the plan from `/1-plan`. Supports single-agent execution for simple tasks and coordinated multi-agent execution for complex work.

## Variants

| Variant | Execution Mode | Agents |
|---------|---------------|--------|
| `/2-impl` | Single agent | implementer |
| `/2-impl --full` | Sequential chain | implementer → qa → security |
| `/2-impl --parallel` | Parallel with aggregation | implementer + (qa ∥ security) |

## Actions

### Default (`/2-impl`)

1. **Invoke implementer** — Execute the planned changes
2. **Commit work** — Stage and commit with conventional commit message
3. **Report results** — Files changed, tests affected, ready for `/3-qa`

### Full (`/2-impl --full`)

1. **Invoke implementer** — Execute changes
2. **Handoff to qa** — Pass implementation context, run verification
3. **Handoff to security** — Pass implementation context, run security checks
4. **Aggregate results** — Combine all findings into single report

### Parallel (`/2-impl --parallel`)

1. **Invoke implementer** — Execute changes
2. **Parallel dispatch** — qa and security run simultaneously on the result
3. **Conflict resolution** — If qa and security produce conflicting recommendations, escalate to Tier 2 (orchestrator) per ADR-009
4. **Aggregate results** — Merge parallel outputs

## Agent Routing Decision Tree

```text
Is this a simple, single-file change?
  YES → implementer only (default)
  NO ↓
Does this touch security-sensitive code?
  YES → /2-impl --full (sequential, security mandatory)
  NO ↓
Are qa and security independent for this change?
  YES → /2-impl --parallel (save time)
  NO → /2-impl --full (sequential to avoid conflicts)
```

## MCP Integration

Maps to Agent Orchestration MCP (ADR-013):

- `invoke_agent("implementer", prompt)` — default mode
- `start_parallel_execution([{agent: "qa"}, {agent: "security"}])` — parallel mode
- `aggregate_parallel_results(execution_id)` — collect parallel results
- `resolve_conflict(execution_id)` — escalation for conflicting recommendations
- `track_handoff(from, to, context)` — preserve context between agents

**Fallback**: Sequential `Task()` invocations with manual context passing.

## Conflict Resolution (Parallel Mode)

When qa and security agents produce conflicting recommendations:

1. **Detect conflict** — Overlapping file changes or contradictory advice
2. **Escalate to orchestrator** — Tier 2 Manager aggregates and decides
3. **If unresolved** — Escalate to architect (Tier 1 Expert)
4. **Document decision** — Record resolution in session log

Per ADR-009: Parallel-Safe Multi-Agent Design.

## Output

- **Changed files** — List of modified/created/deleted files
- **Test results** — If qa was invoked, verification summary
- **Security findings** — If security was invoked, assessment summary
- **Commit reference** — Git commit SHA for the implementation

## Sequence Position

```text
/0-init → /1-plan → ▶ /2-impl → /3-qa → /4-security → /9-sync
```

## Dependencies

- Agent Orchestration MCP Phase 1 (ADR-013) — agent invocation and parallel execution
- ADR-009: Parallel-Safe Multi-Agent Design — conflict resolution patterns
- Requires a plan from `/1-plan` (or explicit task description)

## Examples

```text
/2-impl Add the UserService.cs authentication methods per plan
/2-impl --full Implement and verify the caching layer
/2-impl --parallel Implement API endpoints with concurrent qa and security review
```
