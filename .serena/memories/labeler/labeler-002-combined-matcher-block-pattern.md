# Labeler: Combined Matcher Block Pattern

## Skill-Labeler-002: Combined Matcher Block Pattern

**Statement**: Combine inclusion and exclusion patterns using `all:` block with separate matchers

**Context**: When applying label based on file matches but excluding specific paths

**Evidence**:
- PR #229 (dae9db1): Working config structure:
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

**Atomicity**: 90%
- Length: 11 words ✓
- Single concept: Pattern combination strategy
- Actionable: Yes
- Evidence-based: Yes

**Tag**: helpful
**Impact**: 10/10 (critical for correct exclusion logic)
**Created**: 2025-12-21
**Validated**: 1 (PR #229 success)

**Anti-Pattern**: Mixing inclusion and exclusion in single matcher block

---

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-003-matcher-type-selection-any](labeler-003-matcher-type-selection-any.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
- [labeler-004-matcher-type-selection-all-files](labeler-004-matcher-type-selection-all-files.md)
