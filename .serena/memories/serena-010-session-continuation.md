# Skill: Use prepare_for_new_conversation for Session Continuation

**Skill ID**: skill-serena-010-session-continuation
**Category**: Memory Management
**Impact**: Critical (enables continuation without context loss)
**Status**: Mandatory when approaching token limits

## Trigger Condition

When session is approaching token limit or needs to continue in new session.

## Action Pattern

1. Call `mcp__serena__prepare_for_new_conversation` to generate summary
2. Call `mcp__serena__write_memory(name, summary)` to persist
3. Start new session
4. Call `mcp__serena__read_memory(name)` to restore context

## Cost Benefit

Enables unlimited work by breaking into sessions while preserving context. Prevents context loss and allows LLM caching in new session.

## Evidence

From SERENA-BEST-PRACTICES.md lines 387-394:
- prepare_for_new_conversation creates summary
- Store in memory for next session
- Read memory to continue work

## Example

```text
# End of session approaching limit
1. summary = mcp__serena__prepare_for_new_conversation()
2. mcp__serena__write_memory("session-37-continuation", summary)

# New session
3. mcp__serena__read_memory("session-37-continuation")
4. Continue work with full context restored
```

## Atomicity Score

88% - Single concept: use prepare_for_new_conversation for session continuation

## Validation Count

0 (newly extracted)

## Related Skills

- skill-serena-003-read-memories-first
- skill-serena-011-cache-worktree-sharing
