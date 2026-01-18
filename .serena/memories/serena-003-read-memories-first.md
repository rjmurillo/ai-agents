# Skill: Read Memories Before Starting Work

**Skill ID**: skill-serena-003-read-memories-first
**Category**: Memory Management
**Impact**: Critical (90% cost reduction via caching)
**Status**: Mandatory

## Trigger Condition

At start of any multi-step task or session continuation.

## Action Pattern

1. Call `mcp__serena__list_memories()` to see available context
2. Call `mcp__serena__read_memory(memory_name)` for relevant memories
3. Start work with loaded context

## Cost Benefit

LLM prompt caching reduces cost by 90% when context prefix (memories) remains stable across requests.

## Evidence

From SERENA-BEST-PRACTICES.md lines 315-323:
- Memories enable prompt caching
- Caching provides 90% cost reduction
- Must load memories before work to enable cache

## Example

```text
# Workflow for continuation task
1. mcp__serena__list_memories()
   # Shows: ["project-overview", "phase2-handoff-context", ...]

2. mcp__serena__read_memory("project-overview")
   mcp__serena__read_memory("phase2-handoff-context")
   # Context loaded into cache prefix

3. Start implementation
   # All subsequent requests benefit from cached context
```

## Atomicity Score

95% - Single concept: load memories before work for caching benefit

## Validation Count

0 (newly extracted)

## Related Skills

- skill-init-001-session-initialization
- skill-memory-001-feedback-retrieval
