# Agent Handoff Dashboard

> **Status**: Read-Only Dashboard (v2.0)
> **Last Aggregated**: 2025-12-21
> **Token Budget**: 5K max (enforced by pre-commit hook)

## Context Retrieval Guide

As of 2025-12-21, this file is a **read-only dashboard**. Session context is distributed:

| Context Type | Location | How to Access |
|--------------|----------|---------------|
| Cross-session learnings | Serena memory | `mcp__serena__list_memories` + `read_memory` |
| Recent session details | `.agents/sessions/` | Read recent session logs directly |
| Branch-specific context | `.agents/handoffs/{branch}/` | Read branch INDEX.md |
| Historical archive | `.agents/archive/` | Full pre-deprecation content |

**Do NOT update this file directly.** See [ADR-014](./architecture/ADR-014-distributed-handoff-architecture.md).

---

## Active Work Summary

### Open PRs Requiring Attention

| PR | Branch | Status | Owner | Last Activity |
|----|--------|--------|-------|---------------|
| *Query via `gh pr list --state open`* | - | - | - | - |

### Recent Sessions

| Session | Date | Key Outcomes |
|---------|------|--------------|
| Check `.agents/sessions/` | - | Session logs contain full details |

---

## Key Decisions (Quick Reference)

### Architecture Decisions

| ADR | Title | Status |
|-----|-------|--------|
| ADR-014 | Distributed Handoff Architecture | Accepted |
| *Others* | See `.agents/architecture/` | - |

### Project Constraints

See [PROJECT-CONSTRAINTS.md](./governance/PROJECT-CONSTRAINTS.md) for:

- Skill usage requirements
- Code style conventions
- Workflow patterns

---

## Memory Index

### Critical Memories to Read

| Memory Name | Purpose |
|-------------|---------|
| `skill-usage-mandatory` | Required skill patterns |
| `project-overview` | Project structure and goals |
| `codebase-structure` | Directory layout |

Use `mcp__serena__list_memories` for full catalog.

---

## Quick Start for New Sessions

1. **Initialize Serena**: `mcp__serena__activate_project` + `initial_instructions`
2. **Read memories**: `list_memories` → `read_memory` for relevant ones
3. **Check sessions**: Read recent logs in `.agents/sessions/`
4. **Create session log**: `.agents/sessions/YYYY-MM-DD-session-NN.md`
5. **Work**: Complete tasks, decisions go to session log
6. **End**: Write Serena memory for cross-session context, commit

See [SESSION-PROTOCOL.md](./SESSION-PROTOCOL.md) for full requirements.

---

## Links

- [SESSION-PROTOCOL.md](./SESSION-PROTOCOL.md) - Protocol requirements
- [ADR-014](./architecture/ADR-014-distributed-handoff-architecture.md) - Why this is a dashboard now
- [Archive](./archive/HANDOFF-2025-12-21-full.md) - Full pre-deprecation content
- [Issue #227](https://github.com/rjmurillo-bot/ai-agents/issues/227) - HANDOFF.md crisis resolution
