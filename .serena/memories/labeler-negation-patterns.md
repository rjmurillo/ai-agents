# Labeler: Negation Pattern Handling

## Skill-Labeler-001: Negation Pattern Matcher Selection

**Statement**: Use `all-globs-to-all-files` matcher type for negation patterns in actions/labeler.

**Context**: When excluding paths with `!` prefix in actions/labeler configuration.

**Evidence**:
- PR #226: Used `all-globs-to-all-files` with negation patterns mixed with inclusion - FAILED
- PR #229 (c4799c9): Changed to `any-glob-to-any-file` with negation patterns - FAILED
- PR #229 (dae9db1): Isolated negations in `all-globs-to-all-files` within `all:` block - PASS

**Atomicity**: 85%

**Anti-Pattern**: Using `any-glob-to-any-file` with negation patterns (negations ignored)

## Skill-Labeler-006: Negation Pattern Isolation

**Statement**: Separate negation patterns into dedicated `all-globs-to-all-files` matcher within `all:` block.

**Evidence**: Working pattern from PR #229 (dae9db1):
- Positive patterns: `any-glob-to-any-file: ["**/*.md"]`
- Negative patterns: `all-globs-to-all-files: ["!.agents/**/*.md", "!.serena/**/*.md"]`
- Combined with `all:` block for AND logic

**Atomicity**: 92%

**Anti-Pattern**: Mixing negation and inclusion in same matcher block

## Related

- [labeler-001-negation-pattern-matcher-selection](labeler-001-negation-pattern-matcher-selection.md)
- [labeler-003-any-matcher](labeler-003-any-matcher.md)
- [labeler-004-all-files-matcher](labeler-004-all-files-matcher.md)
- [labeler-005-all-patterns-matcher](labeler-005-all-patterns-matcher.md)
- [labeler-006-negation-pattern-isolation](labeler-006-negation-pattern-isolation.md)
