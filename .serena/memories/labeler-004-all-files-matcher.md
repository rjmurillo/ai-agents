# Labeler: All Files Matcher

## Skill-Labeler-004: ALL FILES Matcher

**Statement**: Use `any-glob-to-all-files` when ALL changed files must match at least one pattern.

**Context**: When label should only apply if every changed file meets criteria.

**Example**: Ensure all files in PR are tests.

**Atomicity**: 90%

**Anti-Pattern**: Using `any-glob-to-any-file` when ALL files must match.

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-002-combined-matcher-block-pattern](labeler-002-combined-matcher-block-pattern.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-003-matcher-type-selection-any](labeler-003-matcher-type-selection-any.md)
- [labeler-004-matcher-type-selection-all-files](labeler-004-matcher-type-selection-all-files.md)
