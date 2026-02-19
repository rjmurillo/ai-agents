# Labeler: Negation Pattern Matcher Selection

## Skill-Labeler-001: Negation Pattern Matcher Selection

**Statement**: Use `all-globs-to-all-files` matcher type for negation patterns in actions/labeler

**Context**: When excluding paths with `!` prefix in actions/labeler configuration

**Evidence**:
- PR #226: Used `all-globs-to-all-files` with negation patterns mixed with inclusion - FAILED
- PR #229 (c4799c9): Changed to `any-glob-to-any-file` with negation patterns - FAILED
- PR #229 (dae9db1): Isolated negations in `all-globs-to-all-files` within `all:` block - PASS

**Atomicity**: 85%
- Length: 11 words ✓
- Single concept: Negation matcher type
- Actionable: Yes
- Evidence-based: Yes

**Tag**: helpful
**Impact**: 9/10 (prevents label misapplication on excluded paths)
**Created**: 2025-12-21
**Validated**: 1 (PR #229 success)

**Anti-Pattern**: Using `any-glob-to-any-file` with negation patterns (negations ignored)

---

## Related

- [labeler-002-combined-matcher-block-pattern](labeler-002-combined-matcher-block-pattern.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-003-matcher-type-selection-any](labeler-003-matcher-type-selection-any.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
- [labeler-004-matcher-type-selection-all-files](labeler-004-matcher-type-selection-all-files.md)
