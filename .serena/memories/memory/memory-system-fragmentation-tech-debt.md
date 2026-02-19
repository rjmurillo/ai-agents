# Memory System Fragmentation Tech Debt

**Status**: DOCUMENTED (not resolved)
**Priority**: Medium
**Scope**: Cross-cutting (affects multiple workflows)

## Problem Statement

Memory access is fragmented across 4 different interfaces, creating confusion about which to use when:

1. **Memory Skill Scripts** (`.claude/skills/memory/scripts/`)
   - PowerShell scripts providing unified interface
   - Example: `Search-Memory.ps1` (Serena-first with Forgetful augmentation)
   - Example: `Extract-SessionEpisode.ps1` (session replay)
   - Benefits: Unified router, deduplication, format options

2. **Context-Retrieval Agent** (`.claude/agents/context-retrieval.md`)
   - Agent specializing in gathering context before planning/implementation
   - Uses Memory Router skill + direct MCP tools
   - Benefits: Deep exploration, knowledge graph traversal, artifact reading

3. **Forgetful Slash Commands** (`.claude/commands/forgetful/`)
   - Direct Forgetful MCP access via slash commands
   - memory-list, memory-save, memory-explore, memory-search
   - Benefits: Quick access, user-friendly

4. **Direct MCP Tool Calls**
   - execute_forgetful_tool(), mcp__serena__*, mcp__plugin_claude-mem_mcp-search__*
   - Used by agents and scripts
   - Benefits: Full control, programmatic access

## User Feedback

> "The whole memory thing is confusing, fragmented, and duplicative. It needs to be cleaned up in order to be useful. @.claude/agents/context-retrieval.md seems to be the closest for breadth, but the protocol is in @.claude/skills/memory/ so those two need to be reconciled."

## Current State

- context-retrieval.md DOES reference Memory Router (lines 18-44)
- But decision tree for "which interface to use when" is not clear
- Multiple overlapping paths to same functionality

## Reconciliation Needed

1. **Decision Matrix**: Create clear guidance on when to use each interface
   - When to use Memory Skill scripts vs direct MCP
   - When to delegate to context-retrieval agent vs call tools directly
   - When slash commands are appropriate vs skill invocation

2. **Consolidation Options**:
   - Option A: Deprecate direct MCP calls in favor of Memory Skill scripts
   - Option B: Deprecate slash commands, use Memory Skill scripts exclusively
   - Option C: Keep all 4, but document clear decision tree

3. **Documentation**:
   - Update CLAUDE.md with memory interface decision matrix
   - Add "When to Use" section to memory skill SKILL.md
   - Cross-reference between context-retrieval.md and memory skill

## Proposed Decision Matrix (Draft)

| Use Case | Recommended Interface | Why |
|----------|----------------------|-----|
| Quick memory search from CLI | Slash command `/memory-search` | Fastest, no agent overhead |
| Complex context gathering | Invoke `context-retrieval` agent | Deep exploration, graph traversal |
| Script integration | Memory Skill scripts | PowerShell, testable, unified |
| Agent-to-agent memory ops | Direct MCP tools | Programmatic, full control |

## Deferral Rationale

Out of scope for SlashCommandCreator implementation (M1-M7). This is a cross-cutting architectural concern requiring:
- Multi-stakeholder review (users of all 4 interfaces)
- Migration plan if deprecating any interface
- Documentation updates across multiple files

## Next Steps

1. Create GitHub issue to track this tech debt
2. Gather usage data: which interfaces are actually used in practice?
3. Propose consolidation plan in issue discussion
4. Implement after consensus

## Related

- ADR-037: Memory Router (Serena-first with Forgetful augmentation)
- ADR-038: Reflexion Memory Schema
- .claude/skills/memory/SKILL.md
- .claude/agents/context-retrieval.md
- Session 280 (SlashCommandCreator implementation)

## Related

- [memory-001-feedback-retrieval](memory-001-feedback-retrieval.md)
- [memory-architecture-serena-primary](memory-architecture-serena-primary.md)
- [memory-index](memory-index.md)
- [memory-size-001-decomposition-thresholds](memory-size-001-decomposition-thresholds.md)
- [memory-token-efficiency](memory-token-efficiency.md)
