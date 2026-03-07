# GitHub Keywords and PR Etiquette

## Issue Linking Keywords

GitHub supports 9 keywords for auto-closing issues when PRs merge:

| Group | Keywords |
|-------|----------|
| Close | `close`, `closes`, `closed` |
| Fix | `fix`, `fixes`, `fixed` |
| Resolve | `resolve`, `resolves`, `resolved` |

**Syntax**: `Keyword #issue-number` or `Keyword owner/repo#number` for cross-repo.

**Case-insensitive**: All variants work.

## Conventional Commits Format

```text
<type>(<scope>): <what changed>
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `ci`, `build`, `chore`, `test`, `perf`, `style`

**Breaking changes**: Add `!` after type/scope: `feat(api)!: remove v1`

## PR Template Sections

1. **Summary**: 2-4 bullets, what + why
2. **Specification References**: Issue links, spec files
3. **Changes**: Bullet list matching diff structure
4. **Type of Change**: Classification checkboxes
5. **Testing**: Coverage verification
6. **Agent Review**: Security-sensitive file listing
7. **Checklist**: Self-review verification

## Spec Requirements by PR Type

| Type | Required? |
|------|-----------|
| `feat:` | Required (link issue or `.agents/planning/`) |
| `fix:` | Optional (link issue if exists) |
| `refactor:` | Optional |
| `docs:` | Not required |
| `ci:`, `build:` | Optional (link ADR if architecture impacted) |

## Etiquette Rules

1. **Small PRs**: Single purpose, easier review
2. **Complete template**: Treat as contract with reviewers
3. **Self-review first**: Check for debug code, config drift
4. **Wait for green CI**: Don't request review with red checks
5. **Respond with action + location**: Save reviewer lookup time
6. **No force push after review**: Invalidates comment context

## Reference

- Analysis: `.agents/analysis/github-keywords-pr-etiquette.md`
- PR Template: `.github/PULL_REQUEST_TEMPLATE.md`
- GitHub Docs: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/using-keywords-in-issues-and-pull-requests

## Related

- [github-actions-local-testing-integration](github-actions-local-testing-integration.md)
- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
