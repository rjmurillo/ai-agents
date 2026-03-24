---
description: Implementation phase - invoke implementer agent (default), or run full sequential chain (--full), or parallel execution of implementer+qa+security (--parallel).
argument-hint: [--full] [--parallel] <implementation-task>
allowed-tools:
  - Bash(pwsh .claude/skills/workflow/scripts/*)
  - Bash(git:*)
  - Bash(ls:*)
  - Read
  - mcp__agent_orchestration__invoke_agent
  - mcp__agent_orchestration__track_handoff
  - mcp__agent_orchestration__start_parallel_execution
  - mcp__agent_orchestration__aggregate_parallel_results
  - mcp__agent_orchestration__resolve_conflict
model: sonnet
---

# /2-impl — Implementation Phase

Invoke the implementer agent, optionally chaining QA and security.

## Context

Planning artifacts: !`ls -1 .agents/planning/ 2>/dev/null | tail -10`

Current branch: !`git branch --show-current`

## Invocation

```bash
pwsh .claude/skills/workflow/scripts/Invoke-Impl.ps1 $ARGUMENTS
```

## Execution Modes

| Flag | Mode | Description |
|------|------|-------------|
| *(none)* | Default | Implementer agent only |
| `--full` | Sequential | implementer → qa → security |
| `--parallel` | Parallel | implementer + parallel(qa, security) |

## Arguments

- `--full`: Run full sequential chain after implementation.
- `--parallel`: Run QA and security in parallel after implementation.
- Remaining text: Implementation task description.

## Related

- ADR-013: `.agents/architecture/ADR-013-agent-orchestration-mcp.md`
