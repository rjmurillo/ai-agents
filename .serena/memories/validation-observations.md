# Skill Observations: validation

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from validation strategies, pre-commit hooks, and quality gates across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Pre-commit hooks that modify files must ensure modifications pass subsequent validation in the same commit - or don't modify (Session 2026-01-16-session-07, 2026-01-16)
- Test-running hooks should only run tests for changed files, not entire directories - prevents blocking on pre-existing failures (Session 2026-01-16-session-07, 2026-01-16)
- Validation scripts must cover ALL input locations, not just obvious ones (Session 2026-01-16-session-07, 2026-01-16)
- Platform detection should be exhaustive with explicit failure for unknown platforms - no 'else' assumptions (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Provide 'known failures' registry to prevent blocking on pre-existing issues in unrelated code (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Pre-commit hooks that modify must ensure modifications pass validation |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Test-running hooks should only run tests for changed files |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Validation scripts must cover ALL input locations |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Platform detection should be exhaustive with explicit failures |
| 2026-01-16 | 2026-01-16-session-07 | MED | Provide 'known failures' registry |

## Related

- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
- [validation-baseline-triage](validation-baseline-triage.md)
- [validation-domain-index-format](validation-domain-index-format.md)
- [validation-error-messages](validation-error-messages.md)
- [validation-false-positives](validation-false-positives.md)
- [validation-pr-feedback](validation-pr-feedback.md)
- [validation-pr-gates](validation-pr-gates.md)
- [validation-skepticism](validation-skepticism.md)
- [validation-test-first](validation-test-first.md)
- [validation-tooling-patterns](validation-tooling-patterns.md)