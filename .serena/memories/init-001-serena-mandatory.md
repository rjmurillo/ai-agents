# Skill-Init-001: Serena Initialization Mandatory

## Statement

Call `mcp__serena__activate_project` and `mcp__serena__initial_instructions` BEFORE any other work.

## Context

Start of EVERY Claude Code session, BEFORE any other tools are called.

## Evidence

Session 2025-12-17: Multiple critical failures from not initializing Serena at session start. User explicitly stated this is MANDATORY.

## Scoring

- **Atomicity**: 98%
- **Tag**: critical
- **Impact**: 10
- **Priority**: P0-BLOCKING

## Protocol

```text
1. FIRST tool call: mcp__serena__activate_project with project path
2. SECOND tool call: mcp__serena__initial_instructions
3. ONLY THEN proceed with any other work
```

## Anti-Pattern

Starting work without Serena initialization leads to:

- Missing project memories
- No access to semantic code tools
- Repeated mistakes from not having historical context
