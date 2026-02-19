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

## TOCTOU Race Conditions in Multi-Process Hooks

### Anti-Pattern: Security Check in Child Process

```bash
# PowerShell script checks for symlinks
RESULT=$(pwsh -File sync-script.ps1)  # Symlink check happens here
git add -- "$FILE"                     # But staging happens here - RACE WINDOW
```

### TOCTOU Problem

Time-of-check to time-of-use (TOCTOU) race condition when:

1. Security validation runs in a child process (e.g., PowerShell)
2. Subsequent action runs in the parent process (e.g., git add)

An attacker can replace the file with a symlink between process completion and the parent's action.

### Solution: Defense-in-Depth

Always re-validate security conditions in the same process that performs the action:

```bash
RESULT=$(pwsh -File sync-script.ps1)  # First check in PowerShell
if [ -L "$FILE" ]; then               # Defense-in-depth check in bash
    echo "Error: symlink detected"
else
    git add -- "$FILE"                # Action in same process as check
fi
```

### Key Insight

CodeRabbit correctly identified that PowerShell's symlink check only runs when the file exists. On first run (or after deletion), the file is created without symlink validation. Defense-in-depth catches this gap.

### TOCTOU References

- Issue: PR #52 comment 2628504961 (CodeRabbit TOCTOU analysis)
- Fix: Commit 8d9c05a
- Original symlink check: PowerShell lines 94-98, 144-148
- Defense-in-depth check: `.githooks/pre-commit` line 306

## References

- Grep pattern issue: PR #52 comment 2628441553
- Grep fix: Commit cd4c6b2
- TOCTOU issue: PR #52 comment 2628504961
- TOCTOU fix: Commit 8d9c05a
- File: `.githooks/pre-commit`
- QA Report: `.agents/qa/PR-52-grep-pattern-fix-verification.md`

## Related

- [pattern-agent-generation-three-platforms](pattern-agent-generation-three-platforms.md)
- [pattern-github-actions-variable-evaluation](pattern-github-actions-variable-evaluation.md)
- [pattern-handoff-merge-session-histories](pattern-handoff-merge-session-histories.md)
- [pattern-single-source-of-truth-workflows](pattern-single-source-of-truth-workflows.md)
- [pattern-thin-workflows](pattern-thin-workflows.md)
