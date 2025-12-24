# Skill-Init-001: Session Initialization Protocol

**Created**: 2025-12-17
**Priority**: P0 - BLOCKING (nothing proceeds until complete)
**Atomicity**: 98%
**Impact**: 10/10

## Statement

At session start, BEFORE any other action, initialize Serena with `mcp__serena__activate_project` and `mcp__serena__initial_instructions`.

## Context

- **When**: Every session start, first interaction, before any work
- **Trigger**: New conversation begins
- **Scope**: ALL Claude Code sessions in this project

## Protocol

```text
1. FIRST:  mcp__serena__activate_project (with project path)
2. SECOND: mcp__serena__initial_instructions
3. THEN:   Proceed with user's request
```

## Evidence

**Session 2025-12-17**: Failed to initialize Serena at session start.

- Blocked access to Serena memory and context tools entire session
- Unable to retrieve previous user feedback
- User explicitly stated: "These should be called at the START of every session before any work"
- Violated MANDATORY requirement, eroded trust

## What Initialization Provides

- Project memories (115+ learned patterns)
- Semantic code tools (symbol search, analysis)
- Historical context (prior decisions, user preferences)
- Session protocol requirements

## Anti-Pattern

Starting work without Serena initialization leads to:
- Missing project memories
- No access to semantic code tools
- Repeated mistakes from not having historical context
- Unable to retrieve user preferences
- Blocked from memory read/write operations

## Implementation Checklist

At session start:

1. [ ] Call `mcp__serena__activate_project` with project path
2. [ ] Call `mcp__serena__initial_instructions`
3. [ ] Verify initialization successful (tool output appears)
4. [ ] Only after initialization: proceed with user's request

## Related

- **BLOCKS**: All other skills (nothing can proceed until init complete)
- **ENABLES**: Memory retrieval, semantic code tools, context access
- **See also**: SESSION-PROTOCOL.md Phase 1

## Tags

#initialization #mandatory #blocking #session-start #serena #P0
