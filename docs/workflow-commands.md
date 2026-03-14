# Workflow Commands Reference

Numbered workflow commands for structured agent orchestration. Implements the MoAI-ADK inspired pipeline.

## Overview

The workflow command system provides a numbered sequence of slash commands that guide development from session initialization through security review.

```text
/0-init → /1-plan → /2-impl → /3-qa → /4-security
```

## Getting Started

### Quick Workflow (Standard Feature)

```bash
/0-init --objective "Add user authentication"
/1-plan Add OAuth2 login flow with JWT tokens
/2-impl --full Add OAuth2 login flow
```

### Strategic Planning Workflow

```bash
/0-init
/1-plan --strategic Q2 roadmap for authentication system
/1-plan --arch Design OAuth2 implementation approach
/2-impl Implement approved design
/3-qa
/4-security
```

### Quick Fix Workflow

```bash
/0-init
/2-impl Fix null reference in UserService.GetById
/3-qa
```

## Command Reference

### /0-init — Session Initialization

Enforces ADR-007 memory-first architecture at session start.

```bash
/0-init
/0-init --session-number 42
/0-init --objective "Implement feature X"
```

**What it does:**

1. Activates Serena project (loads project context)
2. Reads AGENTS.md (project rules)
3. Reads HANDOFF.md (prior session context)
4. Queries relevant memories
5. Creates session log
6. Declares current branch
7. Records evidence to Session State MCP

**When to use:** Always at the start of a new session.

---

### /1-plan — Planning Phase

Routes to the appropriate planning agent based on task type.

```bash
/1-plan <task-description>           # Default: planner agent
/1-plan --arch <design-decision>     # Architect agent
/1-plan --strategic <roadmap-item>   # roadmap → high-level-advisor chain
```

**Variants:**

- Default: `planner` agent for standard feature planning
- `--arch`: `architect` agent for design decisions and ADR creation
- `--strategic`: chains `roadmap` → `high-level-advisor` for high-level planning

**Output:** Planning artifacts stored in `.agents/planning/`

---

### /2-impl — Implementation Phase

Invokes the implementer agent with optional QA and security follow-up.

```bash
/2-impl <task>                # Default: implementer only
/2-impl --full <task>         # Sequential: implementer → qa → security
/2-impl --parallel <task>     # Parallel: implementer + (qa ‖ security)
```

**Variants:**

- Default: implementer agent only
- `--full`: sequential chain (implementer → qa → security)
- `--parallel`: parallel execution (implementer + concurrent qa and security)

**Context:** Automatically surfaces planning artifacts from `/1-plan`.

---

### /3-qa — Quality Assurance

Invokes the QA agent to verify implementation.

```bash
/3-qa <scope>
/3-qa --coverage-threshold 90 <scope>
```

**What it does:**

1. Invokes `qa` agent
2. Validates test coverage against threshold (default: 80%)
3. Checks acceptance criteria from planning phase
4. Reports pass/fail with details

---

### /4-security — Security Review

Invokes the security agent with thorough review using opus model.

```bash
/4-security <scope>
/4-security --owasp-only <scope>    # Skip secret detection
/4-security --secrets-only <scope>  # OWASP check only
```

**What it does:**

1. Invokes `security` agent (uses opus per ADR-013)
2. OWASP Top 10 check
3. Secret detection scan
4. Dependency audit for known CVEs
5. Generates security report

---

## Supporting Scripts

### Invoke-WorkflowCommand.ps1

Generic executor for workflow commands with standardized error handling.

```bash
pwsh .claude/skills/workflow/scripts/Invoke-WorkflowCommand.ps1 -Command "init" -Arguments @{}
```

### Get-AgentHistory.ps1

Query agent invocation history from the Agent Orchestration MCP.

```bash
pwsh .claude/skills/workflow/scripts/Get-AgentHistory.ps1 -SessionNumber 42
pwsh .claude/skills/workflow/scripts/Get-AgentHistory.ps1 -Limit 20 -Format json
```

### Sync-SessionDocumentation.ps1

Sync session log with agent history, generate workflow diagrams, and update memories.

```bash
pwsh .claude/skills/workflow/scripts/Sync-SessionDocumentation.ps1 -SessionLogPath .agents/sessions/session-042.json
```

---

## Integration

### Agent Orchestration MCP

Commands integrate with the Agent Orchestration MCP for structured agent invocation:

- `invoke_agent()` — structured agent invocation with context
- `track_handoff()` — context preservation between agents
- `start_parallel_execution()` — parallel agent execution (`/2-impl --parallel`)
- `aggregate_parallel_results()` — merge parallel outputs

### Session State MCP

All commands record evidence for protocol compliance tracking via `record_evidence()`.

### Serena MCP

`/0-init` integrates with Serena for memory-first architecture:

- `activate_project()` — load project context
- `list_memories()` — surface relevant memories

---

## Troubleshooting

### MCP Unavailable

Commands gracefully degrade when MCP servers are unavailable:

- Serena MCP unavailable: session initialization continues with warning
- Agent Orchestration MCP unavailable: falls back to direct agent invocation

Check MCP server status:

```bash
# Check if agent-orchestration MCP is running
mcp status
```

### Command Validation Errors

Validate command files:

```bash
pwsh .claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1 -Path .claude/commands/workflow/0-init.md
```

### PowerShell Script Errors

Run Pester tests:

```bash
pwsh ./build/scripts/Invoke-PesterTests.ps1 -Path .claude/skills/workflow/
```

---

## Related

- PRD: [`.agents/planning/prd-workflow-orchestration-enhancement.md`](../.agents/planning/prd-workflow-orchestration-enhancement.md)
- Skill: [`.claude/skills/workflow/SKILL.md`](../.claude/skills/workflow/SKILL.md)
- ADR-005: PowerShell Standards
- ADR-006: Thin Workflows
- ADR-007: Memory-First Architecture
- ADR-013: Agent Orchestration MCP
