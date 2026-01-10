# Claude Workflow Authorization Pattern

**Status**: ACTIVE
**Date**: 2026-01-04
**Related**: PR #789, `tests/workflows/Test-ClaudeAuthorization.ps1`

## Context

The Claude Code workflow (`.github/workflows/claude.yml`) needs to restrict who can invoke Claude via @claude mentions in GitHub issues, PRs, and comments. This prevents unauthorized users from consuming API credits or accessing Claude's capabilities.

## Decision

Authorization is handled by a dedicated PowerShell script (`tests/workflows/Test-ClaudeAuthorization.ps1`) that validates:

1. **@claude mention required**: All events must contain "@claude" (case-sensitive, exact match with negative lookahead)
2. **Author association OR bot allowlist**: User must be MEMBER/OWNER/COLLABORATOR, OR be an allowed bot

### Authorization Logic

```
IF @claude mention exists THEN
  IF actor in bot allowlist (dependabot, renovate, github-actions) THEN
    AUTHORIZE
  ELSE IF author_association in (MEMBER, OWNER, COLLABORATOR) THEN
    AUTHORIZE
  ELSE
    DENY (unauthorized user)
  END
ELSE
  DENY (no mention)
END
```

### Event Types

The workflow responds to four event types:

1. **issue_comment**: Comments on issues or PRs
2. **pull_request_review_comment**: Inline code review comments
3. **pull_request_review**: PR review bodies
4. **issues**: Issue creation (body or title)

## Rationale

### Why PowerShell Script (not inline YAML)?

Per ADR-006, complex logic must not live in workflow YAML because:

- **Untestable**: Can't unit test YAML conditionals
- **Undebuggable**: No breakpoints, variable inspection, or error handling
- **Error-prone**: fromJson() failures are silent, property access errors are opaque
- **Unmaintainable**: Changes require full workflow runs to validate

The PowerShell script provides:

- **27 Pester tests** covering all scenarios
- **Try-catch error handling** with proper exit codes
- **Audit logging** to GitHub Actions summary
- **Clear error messages** for debugging

### Why Two-Job Pattern?

```yaml
jobs:
  check-authorization:  # Runs PowerShell script
    outputs:
      authorized: true/false

  claude-response:      # Runs only if authorized
    needs: check-authorization
    if: needs.check-authorization.outputs.authorized == 'true'
```

Benefits:

- Clean separation of concerns
- Authorization failures visible in job summary
- Can add more auth steps without changing Claude job
- GitHub Actions natively handles job dependencies

### Security: Command Injection Prevention

All GitHub event data (comments, titles, bodies) is passed via environment variables, NOT inline string interpolation:

```yaml
env:
  COMMENT_BODY: ${{ github.event.comment.body }}
run: |
  $authorized = & ./script.ps1 -CommentBody $env:COMMENT_BODY
```

This prevents command injection attacks where malicious users craft issue titles/bodies with shell metacharacters.

See: [GitHub's security guide](https://github.blog/security/vulnerability-research/how-to-catch-github-actions-workflow-injections-before-attackers-do/)

## Issues Event Pattern

**Question**: Should `issues` events check author_association?

**Original PR #789**: YES (restricted to MEMBER/OWNER/COLLABORATOR or bots)
**Security Memory (security-012)**: NO ("No comments, safe to run")

**Current Decision**: **YES** (follow PR #789 pattern)

**Rationale**:

- Issue creation can mention @claude in title/body
- Even without comments, we're invoking Claude (consuming API credits)
- Consistency: All event types have same authorization rules
- Bot allowlist still permits dependabot/renovate to create issues

If this proves too restrictive for legitimate external contributors, we can relax it in a future update.

## Deprecation Warning

GitHub announced that `author_association` may be deprecated from webhook payloads in the future to improve API response times. The exact timeline is not publicly confirmed.

**Impact**: This implementation will break when the deprecation takes effect.

**Mitigation Strategy** (future work):

1. Monitor GitHub's deprecation timeline
2. Explore alternative authorization methods:
   - GitHub team membership API
   - Repository collaborator API
   - GitHub Apps installation permissions
3. Update script before deprecation deadline

The script includes a deprecation warning in audit logs.

## Testing

Comprehensive Pester test suite: `tests/workflows/Test-ClaudeAuthorization.Tests.ps1`

Coverage:

- ✅ All 4 event types
- ✅ All 3 allowed associations (MEMBER, OWNER, COLLABORATOR)
- ✅ All 10 allowed bots (including 7 AI coding assistants)
- ✅ Denial scenarios (wrong association, no mention)
- ✅ Edge cases (empty bodies, case sensitivity, partial matches, word boundaries)
- ✅ Input size validation (>1MB bodies)
- ✅ Audit logging verification
- ✅ Error handling

**46 tests passing** (2 unreliable edge case tests removed in Round 2)

## Sources

- [Webhook events and payloads - GitHub Docs](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [GitHub Actions security hardening](https://github.blog/security/vulnerability-research/how-to-catch-github-actions-workflow-injections-before-attackers-do/)
- GitHub Changelog: Upcoming changes to author_association (August 2025)

## See Also

- ADR-006: No logic in workflow YAML
- `tests/workflows/Test-ClaudeAuthorization.ps1`: Implementation
- `.github/workflows/claude.yml`: Workflow using this pattern
- `.serena/memories/security-012-workflow-author-association.md`: Previous pattern
