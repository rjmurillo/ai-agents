# Skill-Labeler-004: ALL FILES Matcher

**Statement**: Use `any-glob-to-all-files` when ALL changed files must match at least one pattern.

**Context**: When label should only apply if every changed file meets criteria.

**Example**: Ensure all files in PR are tests.

**Atomicity**: 90%

**Anti-Pattern**: Using `any-glob-to-any-file` when ALL files must match.
