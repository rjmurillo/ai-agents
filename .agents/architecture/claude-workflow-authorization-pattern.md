# Claude Workflow Authorization Pattern

**Status**: ACTIVE
**Date**: 2026-01-04
**Related**: PR #789, `tests/workflows/test_claude_authorization.py`

## Context

The Claude Code workflow (`.github/workflows/claude.yml`) needs to restrict who can invoke Claude via @claude mentions in GitHub issues, PRs, and comments. This prevents unauthorized users from consuming API credits or accessing Claude's capabilities.

## Decision

Authorization is handled by a dedicated Python script (`tests/workflows/test_claude_authorization.py`) that validates:

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

### Why Dedicated Script (not inline YAML)?

Per ADR-006, complex logic must not live in workflow YAML because:

- **Untestable**: Can't unit test YAML conditionals
- **Undebuggable**: No breakpoints, variable inspection, or error handling
- **Error-prone**: fromJson() failures are silent, property access errors are opaque
- **Unmaintainable**: Changes require full workflow runs to validate

The Python script provides:

- **109 pytest tests** covering all scenarios
- **Try-except error handling** with proper exit codes
- **Audit logging** to GitHub Actions summary
- **Clear error messages** for debugging

### Why Two-Job Pattern?

```yaml
jobs:
  check-authorization:  # Runs Python script
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
  authorized=$(python3 ./tests/workflows/test_claude_authorization.py --comment-body "$COMMENT_BODY")
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

Comprehensive pytest suite: `tests/test_claude_authorization.py`

Coverage:

- All 6 event types (issue_comment, pull_request_review_comment, pull_request_review, issues, pull_request, workflow_dispatch)
- All 3 allowed associations (MEMBER, OWNER, COLLABORATOR)
- All 10 allowed bots (including AI coding assistants)
- Denial scenarios (wrong association, no mention)
- Edge cases (empty bodies, case sensitivity, partial matches, word boundaries)
- Input size validation (>1MB bodies)
- Audit logging verification
- Error handling (exit codes 0, 1, 2)

**109 tests passing** at 99% line coverage

## Sources

- [Webhook events and payloads - GitHub Docs](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
- [GitHub Actions security hardening](https://github.blog/security/vulnerability-research/how-to-catch-github-actions-workflow-injections-before-attackers-do/)
- GitHub Changelog: Upcoming changes to author_association (August 2025)

## See Also

- ADR-006: No logic in workflow YAML
- `tests/workflows/test_claude_authorization.py`: Implementation
- `tests/test_claude_authorization.py`: pytest test suite (109 tests)
- `.github/workflows/claude.yml`: Workflow using this pattern
- `.serena/memories/security-012-workflow-author-association.md`: Previous pattern
