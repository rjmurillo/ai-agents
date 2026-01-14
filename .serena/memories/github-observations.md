# Skill Observations: github

**Last Updated**: 2026-01-14
**Sessions Analyzed**: 2

## Purpose

This memory captures learnings from using the `github` skill across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- For batch operations (reactions, labels), use gh api graphql with parallel mutations. Break into batches of 5 to avoid complexity limits. (Session 2026-01-14, 2026-01-14)
- Use mutation aliases (c1, c2, etc.) for batch GraphQL operations to track individual results. (Session 2026-01-14, 2026-01-14)

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- Use `gh pr comment` to keep PRs updated with major enhancements (Session 2026-01-13-session-906, 2026-01-13)

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-13 | 2026-01-13-session-906 | LOW | Use gh pr comment to keep PRs updated with major enhancements |
| 2026-01-14 | 2026-01-14 | MED | Use gh api graphql with parallel mutations for batch operations |
| 2026-01-14 | 2026-01-14 | MED | Use mutation aliases for batch GraphQL operations |

## Related

- [github-actions-local-testing-integration](github-actions-local-testing-integration.md)
- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
