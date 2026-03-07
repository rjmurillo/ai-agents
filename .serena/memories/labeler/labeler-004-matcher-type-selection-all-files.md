# Labeler: Matcher Type Selection All Files

## Skill-Labeler-004: Matcher Type Selection - ALL FILES

**Statement**: Use `any-glob-to-all-files` when ALL changed files must match at least one pattern

**Context**: When label should only apply if every changed file meets criteria

**Evidence**:
- actions/labeler docs: "ANY glob must match against ALL changed files"
- Use case: Ensure all files in PR meet quality criteria (e.g., all files are tests)

**Atomicity**: 90%
- Length: 14 words ✓
- Single concept: Universal file requirement
- Actionable: Yes

**Tag**: helpful
**Impact**: 7/10 (less common but important for strict requirements)
**Created**: 2025-12-21
**Validated**: 0 (not yet used in our config but documented)

**Anti-Pattern**: Using `any-glob-to-any-file` when ALL files must match

---

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-002-combined-matcher-block-pattern](labeler-002-combined-matcher-block-pattern.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-003-matcher-type-selection-any](labeler-003-matcher-type-selection-any.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
