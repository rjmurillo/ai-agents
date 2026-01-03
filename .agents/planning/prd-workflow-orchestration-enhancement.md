# PRD: Workflow Orchestration Enhancement

**Version**: 1.0
**Date**: 2026-01-03
**Author**: Explainer Agent
**Status**: Draft
**Epic**: [#739](https://github.com/rjmurillo/ai-agents/issues/739)

## Introduction/Overview

This PRD defines enhancements to the ai-agents workflow system inspired by MoAI-ADK patterns. The enhancement introduces numbered workflow commands, agent tier hierarchy, mandatory orchestration, and auto-sync documentation to improve developer experience and workflow consistency.

### Problem Statement

Current workflow has four problems:

1. **Ad-hoc Command Discovery**: 25+ skills and commands with no clear sequencing. Developers must know which to invoke and when.
2. **Flat Agent Structure**: 18 agents with no tier hierarchy. No clear escalation path or delegation patterns.
3. **Optional Orchestration**: Direct agent invocation bypasses coordination, causing context loss and parallel conflicts.
4. **Manual Documentation**: Session logs require manual sync. No automated workflow documentation.

### Solution Overview

Implement a numbered command system with tiered agent organization:

```text
/0-init    → Session initialization (memory-first)
/1-plan    → Planning and architecture
/2-impl    → Implementation execution
/3-qa      → Quality assurance
/4-security → Security review
/9-sync    → Auto-documentation
```

This builds on the existing Agent Orchestration MCP PRD (ADR-013) as the infrastructure layer.

---

## Goals

1. Reduce workflow discovery time by 50% through numbered command sequencing
2. Establish 4-tier agent hierarchy (Expert, Manager, Builder, Integration)
3. Enforce mandatory orchestration for multi-agent workflows
4. Automate session documentation through `/9-sync` command
5. Integrate with existing Three-MCP strategy (Session State, Skill Catalog, Agent Orchestration)

---

## Non-Goals (Out of Scope)

1. **Replacing Agent Orchestration MCP**: This PRD defines UX layer, not infrastructure
2. **Changing Agent Prompts**: Agent capabilities remain unchanged; only organization changes
3. **Breaking Existing Workflows**: Current direct invocation remains valid for simple tasks
4. **Full Automation**: Human approval checkpoints preserved (critic gate, qa gate)

---

## User Stories

### US-1: Developer Discovers Workflow Sequence

**As a** developer starting a new feature
**I want to** see numbered commands that guide me through the workflow
**So that** I know the correct sequence without reading documentation

**Acceptance Criteria**:

- `/0-init` is always first (session start, memory load)
- `/1-plan` through `/4-security` follow logical sequence
- `/9-sync` is always last (documentation sync)
- Command help shows full sequence with descriptions

### US-2: Orchestrator Routes Multi-Agent Work

**As a** developer invoking `/2-impl` with complex changes
**I want** the command to automatically coordinate multiple agents
**So that** I don't need to manually invoke implementer, then qa, then security

**Acceptance Criteria**:

- `/2-impl --full` invokes: implementer → qa → security (sequential)
- `/2-impl --parallel` invokes: implementer + (qa || security) where safe
- Handoff context preserved between agents via Agent Orchestration MCP
- Conflicts detected and escalated per ADR-009

### US-3: Auto-Sync Documents Session

**As a** developer finishing a workflow
**I want** `/9-sync` to automatically update session documentation
**So that** I don't need to manually write session log entries

**Acceptance Criteria**:

- Queries `agents://history` for session's agent invocations
- Generates workflow diagram (sequence of agents)
- Appends to session log with: agents used, decisions made, artifacts created
- Suggests retrospective learnings

---

## Agent Tier Hierarchy

### Tier 1: Expert (Strategic Depth)

| Agent | Model | Purpose |
|-------|-------|---------|
| high-level-advisor | opus | Strategic decisions, priority arbitration |
| independent-thinker | sonnet | Challenge assumptions, alternative viewpoints |
| architect | sonnet | Design governance, ADR creation |
| roadmap | sonnet | Epic definition, business value prioritization |

**Escalation point** for conflicts between lower tiers.

### Tier 2: Manager (Coordination)

| Agent | Model | Purpose |
|-------|-------|---------|
| orchestrator | sonnet | Task routing, workflow coordination |
| planner | sonnet | Milestone breakdown, dependency sequencing |
| critic | sonnet | Plan validation, blocker identification |

**Aggregation point** for parallel execution results per ADR-009.

### Tier 3: Builder (Execution)

| Agent | Model | Purpose |
|-------|-------|---------|
| implementer | opus | Production code, .NET patterns |
| qa | sonnet | Test strategy, verification |
| devops | sonnet | CI/CD, deployment |
| security | sonnet | Vulnerability assessment, OWASP |

**Parallelizable work** with conflict detection.

### Tier 4: Integration (Support)

| Agent | Model | Purpose |
|-------|-------|---------|
| analyst | sonnet | Research, root cause analysis |
| explainer | sonnet | PRDs, documentation |
| task-generator | sonnet | Atomic task breakdown |
| retrospective | sonnet | Learning extraction |
| memory | haiku | Context retrieval/storage |
| skillbook | haiku | Skill management |
| context-retrieval | haiku | Memory search, docs fetch |

**Support functions** for other tiers.

---

## Numbered Command Definitions

### /0-init (Session Initialization)

**Purpose**: Enforce ADR-007 memory-first architecture at session start.

**Actions**:

1. Activate Serena project
2. Load initial instructions
3. Read HANDOFF.md
4. Query relevant memories
5. Create session log
6. Declare current branch

**Maps to**: Session State MCP `session_start()` tool

### /1-plan (Planning Phase)

**Purpose**: Route to planning agents based on task complexity.

**Variants**:

- `/1-plan` → planner agent (default)
- `/1-plan --arch` → architect agent (design decisions)
- `/1-plan --strategic` → roadmap → high-level-advisor chain

**Maps to**: Agent Orchestration MCP with routing recommendation

### /2-impl (Implementation Phase)

**Purpose**: Execute implementation with optional coordination.

**Variants**:

- `/2-impl` → implementer agent (default)
- `/2-impl --full` → implementer → qa → security (sequential)
- `/2-impl --parallel` → implementer + parallel(qa, security)

**Maps to**: Agent Orchestration MCP `invoke_agent()` and `start_parallel_execution()`

### /3-qa (Quality Assurance)

**Purpose**: Route to QA verification.

**Actions**:

1. Invoke qa agent
2. Validate test coverage
3. Check acceptance criteria
4. Report verification results

**Maps to**: Agent Orchestration MCP with handoff tracking

### /4-security (Security Review)

**Purpose**: Security assessment for sensitive changes.

**Actions**:

1. Invoke security agent
2. OWASP Top 10 check
3. Secret detection
4. Dependency audit

**Maps to**: Agent Orchestration MCP with mandatory invocation for security-tagged issues

### /9-sync (Documentation Sync)

**Purpose**: Auto-generate session documentation.

**Actions**:

1. Query `agents://history` for session invocations
2. Generate workflow sequence diagram
3. Extract decisions and artifacts
4. Append to session log
5. Update Serena memory
6. Suggest retrospective learnings

**Maps to**: Agent Orchestration MCP `agents://history` resource

---

## Technical Requirements

### TR-1: Command Infrastructure

Commands implemented as Claude Code command files in `.claude/commands/workflow/`:

```text
.claude/commands/workflow/
├── 0-init.md
├── 1-plan.md
├── 2-impl.md
├── 3-qa.md
├── 4-security.md
└── 9-sync.md
```

### TR-2: Agent Tier Metadata

Add `tier` field to agent frontmatter:

```yaml
---
name: implementer
tier: builder
model: opus
---
```

### TR-3: MCP Integration

Commands wrap Agent Orchestration MCP tools:

| Command | MCP Tool |
|---------|----------|
| /0-init | `session_start()` (Session State MCP) |
| /1-plan | `invoke_agent()` + `get_routing_recommendation()` |
| /2-impl | `invoke_agent()` or `start_parallel_execution()` |
| /9-sync | Read `agents://history` resource |

### TR-4: PowerShell Scripts

Per ADR-005, any automation scripts use PowerShell:

```text
.claude/skills/workflow/scripts/
├── Invoke-WorkflowCommand.ps1
├── Get-AgentHistory.ps1
└── Sync-SessionDocumentation.ps1
```

---

## Dependencies

### Required (Blockers)

1. **Agent Orchestration MCP Phase 1**: Core agent invocation infrastructure
2. **Session State MCP Phase 1**: Session initialization state machine

### Recommended (Enhances)

1. **Skill Catalog MCP**: Command discovery and validation
2. **ADR-007 Hooks**: Memory-first enforcement at /0-init

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Workflow discovery time | ~5 min (docs lookup) | <1 min (command sequence) |
| Multi-agent coordination errors | ~30% context loss | <5% with handoff tracking |
| Session documentation completeness | ~60% (manual) | 95% (auto-sync) |
| Agent tier clarity | None (flat) | 4-tier with escalation paths |

---

## Implementation Phases

### Phase 1: Command Definitions (Week 1-2)

- Create `.claude/commands/workflow/` directory
- Define /0-init, /1-plan, /2-impl, /3-qa, /9-sync commands
- Add tier metadata to all 18 agent files
- Document tier hierarchy in AGENT-SYSTEM.md

### Phase 2: Basic MCP Integration (Week 3-4)

- Integrate /0-init with Session State MCP
- Integrate /1-plan, /2-impl with Agent Orchestration MCP invoke_agent()
- Add handoff tracking to command transitions

### Phase 3: Parallel Execution (Week 5-6)

- Implement /2-impl --parallel variant
- Integrate with Agent Orchestration MCP start_parallel_execution()
- Add conflict detection and escalation

### Phase 4: Auto-Sync (Week 7-8)

- Implement /9-sync command
- Query agents://history resource
- Generate workflow diagrams
- Auto-append to session logs

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| MCP dependency delays | Commands non-functional | Fallback to direct Task() calls |
| Agent tier disagreement | Confusion on escalation | Document clear examples |
| Auto-sync noise | Cluttered session logs | Configurable verbosity |
| Command proliferation | Too many variants | Limit to core numbered set |

---

## Related Documents

### Project Plans

- [enhancement-PROJECT-PLAN.md](enhancement-PROJECT-PLAN.md) - Master project plan (Phase 7)
- [three-mcp-milestone-plan.md](three-mcp-milestone-plan.md) - Three-MCP implementation milestones
- [003-awesome-copilot-gap-analysis.md](../analysis/003-awesome-copilot-gap-analysis.md) - Agent gap analysis

### PRDs

- [PRD-agent-orchestration-mcp.md](PRD-agent-orchestration-mcp.md) - Infrastructure layer
- [PRD-session-state-mcp.md](PRD-session-state-mcp.md) - Session state management
- [PRD-skill-catalog-mcp.md](PRD-skill-catalog-mcp.md) - Skill discovery

### ADRs

- [ADR-013: Agent Orchestration MCP](../architecture/ADR-013-agent-orchestration-mcp.md) - Architecture decision
- [ADR-011: Session State MCP](../architecture/ADR-011-session-state-mcp.md) - Session state architecture
- [ADR-007: Memory-First Architecture](../architecture/ADR-007-memory-first-architecture.md) - /0-init foundation
- [ADR-009: Parallel-Safe Multi-Agent Design](../architecture/ADR-009-parallel-safe-multi-agent-design.md) - /2-impl --parallel foundation

### GitHub Issues

- [#739](https://github.com/rjmurillo/ai-agents/issues/739) - Epic: Workflow Orchestration Enhancement (this PRD)
- [#221](https://github.com/rjmurillo/ai-agents/issues/221) - feat: Agent Orchestration MCP (dependency)
- [#219](https://github.com/rjmurillo/ai-agents/issues/219) - feat: Session State MCP (dependency)
- [#220](https://github.com/rjmurillo/ai-agents/issues/220) - feat: Skill Catalog MCP (enhances)
- [#183](https://github.com/rjmurillo/ai-agents/issues/183) - Epic: Claude-Flow Inspired Enhancements (parent)
- [#168](https://github.com/rjmurillo/ai-agents/issues/168) - Parallel Agent Execution
- [#166](https://github.com/rjmurillo/ai-agents/issues/166) - Awesome-Copilot Agent Gap Analysis

### Agent Documentation

- [AGENT-SYSTEM.md](../AGENT-SYSTEM.md) - Current agent catalog
- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md) - Session requirements

---

## Appendix: MoAI-ADK Inspiration

This PRD is inspired by [MoAI-ADK](https://github.com/modu-ai/moai-adk) patterns:

| MoAI Pattern | ai-agents Adaptation |
|--------------|---------------------|
| /moai:0-project | /0-init (session start) |
| /moai:1-plan | /1-plan (planning agents) |
| /moai:2-run | /2-impl (implementation) |
| /moai:3-sync | /9-sync (auto-documentation) |
| Mr. Alfred orchestrator | orchestrator agent (mandatory for multi-agent) |
| 5-tier agent hierarchy | 4-tier hierarchy (Expert, Manager, Builder, Integration) |
| SPEC-First development | Critic gate + plan validation |

Key difference: MoAI uses Python; ai-agents uses PowerShell per ADR-005.
