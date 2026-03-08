---
description: Execute implementation with optional multi-agent coordination. Supports --full (sequential) and --parallel modes.
argument-hint: <task description> [--full | --parallel]
model: opus
---

# /2-impl - Implementation Phase

Produce code changes, configurations, or artifacts from the `/1-plan` output. Supports single-agent and coordinated multi-agent execution.

## Variants

| Variant | Execution Mode | Agents |
|---------|---------------|--------|
| `/2-impl` | Single agent | implementer |
| `/2-impl --full` | Sequential chain | implementer → qa → security |
| `/2-impl --parallel` | Parallel with aggregation | implementer + (qa ∥ security) |

## Actions

### Default (`/2-impl`)

1. **Invoke implementer** - Execute the planned changes
2. **Commit work** - Stage and commit with conventional commit message
3. **Report results** - Files changed, tests affected, ready for `/3-qa`

### Full (`/2-impl --full`)

1. **Invoke implementer** - Execute changes
2. **Handoff to qa** - Pass implementation context, run verification
3. **Handoff to security** - Pass implementation context, run security checks
4. **Aggregate results** - Combine all findings into single report

### Parallel (`/2-impl --parallel`)

1. **Invoke implementer** - Execute changes
2. **Parallel dispatch** - qa and security run simultaneously on the result
3. **Conflict resolution** - If qa and security produce conflicting recommendations, escalate to Tier 2 (orchestrator) per ADR-009
4. **Aggregate results** - Merge parallel outputs

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

Maps to Agent Orchestration MCP (ADR-013): `invoke_agent()`, `start_parallel_execution()`, `aggregate_parallel_results()`, `resolve_conflict()`, `track_handoff()`. Fallback: sequential `Task()` invocations with manual context passing.

## Conflict Resolution (Parallel Mode)

When qa and security agents produce conflicting recommendations:

1. **Detect conflict** - Overlapping file changes or contradictory advice
2. **Escalate to orchestrator** - Tier 2 Manager aggregates and decides
3. **If unresolved** - Escalate to architect (Tier 1 Expert)
4. **Document decision** - Record resolution in session log

Per ADR-009: Parallel-Safe Multi-Agent Design.

## Output

- **Changed files** - List of modified/created/deleted files
- **Test results** - If qa was invoked, verification summary
- **Security findings** - If security was invoked, assessment summary
- **Commit reference** - Git commit SHA for the implementation

## Sequence Position

```text
/0-init → /1-plan → ▶ /2-impl → /3-qa → /4-security → /9-sync
```

## Prerequisites

Requires a plan from `/1-plan` (or explicit task description).

## References

- ADR-009: Parallel-Safe Multi-Agent Design
- ADR-013: Agent Orchestration MCP

## Examples

```text
/2-impl Add the UserService.cs authentication methods per plan
/2-impl --full Implement and verify the caching layer
/2-impl --parallel Implement API endpoints with concurrent qa and security review
```
