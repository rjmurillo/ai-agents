# Skill-Labeler-001: Negation Pattern Matcher Selection

**Statement**: Use `all-globs-to-all-files` matcher type for negation patterns in actions/labeler.

**Context**: When excluding paths with `!` prefix in actions/labeler configuration.

**Evidence**:

- PR #226: Used `all-globs-to-all-files` with negation patterns mixed with inclusion - FAILED
- PR #229 (c4799c9): Changed to `any-glob-to-any-file` with negation patterns - FAILED
- PR #229 (dae9db1): Isolated negations in `all-globs-to-all-files` within `all:` block - PASS

**Atomicity**: 85%

**Anti-Pattern**: Using `any-glob-to-any-file` with negation patterns (negations ignored)
