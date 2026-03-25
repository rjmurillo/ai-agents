---
name: workflow
version: 1.0.0
model: claude-sonnet-4-5
license: MIT
description: |
  Numbered workflow commands for structured agent orchestration.
  Implements the MoAI-ADK inspired pipeline: /0-init → /1-plan → /2-impl → /3-qa → /4-security.
---

# Workflow Orchestration Skill

Numbered workflow commands for structured agent orchestration. Implements the MoAI-ADK inspired pipeline: `/0-init → /1-plan → /2-impl → /3-qa → /4-security`.

## Triggers

Use this skill when:

- Starting a new development session (`/0-init`)
- Breaking down a task into a plan (`/1-plan`)
- Implementing a planned feature (`/2-impl`)
- Running quality assurance checks (`/3-qa`)
- Performing a security review (`/4-security`)
- Routing any numbered workflow command through the dispatcher

## Commands

| Command | Purpose | Agents |
|---------|---------|--------|
| `/0-init` | Session initialization (ADR-007) | Agent Orchestration MCP |
| `/1-plan` | Planning phase | planner / architect / roadmap+advisor |
| `/2-impl` | Implementation | implementer (+ qa + security) |
| `/3-qa` | Quality assurance | qa |
| `/4-security` | Security review (opus) | security |

## Process

### Phase 1: Session Initialization (`/0-init`)

1. Activate project context via MCP
2. Load `AGENTS.md` and `HANDOFF.md` for context
3. Query relevant memories from prior sessions
4. Create session log in `.agents/sessions/`
5. Declare current git branch
6. Record evidence to Session State MCP

### Phase 2: Planning (`/1-plan`)

1. Select agent chain based on flags:
   - Default: `planner`
   - `--arch`: `architect`
   - `--strategic`: `roadmap → high-level-advisor`
2. Load workflow context via `Get-WorkflowContext`
3. Pass context and task description to selected agent
4. Persist `LastCommand=1-plan` and `PlanningAgent` to workflow context

### Phase 3: Implementation (`/2-impl`)

1. Select execution mode:
   - Default/`--full`: Sequential `implementer → qa → security`
   - `--parallel`: Parallel `qa + security` after `implementer`
2. Run implementation agent
3. Aggregate parallel results if applicable
4. Persist `LastCommand=2-impl` to workflow context

### Phase 4: Quality Assurance (`/3-qa`)

1. Check for planning artifacts
2. Invoke qa agent with coverage threshold (default: 80%)
3. Persist `LastCommand=3-qa` to workflow context

### Phase 5: Security Review (`/4-security`)

1. Select security scope based on flags:
   - Default: Full OWASP + secrets scan
   - `--owasp-only`: OWASP checks only
   - `--secrets-only`: Secrets scan only
2. Invoke security agent
3. Persist `LastCommand=4-security` to workflow context

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

**Agent Orchestration MCP:** `/0-init` activates project and loads memories per ADR-007.

## MCP Fallback

All commands gracefully degrade when MCP is unavailable:

- Warning message displayed
- Direct agent instruction provided as fallback
- Workflow context still persisted locally

## Verification

- [ ] `/0-init` creates session log in `.agents/sessions/`
- [ ] `/1-plan` routes to correct agent based on flags
- [ ] `/2-impl --parallel` aggregates results from concurrent agents
- [ ] `/3-qa` respects `--coverage-threshold` parameter
- [ ] `/4-security` filters checks based on `--owasp-only`/`--secrets-only`
- [ ] MCP unavailability produces WARN (not ERROR) and falls back gracefully
- [ ] Path traversal validation in `Sync-SessionDocumentation.ps1` blocks paths outside `.agents/sessions/`
- [ ] All scripts exit with standardized codes per ADR-035

## Anti-Patterns

- Skipping `/0-init` — session context will be missing for subsequent commands
- Running `/2-impl` without a prior `/1-plan` — no planning artifacts to guide implementation
- Hardcoding MCP URLs — use `.mcp.json` or `AGENT_ORCHESTRATION_MCP_URL` env var
- Passing absolute paths to `Sync-SessionDocumentation.ps1` from outside `.agents/sessions/`

## Extension Points

- Add new numbered commands by creating `Invoke-<Name>.ps1` and registering in `Invoke-WorkflowCommand.ps1` `$CommandMap`
- Customize agent chains per flag in each `Invoke-*.ps1` script
- Override MCP tool names via `WorkflowHelpers.psm1` module

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
