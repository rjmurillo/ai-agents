# Claude Code Hooks Opportunity Analysis

**Date**: 2026-01-04
**Analysis**: `.agents/analysis/claude-code-hooks-opportunity-analysis.md`

## Current State

- 2 of 8 hook types implemented (SessionStart, UserPromptSubmit)
- Existing hooks: ADR-007 memory-first, ADR change detection, memory checks, PR validation, skill usage

## Available Hook Types

| Hook | Purpose | Implemented |
|------|---------|-------------|
| SessionStart | Context injection at session start | Yes |
| UserPromptSubmit | Prompt analysis and guidance | Yes |
| PreToolUse | Block/modify before tool execution | No |
| PostToolUse | Format/validate after tool execution | No |
| PermissionRequest | Auto-approve/deny permissions | No |
| Stop | Verify completion before stopping | No |
| SubagentStop | Validate subagent output | No |
| PreCompact | Backup before context compaction | No |

## Priority Implementations

1. **PostToolUse: Markdown Linter** (LOW effort, HIGH impact)
   - Auto-lint .md files after Write/Edit
   - Filter by extension to avoid .ps1 corruption

2. **PreToolUse: Branch Guard** (LOW effort, MEDIUM impact)
   - Block commits to main/master
   - Implements SESSION-PROTOCOL Phase 4

3. **Stop: Session Validator** (MEDIUM effort, HIGH impact)
   - Verify session log exists with required sections
   - Force continuation if incomplete

## Daem0n-MCP Patterns

Valuable patterns from Daem0n-MCP (DasBluEyedDevil/Daem0n-MCP):

- **Sacred Covenant**: State machine (NotStarted → Communed → Counseled)
- **Preflight Tokens**: Timestamp-based context freshness (5 min TTL)
- **Memory Decay**: Decision/Learning decay, Pattern/Warning permanent
- **Failed Boosting**: 1.5x boost for failed approaches in recall
- **Pre-commit Integration**: Block if pending decisions > 24h

## Matcher Syntax

| Pattern | Example |
|---------|---------|
| Exact tool | `Write` |
| Multiple | `Write\|Edit` |
| All | `*` or empty |
| Command prefix | `Bash(npm test*)` |
| MCP namespace | `mcp__serena__*` |

## Related

- ADR-008: Protocol Automation via Lifecycle Hooks
- ADR-007: Memory-First Architecture
- SESSION-PROTOCOL.md: Protocol requirements

## Related

- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)
- [claude-md-anthropic-best-practices](claude-md-anthropic-best-practices.md)
