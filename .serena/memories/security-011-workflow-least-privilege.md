# Security Pattern: Workflow Least Privilege Permissions

**Importance**: HIGH
**Date**: 2026-01-04
**Category**: CI/CD Security

## Pattern

Apply least privilege principle to GitHub Actions workflow permissions. Only grant permissions explicitly required by the action.

## Claude Code Action Requirements

For `anthropics/claude-code-action`:

**Required Permissions:**
- `contents: write` - Creates branches and commits code changes
- `issues: write` - Reads/writes issue data and comments
- `pull-requests: write` - Reads/writes PR data and creates/updates PRs
- `id-token: write` - **REQUIRED** for OIDC authentication to exchange for GitHub App token

**NOT Required:**
- Broader permissions like `write-all` or `admin`

**Note on OIDC:** The `id-token: write` permission is required because the action uses OIDC to obtain a GitHub App token for API calls. Without this permission, the action fails with: "Could not fetch an OIDC token."

## Anti-Pattern

```yaml
permissions:
  write-all  # WRONG: Too broad, violates least privilege
```

## Correct Pattern

```yaml
permissions:
  contents: write
  issues: write
  pull-requests: write
  id-token: write  # Required for OIDC authentication
```

## Security Mitigation

When using `id-token: write` with externally-triggerable events, add author association guards:

```yaml
jobs:
  claude-response:
    if: |
      github.event_name == 'issues' ||
      github.event_name == 'pull_request_review' ||
      github.event.comment.author_association == 'MEMBER' ||
      github.event.comment.author_association == 'OWNER' ||
      github.event.comment.author_association == 'COLLABORATOR'
```

This prevents external contributors from triggering workflows that access secrets.

## Verification

Before adding permissions:
1. Check action documentation for minimum requirements
2. Verify if OIDC is actually used (most actions don't need `id-token: write`)
3. Test with reduced permissions to confirm functionality
4. Remove unused permissions

## Common Mistakes

- Adding `id-token: write` by default without verification
- Using `permissions: write-all` for convenience
- Copying permissions from other workflows without analysis
- Not removing deprecated permissions when action updates

## References

- [GitHub Actions Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Anthropic Claude Code Action Documentation](https://github.com/anthropics/claude-code-action)

## Related Memories

- `security-infrastructure-review` - Infrastructure file security patterns
- `ci-infrastructure-quality-gates` - CI/CD quality standards
