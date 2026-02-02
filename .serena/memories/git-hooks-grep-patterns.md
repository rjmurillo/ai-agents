# Grep Pattern Best Practices in Hooks

**Statement**: Use anchored patterns (`^True$`) for exact matches; avoid substring matches

**Context**: Parsing command output in pre-commit hooks

**Evidence**: PR #52 - "True" matched in path `/Users/TrueUser/repo/file.json`

**Atomicity**: 90%

**Impact**: 7/10

## Anti-Pattern

```bash
if echo "$OUTPUT" | grep -q "True"; then  # BUG: substring match
```

**Problem**: Matches "True" in paths like `/Users/TrueUser/repo/file.json`

## Solution

```bash
if echo "$OUTPUT" | grep -q '^True$'; then  # FIXED: exact line match
```

## Best Practices

| Pattern | Use Case |
|---------|----------|
| `grep -E '\.md$'` | Match file extensions |
| `grep -q '^True$'` | Match exact boolean |
| `grep -E '^[^/]'` | Match non-path lines |
| `grep -n "pattern"` | Include line numbers |

## Related

- [git-hooks-001-pre-commit-branch-validation](git-hooks-001-pre-commit-branch-validation.md)
- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
