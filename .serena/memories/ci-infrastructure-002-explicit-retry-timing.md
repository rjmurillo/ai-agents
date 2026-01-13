# CI Infrastructure: Explicit Retry Timing

**Issue**: #163, #338, #328
**Component**: AI Review composite action
**Pattern**: Exponential backoff for transient failures

## Retry Configuration

### Timing Pattern

```bash
# Issue #163 spec: Exponential backoff for rate limit recovery
RETRY_DELAYS=(0 30 60)  # seconds before each attempt
```

| Attempt | Delay Before | Cumulative Wait |
|---------|--------------|-----------------|
| 1       | 0s           | 0s              |
| 2       | 30s          | 30s             |
| 3       | 60s          | 90s             |

### Historical Evolution

| Issue | Timing | Rationale |
|-------|--------|-----------|
| #338  | (0 10 30) | Initial retry with quick backoff (40s total) |
| #163  | (0 30 60) | Longer backoff for rate limit recovery (90s total) |

## Implementation Location

`.github/actions/ai-review/action.yml` lines 516-615

## Key Learnings

### "Job-Level Retry" Terminology

Issue #163 requested "job-level retry for matrix jobs" but investigation revealed:

1. **GitHub Actions Limitation**: No native job-level retry for matrix jobs (feature request dormant since 2024)
2. **Existing Implementation**: Composite action already provides retry at step level
3. **Actual Gap**: Retry timing didn't match requirements (10s/30s vs 30s/60s)

**Lesson**: "Job-level retry" in CI context often means "retry the critical step" not "retry the entire job construct"

### Third-Party Options Considered

- `nick-fields/retry@v3`: Wraps steps for retry
- `Wandalen/wretry.action`: Similar functionality

**Decision**: Update existing retry logic rather than add wrapper (simpler, fewer dependencies)

## Related

- [issue-338-retry-implementation](issue-338-retry-implementation.md): Original retry implementation
- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md): Failure categorization
- [ci-infrastructure-quality-gates](ci-infrastructure-quality-gates.md): Overall quality gate design

## Related

- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-004-error-message-investigation](ci-infrastructure-004-error-message-investigation.md)
- [ci-infrastructure-ai-integration](ci-infrastructure-ai-integration.md)
- [ci-infrastructure-claude-code-action-installer-race-condition](ci-infrastructure-claude-code-action-installer-race-condition.md)
