# GitHub Issue Assignment Protocol

## Rule

When starting work on a GitHub issue, **always assign it to yourself** if not already assigned.

## Command

```bash
gh issue edit <number> --add-assignee @me
```

## When to Apply

- At the **start** of work on any issue
- Before making any code changes
- Before creating branches related to the issue

## Rationale

- Prevents duplicate work by signaling ownership
- Provides visibility into who is working on what
- Required by project workflow conventions

## Related

- [github-actions-local-testing-integration](github-actions-local-testing-integration.md)
- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
