# Labeler: Matcher Type Selection Any

## Skill-Labeler-003: Matcher Type Selection - ANY

**Statement**: Use `any-glob-to-any-file` when label applies if ANY file matches pattern

**Context**: When labeling based on at least one file matching (most common use case)

**Evidence**:
- Current working config uses this for all simple area labels (area-workflows, area-prompts, etc.)
- actions/labeler docs: "ANY glob must match against ANY changed file"
- Most permissive matching strategy

**Atomicity**: 95%
- Length: 12 words ✓
- Single concept: Matcher selection for ANY logic
- Actionable: Yes
- Clear criteria: Yes

**Tag**: helpful
**Impact**: 8/10 (most common use case)
**Created**: 2025-12-21
**Validated**: 1 (all simple labels work correctly)

**Anti-Pattern**: Using `all-globs-to-all-files` for simple file presence checks

---

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-002-combined-matcher-block-pattern](labeler-002-combined-matcher-block-pattern.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
- [labeler-004-matcher-type-selection-all-files](labeler-004-matcher-type-selection-all-files.md)
