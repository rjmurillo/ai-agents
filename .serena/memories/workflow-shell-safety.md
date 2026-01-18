# Shell Interpolation Safety Pattern

**Statement**: Use env vars for safe interpolation; never interpolate user content directly

**Context**: GitHub Actions workflows handling PR content

**Evidence**: Security review - GitHub context values can contain shell metacharacters

**Atomicity**: 97%

**Impact**: 10/10 (CRITICAL)

## Anti-Pattern

```yaml
# BAD - vulnerable to injection
run: |
  echo "${{ github.event.pull_request.body }}"
```

## Solution

```yaml
# GOOD - safe from injection
env:
  PR_BODY: ${{ github.event.pull_request.body }}
run: |
  echo "$PR_BODY"
```

## Why

GitHub context values can contain shell metacharacters. Env vars are properly escaped.

## Always Use Env Vars For

- `github.event.pull_request.body`
- `github.event.issue.body`
- `github.event.comment.body`
- Any user-controlled content

## Related

- [workflow-authorization-testable-pattern](workflow-authorization-testable-pattern.md)
- [workflow-batch-changes-reduce-cogs](workflow-batch-changes-reduce-cogs.md)
- [workflow-composite-action](workflow-composite-action.md)
- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
