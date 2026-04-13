# MCP Integration Overview

> **Status**: Draft
> **Version**: 0.1.0
> **Date**: 2025-12-21

## Three-MCP Architecture

This document describes how the three custom MCPs integrate to provide comprehensive agent workflow management.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Claude Code CLI                                 │
│                                                                              │
│   User Request ──> Orchestrator ──> Specialized Agents ──> Output           │
│                         │                   │                                │
│                         v                   v                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        MCP Integration Layer                         │   │
│   │                                                                      │   │
│   │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │   │
│   │  │ Session State │  │ Skill Catalog │  │    Agent      │           │   │
│   │  │     MCP       │  │     MCP       │  │ Orchestration │           │   │
│   │  │               │  │               │  │     MCP       │           │   │
│   │  │ • Phase gates │  │ • Skill search│  │ • Invocation  │           │   │
│   │  │ • Evidence    │  │ • Citations   │  │ • Handoffs    │           │   │
│   │  │ • Validation  │  │ • Suggestions │  │ • Parallel    │           │   │
│   │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘           │   │
│   │          │                  │                  │                    │   │
│   │          └──────────────────┼──────────────────┘                    │   │
│   │                             │                                       │   │
│   │                             v                                       │   │
│   │                    ┌────────────────┐                               │   │
│   │                    │   Serena MCP   │                               │   │
│   │                    │   (Memories)   │                               │   │
│   │                    └────────────────┘                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## MCP Summary

| MCP | Primary Purpose | Key Tools | ADR |
|-----|-----------------|-----------|-----|
| **Session State** | Protocol enforcement | session_start, validate_gate, session_end | [ADR-011](../architecture/ADR-011-session-state-mcp.md) |
| **Skill Catalog** | Skill discovery & enforcement | search_skills, check_skill_exists, cite_skill | [ADR-012](../architecture/ADR-012-skill-catalog-mcp.md) |
| **Agent Orchestration** | Structured agent invocation | invoke_agent, track_handoff, start_parallel_execution | [ADR-013](../architecture/ADR-013-agent-orchestration-mcp.md) |

---

## Integration Points

### 1. Session Start Flow

```
User starts session
        │
        v
┌───────────────────┐
│ Session State MCP │
│ session_start()   │─────> Creates session state in Serena
└─────────┬─────────┘
          │
          v
┌───────────────────┐
│ Session State MCP │
│ validate_gate()   │─────> SERENA_INIT gate
└─────────┬─────────┘
          │
          v
┌───────────────────┐
│ Skill Catalog MCP │
│ (via Phase 1.5)   │─────> List available skills, validate skill-usage-mandatory
└─────────┬─────────┘
          │
          v
┌───────────────────┐
│ Session State MCP │
│ validate_gate()   │─────> SKILL_VALIDATION gate
└─────────┬─────────┘
          │
          v
      Session READY
```

### 2. Agent Invocation Flow

```
Orchestrator receives task
        │
        v
┌────────────────────────┐
│ Agent Orchestration MCP│
│ get_routing_recommendation()
└─────────┬──────────────┘
          │
          v
┌────────────────────────┐
│ Skill Catalog MCP      │
│ suggest_skills()       │─────> Check for relevant skills
└─────────┬──────────────┘
          │ (warnings if raw commands detected)
          v
┌────────────────────────┐
│ Agent Orchestration MCP│
│ invoke_agent()         │─────> Structured invocation
└─────────┬──────────────┘
          │
          v
┌────────────────────────┐
│ Session State MCP      │
│ record_evidence()      │─────> Track invocation in session
└─────────┬──────────────┘
          │
          v
     Agent executes
          │
          v
┌────────────────────────┐
│ Agent Orchestration MCP│
│ track_handoff()        │─────> Preserve context
└────────────────────────┘
```

### 3. Skill Usage Flow

```
Agent plans to use `gh pr view`
        │
        v
┌────────────────────────┐
│ Skill Catalog MCP      │
│ check_skill_exists()   │─────> Returns: exists=true, skill=github/pr/Get-PRContext
└─────────┬──────────────┘
          │
          v
Agent uses skill script
        │
        v
┌────────────────────────┐
│ Skill Catalog MCP      │
│ cite_skill()           │─────> Records usage with session link
└─────────┬──────────────┘
          │
          v
┌────────────────────────┐
│ Session State MCP      │
│ (automatic link)       │─────> Citation appears in session evidence
└────────────────────────┘
```

### 4. Parallel Execution Flow

```
Orchestrator needs parallel analysis
        │
        v
┌─────────────────────────────┐
│ Agent Orchestration MCP     │
│ start_parallel_execution()  │
│  agents: [architect,        │
│           security,         │
│           devops]           │
└─────────┬───────────────────┘
          │
          ├──────────────┬──────────────┐
          v              v              v
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │architect │   │ security │   │  devops  │
    └────┬─────┘   └────┬─────┘   └────┬─────┘
         │              │              │
         └──────────────┼──────────────┘
                        │
                        v
┌─────────────────────────────┐
│ Agent Orchestration MCP     │
│ aggregate_parallel_results()│─────> Merge/Vote/Escalate
└─────────┬───────────────────┘
          │
          v
┌─────────────────────────────┐
│ Agent Orchestration MCP     │
│ track_handoff()             │─────> Single consolidated handoff
└─────────────────────────────┘       (prevents HANDOFF.md conflicts)
```

