# Security Pattern: Workflow Author Association Restrictions

**Importance**: HIGH
**Date**: 2026-01-04
**Category**: CI/CD Security

## Pattern

Restrict comment-triggered GitHub Actions workflows to trusted author associations to prevent untrusted users from triggering workflows with write permissions and secret access.

## Vulnerability

Comment-triggered workflows (`issue_comment`, `pull_request_review_comment`) can be triggered by ANY user who can comment on the repository (including public contributors), potentially allowing:

- Secret exposure through workflow logs
- Unauthorized code execution with write permissions
- Repository modification by untrusted actors

## Secure Pattern

Add job-level conditional checking author association:

```yaml
jobs:
  job-name:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'issues' ||
      github.event_name == 'pull_request_review' ||
      github.event.comment.author_association == 'MEMBER' ||
      github.event.comment.author_association == 'OWNER' ||
      github.event.comment.author_association == 'COLLABORATOR'
```

## Trusted Author Associations

**Allow:**
- `MEMBER` - Organization/repository members
- `OWNER` - Repository owners
- `COLLABORATOR` - Users with explicit collaborator access

**Deny:**
- `CONTRIBUTOR` - Previous contributors (not currently trusted)
- `FIRST_TIME_CONTRIBUTOR` - First-time contributors
- `NONE` - No association

## Bot Allowlists

Replace wildcard bot allowlists with specific trusted bots:

```yaml
# INSECURE
allowed_bots: "*"

# SECURE
allowed_bots: "dependabot[bot],renovate[bot],github-actions[bot]"
```

## Event Handling

- `issues` events: No comments, safe to run
- `pull_request_review` events: No comments, safe to run
- `issue_comment` events: Requires author association check
- `pull_request_review_comment` events: Requires author association check

## Verification

Test the conditional with different author associations:

1. Comment as MEMBER - should trigger
2. Comment as OWNER - should trigger
3. Comment as FIRST_TIME_CONTRIBUTOR - should NOT trigger
4. Create issue as any user - should trigger
5. Submit PR review as MEMBER - should trigger

## References

- [GitHub Author Association Values](https://docs.github.com/en/graphql/reference/enums#commentauthorassociation)
- [GitHub Actions Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)

## Related Memories

- `security-011-workflow-least-privilege` - Permission scoping
- `security-infrastructure-review` - Infrastructure security patterns
