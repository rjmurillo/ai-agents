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
