# Skill Observations: github

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 5

## Purpose

This memory captures learnings from using the `github` skill across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Always use GitHub skill PowerShell scripts instead of raw gh commands when script exists (Session 2026-01-16-session-07, 2026-01-16)
- Route GitHub URLs to API calls, never fetch HTML directly (Session 2026-01-16-session-07, 2026-01-16)
- Use GraphQL API for review thread resolution - REST API does not support resolveReviewThread operation (Session 07, 2026-01-16)
  - Evidence: Session 38 - REST API research led to GraphQL discovery, thread resolution succeeded via GraphQL mutation

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- For batch operations (reactions, labels), use gh api graphql with parallel mutations. Break into batches of 5 to avoid complexity limits. (Session 2026-01-14, 2026-01-14)
- Use mutation aliases (c1, c2, etc.) for batch GraphQL operations to track individual results. (Session 2026-01-14, 2026-01-14)
- Use GraphQL batch mutations for resolving multiple threads efficiently (single API call for 5+ threads) (Session 2026-01-14-session-907, 2026-01-15)
- Prioritize github skill scripts > gh api > gh commands for routing (Session 2026-01-16-session-07, 2026-01-16)
- When github skill script doesn't exist for URL pattern, use gh api with specific endpoint (e.g., repos/{owner}/{repo}/contents/...) (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- dorny/paths-filter requires checkout in ALL workflow jobs, not just jobs using the filter output (Session 07, 2026-01-16)
  - Evidence: Session 38 - docs-only filter unused after discovering global checkout requirement
- Workflow re-run executes on main branch, not PR branch - cannot use re-run to validate PR fixes, requires dummy commit to trigger PR run (Session 07, 2026-01-16)
  - Evidence: Session 38 - workflow re-run behavior discovery, cannot validate PR changes via manual re-run
- Bot PR authors need @mention to monitor PR feedback - don't automatically track review comments without explicit notification (Session 07, 2026-01-16)
  - Evidence: Session 38 - Issue #152 created after PR #121 revealed bot author awareness gap

## Notes for Review (LOW confidence)

These are observations that may become patterns:

- Use `gh pr comment` to keep PRs updated with major enhancements (Session 2026-01-13-session-906, 2026-01-13)

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-13 | 2026-01-13-session-906 | LOW | Use gh pr comment to keep PRs updated with major enhancements |
| 2026-01-14 | 2026-01-14 | MED | Use gh api graphql with parallel mutations for batch operations |
| 2026-01-14 | 2026-01-14 | MED | Use mutation aliases for batch GraphQL operations |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Always use GitHub skill PowerShell scripts instead of raw gh commands |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Route GitHub URLs to API calls, never fetch HTML directly |
| 2026-01-16 | Session 07 | HIGH | Use GraphQL API for review thread resolution (REST doesn't support it) |
| 2026-01-16 | 2026-01-16-session-07 | MED | Prioritize github skill scripts > gh api > gh commands |
| 2026-01-16 | 2026-01-16-session-07 | MED | When github skill script doesn't exist, use gh api with specific endpoint |
| 2026-01-16 | Session 07 | MED | dorny/paths-filter requires checkout in ALL workflow jobs |
| 2026-01-16 | Session 07 | MED | Workflow re-run executes on main branch not PR branch |
| 2026-01-16 | Session 07 | MED | Bot PR authors need @mention for PR feedback monitoring |

## Related

- [github-actions-local-testing-integration](github-actions-local-testing-integration.md)
- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
