---
description: Planning phase - route task to planner (default), architect (--arch), or roadmap→high-level-advisor chain (--strategic).
argument-hint: [--arch] [--strategic] <task-description>
allowed-tools:
  - Bash(pwsh .claude/skills/workflow/scripts/*)
  - Bash(git:*)
  - Bash(ls:*)
  - Read
  - mcp__agent_orchestration__invoke_agent
  - mcp__agent_orchestration__track_handoff
  - mcp__agent_orchestration__get_routing_recommendation
model: sonnet
---

# /1-plan — Planning Phase

Route a planning task to the appropriate agent.

## Context

Current branch: !`git branch --show-current`

Recent commits: !`git log --oneline -5`

Planning artifacts: !`ls -1 .agents/planning/ 2>/dev/null | tail -10`

## Invocation

```bash
pwsh .claude/skills/workflow/scripts/Invoke-Plan.ps1 $ARGUMENTS
```

## Variants

| Flag | Agent | Use When |
|------|-------|----------|
| *(none)* | `planner` | Standard feature/task planning |
| `--arch` | `architect` | Design decisions, ADR-worthy choices |
| `--strategic` | `roadmap → high-level-advisor` | Roadmap, epics, strategic alignment |

## Arguments

- `--arch`: Use architect agent instead of planner.
- `--strategic`: Chain roadmap agent → high-level-advisor.
- Remaining text: Task description passed to agent.

## Output

Planning artifacts stored in `.agents/planning/`.

## Related

- ADR-013: `.agents/architecture/ADR-013-agent-orchestration-mcp.md`
- Agent Orchestration Spec: `.agents/specs/agent-orchestration-mcp-spec.md`
