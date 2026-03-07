# Workflow Orchestration Skill

Numbered workflow commands for structured agent orchestration. Implements the MoAI-ADK inspired pipeline: `/0-init → /1-plan → /2-impl → /3-qa → /4-security`.

## Commands

| Command | Purpose | Agents |
|---------|---------|--------|
| `/0-init` | Session initialization (ADR-007) | Serena MCP |
| `/1-plan` | Planning phase | planner / architect / roadmap+advisor |
| `/2-impl` | Implementation | implementer (+ qa + security) |
| `/3-qa` | Quality assurance | qa |
| `/4-security` | Security review (opus) | security |

## Command Sequence

```text
/0-init → /1-plan → /2-impl → /3-qa → /4-security
```

Variants:

- `/1-plan --arch` — architecture decisions
- `/1-plan --strategic` — roadmap chain
- `/2-impl --full` — sequential impl+qa+security
- `/2-impl --parallel` — parallel qa+security

## Directory Structure

```text
.claude/skills/workflow/
├── modules/
│   ├── WorkflowHelpers.psm1        # Shared MCP wrappers
│   └── WorkflowHelpers.Tests.ps1
├── scripts/
│   ├── Invoke-Init.ps1             # /0-init
│   ├── Invoke-Plan.ps1             # /1-plan
│   ├── Invoke-Impl.ps1             # /2-impl
│   ├── Invoke-QA.ps1               # /3-qa
│   ├── Invoke-Security.ps1         # /4-security
│   ├── Invoke-WorkflowCommand.ps1  # Generic router
│   ├── Get-AgentHistory.ps1        # Query MCP history
│   └── Sync-SessionDocumentation.ps1
└── SKILL.md
```

## Integration

**Agent Orchestration MCP tools used:**

- `invoke_agent` — all commands
- `track_handoff` — context preservation between agents
- `start_parallel_execution` — `/2-impl --parallel`
- `aggregate_parallel_results` — parallel result merging
- `agents://history` — history queries

**Session State MCP:** `/0-init` records evidence via `record_evidence`.

**Serena MCP:** `/0-init` activates project and loads memories per ADR-007.

## MCP Fallback

All commands gracefully degrade when MCP is unavailable:

- Warning message displayed
- Direct agent instruction provided as fallback
- Workflow context still persisted locally

## Troubleshooting

| Issue | Solution |
|-------|----------|
| MCP unavailable | Set `AGENT_ORCHESTRATION_MCP_URL` env var or add `.mcp.json` |
| Session log not created | Verify `.claude/skills/session-init/scripts/New-SessionLog.ps1` exists |
| Context not persisting | Check `.agents/workflow-context.json` write permissions |

## Related ADRs

- ADR-005: PowerShell-only scripting
- ADR-006: Thin workflows, testable modules
- ADR-007: Memory-first architecture
- ADR-013: Agent Orchestration MCP
- ADR-035: Exit code standardization
