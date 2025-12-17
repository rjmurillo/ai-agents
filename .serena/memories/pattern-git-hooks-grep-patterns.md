# Git Hooks - Grep Pattern Best Practices

## Context

Learnings from PR #52 grep pattern bug fix in pre-commit hook.

## Issue Pattern: Substring Matching on Multi-line Output

### Anti-Pattern

```bash
OUTPUT=$(command_that_returns_boolean_and_messages 2>&1)
if echo "$OUTPUT" | grep -q "True"; then
    # BUG: Matches "True" anywhere, including in paths
fi
```

### Problem

When a script outputs both status messages and boolean return values:

```text
MCP config already in sync: /Users/TrueUser/repo/mcp.json
False
```

Substring grep matches "True" in the path even when boolean is "False".

### Solution

Use anchored patterns for exact line matching:

```bash
OUTPUT=$(command_that_returns_boolean_and_messages 2>&1)
if echo "$OUTPUT" | grep -q '^True$'; then
    # FIXED: Matches only exact line "True"
fi
```

## Best Practices for Git Hooks

### 1. Anchor Grep Patterns

Always use `^` and `$` when matching specific values:

- `grep -E '\.md$'` - Match file extensions
- `grep -q '^True$'` - Match exact boolean
- `grep -E '^[^/]'` - Match non-path lines

### 2. Validate Multi-line Output

When parsing command output containing multiple types of data:

1. Use anchored patterns for exact matches
2. Consider splitting output into separate channels (stdout/stderr)
3. Use structured output (JSON) if possible

### 3. Test Edge Cases

Common edge cases for path-based false positives:

- Paths containing keywords ("True", "False", "Success")
- Paths with special characters
- Paths with spaces or newlines

### 4. Security Considerations

- MEDIUM-002: Reject symlinks to prevent TOCTOU attacks
- CRITICAL-001: Use arrays and proper quoting to prevent injection
- HIGH-001: Use while/read loops for files with spaces

## Reference

- Issue: PR #52 comment 2628441553
- Fix: Commit cd4c6b2
- File: `.githooks/pre-commit` line 303
- QA Report: `.agents/qa/PR-52-grep-pattern-fix-verification.md`
