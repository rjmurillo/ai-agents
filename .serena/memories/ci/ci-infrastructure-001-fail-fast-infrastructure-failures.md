# Skill: CI-001 Fail-Fast Infrastructure Failures

**Atomicity Score**: 92%
**Source**: Session 04 retrospective - Issue #338 implementation
**Date**: 2025-12-24
**Validation Count**: 1 (Commit 888cc39)
**Tag**: helpful
**Impact**: 8/10 (Reduces debugging time, improves error visibility)

## Statement

Exit with code 1 for infrastructure failures instead of returning verdicts.

## Context

When Copilot CLI timeouts occur, tokens expire, or retries are exhausted with no output.

## Evidence

Commit 888cc39 - Issue #338 implementation in `.github/actions/ai-review/action.yml`:

```bash
# Before: Infrastructure failures returned CRITICAL_FAIL verdict
# After: Job fails immediately with exit 1

if [[ $ATTEMPT -eq ${#RETRY_DELAYS[@]} && -z "$REVIEW_OUTPUT" ]]; then
    echo "::error::=== INFRASTRUCTURE FAILURE - JOB FAILED ==="
    echo "::error::Copilot CLI failed after 3 attempts with no output."
    exit 1  # Fail fast - don't return verdict
fi
```

## Why This Works

### Before (Anti-pattern)

1. Infrastructure failure → `CRITICAL_FAIL` verdict
2. Verdict aggregated with other agent results
3. Root cause obscured in aggregate output
4. Developer must dig through logs

### After (Correct Pattern)

1. Infrastructure failure → Job fails with exit 1
2. GitHub Actions UI shows red X immediately
3. Clear error message visible at job level
4. Root cause obvious (token expired, timeout, etc.)

## When to Use

Apply when:
- External API calls fail (Copilot, Gemini, etc.)
- Authentication/authorization errors occur
- Timeouts or rate limits hit
- Network connectivity issues
- Required secrets missing or invalid

Do NOT use for:
- Code quality issues (return verdict)
- Security findings (return verdict)
- Test failures (return verdict)
- Linting errors (return verdict)

## Related Skills

- skill-ci-002-explicit-retry-timing: Retry mechanism for recoverable failures
- ci-quality-gates: When to block PR vs warn
- ci-ai-integration: AI agent integration patterns

## Success Criteria

- Infrastructure failures visible in GitHub Actions summary
- No need to dig through aggregated results
- Clear actionable error messages
- Job status reflects actual failure (not success with bad verdict)

## Related

- [ci-infrastructure-002-explicit-retry-timing](ci-infrastructure-002-explicit-retry-timing.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-004-error-message-investigation](ci-infrastructure-004-error-message-investigation.md)
- [ci-infrastructure-ai-integration](ci-infrastructure-ai-integration.md)
- [ci-infrastructure-claude-code-action-installer-race-condition](ci-infrastructure-claude-code-action-installer-race-condition.md)
