# Labeler: Matcher Type Selection All Patterns

## Skill-Labeler-005: Matcher Type Selection - ALL PATTERNS

**Statement**: Use `all-globs-to-any-file` when ALL patterns must find matches somewhere in changeset

**Context**: When label requires multiple pattern types to be present

**Evidence**:
- actions/labeler docs: "ALL globs must match against ANY changed file"
- Example: Label when both `.ts` AND `.test.ts` files changed

**Atomicity**: 88%
- Length: 13 words ✓
- Single concept: Multi-pattern requirement
- Actionable: Yes

**Tag**: helpful
**Impact**: 6/10 (specialized use case)
**Created**: 2025-12-21
**Validated**: 0 (not yet used but documented)

**Anti-Pattern**: Using multiple separate matchers expecting AND logic (they OR by default)

---

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-002-combined-matcher-block-pattern](labeler-002-combined-matcher-block-pattern.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-003-matcher-type-selection-any](labeler-003-matcher-type-selection-any.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
