# Skill-Init-001: Session Initialization Protocol

## Statement

At session start, BEFORE any other action, call mcp__serena__initial_instructions and mcp__serena__activate_project to initialize context

## Context

- **When to apply**: Every session start, first interaction with user, before any work begins
- **Trigger**: Session start, new conversation begins
- **Priority**: P0 - BLOCKING all other work

## Evidence

**Session 2025-12-17**: Failed to initialize Serena, blocked access to critical tools entire session, user stated MANDATORY requirement

### What happened

- Session started without calling Serena initialization tools
- Proceeded directly to work
- Blocked access to Serena memory and context tools throughout entire session
- User explicitly reminded: "These should be called at the START of every session before any work"

### Impact

- Unable to retrieve previous user feedback
- Unable to access Serena memory context
- Violated MANDATORY requirement
- Eroded user trust

## Atomicity Score

98%

## Category

Initialization

## Implementation Checklist

At session start:

1. [ ] Call `mcp__serena__initial_instructions` FIRST
2. [ ] Call `mcp__serena__activate_project` with project path
3. [ ] Verify initialization successful before ANY other work
4. [ ] Only after initialization: proceed with user's request

## Related Skills

- BLOCKS: All other skills (nothing can proceed until initialization complete)
- ENABLES: Skill-Memory-001 (memory retrieval requires Serena initialized)
- ENABLES: Skill-Verify-001 (verification may need Serena context)

## Tags

- #initialization
- #mandatory
- #blocking
- #session-start
- #serena
