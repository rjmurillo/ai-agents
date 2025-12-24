# Skill-Labeler-002: Combined Matcher Block Pattern

**Statement**: Combine inclusion and exclusion patterns using `all:` block with separate matchers.

**Context**: When applying label based on file matches but excluding specific paths.

**Atomicity**: 90%

**Impact**: 10/10 (critical for correct exclusion logic)

## Working Configuration

```yaml
documentation:
  - all:
      - changed-files:
          - any-glob-to-any-file:
              - "**/*.md"
      - changed-files:
          - all-globs-to-all-files:
              - "!.agents/**/*.md"
```

## Pattern Explanation

1. **`all:` block**: Requires ALL conditions to match (AND logic)
2. **First matcher**: Uses `any-glob-to-any-file` for positive patterns
3. **Second matcher**: Uses `all-globs-to-all-files` for negation patterns
4. **Result**: Label applies when file matches AND doesn't match exclusions

## Anti-Pattern

Mixing inclusion and exclusion in single matcher block:

```yaml
# WRONG - negations may be ignored
documentation:
  - changed-files:
      - any-glob-to-any-file:
          - "**/*.md"
          - "!.agents/**/*.md"  # May not work as expected
```
