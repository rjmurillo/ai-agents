# Labeler: Negation Pattern Isolation

## Skill-Labeler-006: Negation Pattern Isolation

**Statement**: Separate negation patterns into dedicated `all-globs-to-all-files` matcher within `all:` block

**Context**: When excluding specific paths from broader pattern match

**Evidence**:
- Working pattern from PR #229 (dae9db1):
  - Positive patterns: `any-glob-to-any-file: ["**/*.md"]`
  - Negative patterns: `all-globs-to-all-files: ["!.agents/**/*.md", "!.serena/**/*.md"]`
  - Combined with `all:` block for AND logic

**Atomicity**: 92%
- Length: 12 words ✓
- Single concept: Negation isolation
- Actionable: Yes
- Evidence-based: Yes

**Tag**: helpful
**Impact**: 9/10 (prevents subtle label misapplication bugs)
**Created**: 2025-12-21
**Validated**: 1 (PR #229 success)

**Anti-Pattern**: Mixing negation and inclusion in same matcher block

---

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total Skills | 6 |
| Average Atomicity | 90% |
| Validated Skills | 3 |
| Impact 9-10 | 3 |
| Impact 6-8 | 3 |
| Evidence Quality | High (failed PRs → working solution) |

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-002-combined-matcher-block-pattern](labeler-002-combined-matcher-block-pattern.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-003-matcher-type-selection-any](labeler-003-matcher-type-selection-any.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
