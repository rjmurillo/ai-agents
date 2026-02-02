# GITHUB_OUTPUT with Heredocs Pattern

**Statement**: Use heredoc syntax for multi-line outputs in GitHub Actions

**Context**: Setting step outputs with multi-line content

**Evidence**: YAML inputs can't execute shell commands

**Atomicity**: 90%

**Impact**: 7/10

## Pattern

```bash
{
  echo "context<<EOF_CONTEXT"
  echo "## Additional Context"
  echo "$CONTENT"
  echo "EOF_CONTEXT"
} >> $GITHUB_OUTPUT
```

## Why

- YAML inputs can't execute shell commands
- Prepare content in a prior step
- EOF marker must be unique

## Related

- [workflow-authorization-testable-pattern](workflow-authorization-testable-pattern.md)
- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
- [workflow-patterns-batch-changes-reduce-cogs](workflow-patterns-batch-changes-reduce-cogs.md)
- [workflow-patterns-composite-action](workflow-patterns-composite-action.md)