### 5. Session End Flow

```
Agent work complete
        │
        v
┌────────────────────────┐
│ Session State MCP      │
│ validate_gate()        │─────> DOCS_UPDATE, QUALITY_CHECKS gates
└─────────┬──────────────┘
          │
          v
┌────────────────────────┐
│ Session State MCP      │
│ validate_gate()        │─────> QA_VALIDATION gate
└─────────┬──────────────┘
          │
          v
┌────────────────────────┐
│ Session State MCP      │
│ session_end()          │
└─────────┬──────────────┘
          │
          v
┌────────────────────────┐
│ Serena MCP             │
│ (persistence)          │─────> Update session-history, skill-usage-citations
└────────────────────────┘
```

---

## Shared Serena Memories

| Memory | Owner MCP | Consumers |
|--------|-----------|-----------|
| `session-current-state` | Session State | Agent Orchestration |
| `session-history` | Session State | All MCPs |
| `skill-catalog-index` | Skill Catalog | Skill Catalog |
| `skill-usage-citations` | Skill Catalog | Session State |
| `agent-invocation-history` | Agent Orchestration | Session State |
| `agent-handoff-chain` | Agent Orchestration | Session State |
| `agent-parallel-state` | Agent Orchestration | Agent Orchestration |

---

## Cross-MCP Events

### Session State → Others

| Event | Trigger | Consumers |
|-------|---------|-----------|
| `session_started` | session_start() completes | Agent Orchestration (reset handoff chain) |
| `phase_changed` | advance_phase() | Skill Catalog (suggest skills for phase) |
| `session_ending` | session_end() starts | Agent Orchestration (consolidate handoffs) |

### Skill Catalog → Others

| Event | Trigger | Consumers |
|-------|---------|-----------|
| `skill_cited` | cite_skill() | Session State (record evidence) |
| `raw_command_detected` | suggest_skills() warns | Agent Orchestration (block invocation?) |

### Agent Orchestration → Others

| Event | Trigger | Consumers |
|-------|---------|-----------|
| `agent_invoked` | invoke_agent() | Session State (record evidence) |
| `handoff_tracked` | track_handoff() | Session State (update checklist) |
| `parallel_conflict` | aggregate detects conflict | Session State (flag for review) |

---

## Enforcement Summary

| Violation Type | Preventing MCP | Mechanism |
|----------------|----------------|-----------|
| Skipped Serena init | Session State | BLOCKING gate on SERENA_INIT |
| Skipped HANDOFF read | Session State | BLOCKING gate on CONTEXT_RETRIEVAL |
| Raw `gh` command | Skill Catalog | check_skill_exists returns blocking=true |
| Missing QA validation | Session State | BLOCKING gate on QA_VALIDATION |
| HANDOFF conflicts | Agent Orchestration | Consolidated handoff tracking |
| Model misassignment | Agent Orchestration | Registry enforces default models |

---

## Implementation Priority

### Phase 1 (P0): Core Functionality

| MCP | Tools | Target |
|-----|-------|--------|
| Session State | session_start, validate_gate, advance_phase | Protocol enforcement |
| Skill Catalog | search_skills, check_skill_exists | Skill discovery |
| Agent Orchestration | invoke_agent, get_agent_catalog | Structured invocation |

### Phase 2 (P1): Tracking

| MCP | Tools | Target |
|-----|-------|--------|
| Session State | record_evidence, session_end | Evidence collection |
| Skill Catalog | cite_skill | Usage tracking |
| Agent Orchestration | track_handoff | Context preservation |

### Phase 3 (P2): Advanced

| MCP | Tools | Target |
|-----|-------|--------|
| Session State | get_blocked_reason | Diagnostics |
| Skill Catalog | suggest_skills, validate_no_raw_commands | Proactive guidance |
| Agent Orchestration | start_parallel_execution, aggregate_parallel_results | Parallel safety |

### Phase 4 (P3): Intelligence

| MCP | Tools | Target |
|-----|-------|--------|
| All | Resource subscriptions | Real-time updates |
| Agent Orchestration | get_routing_recommendation | AI-assisted routing |
| Skill Catalog | Index auto-refresh | Always current |

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| MCP Framework | @modelcontextprotocol/sdk (TypeScript) |
| Runtime | Node.js 20+ |
| State Persistence | Serena MCP (via mcp__serena__* tools) |
| File Watching | chokidar (for index refresh) |
| Testing | Jest + mock Serena |

---

## Metrics & Observability

### Session State MCP

- Gate pass/fail rates by phase
- Average session duration
- Violation frequency by type

### Skill Catalog MCP

- Search query patterns
- Citation frequency by skill
- Raw command violation rate

### Agent Orchestration MCP

- Invocation counts by agent
- Handoff context preservation rate
- Parallel execution conflict rate

---

## References

- [ADR-011: Session State MCP](../architecture/ADR-011-session-state-mcp.md)
- [ADR-012: Skill Catalog MCP](../architecture/ADR-012-skill-catalog-mcp.md)
- [ADR-013: Agent Orchestration MCP](../architecture/ADR-013-agent-orchestration-mcp.md)
- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md)
- [AGENT-SYSTEM.md](../AGENT-SYSTEM.md)
