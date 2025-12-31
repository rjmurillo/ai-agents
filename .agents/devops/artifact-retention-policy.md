# Artifact Retention Policy

## Summary

This document defines the artifact retention policy for GitHub Actions workflows,
optimized for cost (COGS) while maintaining operational needs.

## Policy

| Category | Retention | Rationale |
|----------|-----------|-----------|
| **Ephemeral** | 1 day | Review artifacts, validation results. Only needed during PR review. |
| **Test Results** | 7 days | Pester results, coverage, linting. Needed for debugging recent failures. |
| **Metrics** | 30 days | Agent metrics, trend analysis. Balance between history and cost. |
| **Long-term** | 90 days | Critical audit artifacts only (none currently). |

## Current Configuration

| Workflow | Artifact | Before | After | Savings |
|----------|----------|--------|-------|---------|
| agent-metrics.yml | metrics-report | 90 days | 30 days | 67% reduction |
| pester-tests.yml | pester-test-results | 30 days | 7 days | 77% reduction |
| pester-tests.yml | code-coverage-results | 30 days | 7 days | 77% reduction |
| pester-tests.yml | psscriptanalyzer-results | 30 days | 7 days | 77% reduction |
| ai-pr-quality-gate.yml | review-* | 1 day | 1 day | No change |
| ai-session-protocol.yml | validation-* | 1 day | 1 day | No change |

## Cost Impact Analysis

**Before optimization:**
- 90-day artifacts: ~90x daily storage
- 30-day artifacts: ~30x daily storage

**After optimization:**
- 30-day artifacts: ~30x daily storage (reduced from 90)
- 7-day artifacts: ~7x daily storage (reduced from 30)

**Estimated storage reduction:** ~70% overall

## Guidelines for New Workflows

When adding new artifacts, follow these guidelines:

1. **Default to shortest reasonable retention**
   - Most artifacts are only useful during active development
   - Test results older than 7 days rarely investigated

2. **Use 1 day for:**
   - AI review results
   - Validation artifacts
   - Temporary debugging outputs

3. **Use 7 days for:**
   - Test results and coverage
   - Linting reports
   - Build logs

4. **Use 30 days for:**
   - Metrics and trends
   - Performance baselines
   - Historical comparisons

5. **Only use 90 days for:**
   - Audit requirements
   - Compliance evidence
   - Critical decision records

## Monitoring

Monitor artifact storage usage via:

```bash
# Check repository storage usage
gh api repos/rjmurillo/ai-agents -q '.size'

# Check Actions storage (requires admin access)
gh api /repos/rjmurillo/ai-agents/actions/cache/usage
```

## Related

- Issue: #278
- Parent: #272 (PR Maintenance Follow-up)
- ADR: None (configuration change, no architectural decision)
