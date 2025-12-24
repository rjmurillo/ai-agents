# Labeler: Matcher Type Selection

## Skill-Labeler-003: ANY Matcher

**Statement**: Use `any-glob-to-any-file` when label applies if ANY file matches pattern.

**Context**: When labeling based on at least one file matching (most common use case).

**Evidence**: Current working config uses this for all simple area labels.

**Atomicity**: 95%

## Skill-Labeler-004: ALL FILES Matcher

**Statement**: Use `any-glob-to-all-files` when ALL changed files must match at least one pattern.

**Context**: When label should only apply if every changed file meets criteria.

**Example**: Ensure all files in PR are tests.

**Atomicity**: 90%

**Anti-Pattern**: Using `any-glob-to-any-file` when ALL files must match.

## Skill-Labeler-005: ALL PATTERNS Matcher

**Statement**: Use `all-globs-to-any-file` when ALL patterns must find matches somewhere in changeset.

**Context**: When label requires multiple pattern types to be present.

**Example**: Label when both `.ts` AND `.test.ts` files changed.

**Atomicity**: 88%

**Anti-Pattern**: Using multiple separate matchers expecting AND logic (they OR by default).

## Matcher Reference

| Matcher | Logic | Use When |
|---------|-------|----------|
| `any-glob-to-any-file` | ANY → ANY | Simple presence check |
| `all-globs-to-all-files` | ALL → ALL | Negation patterns |
| `any-glob-to-all-files` | ANY → ALL | All files must match |
| `all-globs-to-any-file` | ALL → ANY | Multiple patterns required |
