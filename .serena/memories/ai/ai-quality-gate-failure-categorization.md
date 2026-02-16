# AI Quality Gate Failure Categorization Patterns

**Date**: 2025-12-23
**Issue**: #329 - Categorize failures as INFRASTRUCTURE vs CODE_QUALITY
**Analysis**: `.agents/analysis/002-ai-quality-gate-failure-patterns.md`

## Purpose

Prevent infrastructure failures from cascading to CRITICAL_FAIL and blocking PRs. Enable targeted retry logic (Issue #328) and accurate PR status reporting.

## Infrastructure Failure Patterns

These failures indicate temporary/transient issues (should NOT block PR):

### High Confidence Patterns

```powershell
$infrastructurePatterns = @(
    'timed?\s*out',           # Timeout patterns
    'timeout',
    'rate\s*limit',           # Rate limiting
    '429',                    # HTTP 429 Too Many Requests
    'network\s*error',        # Network issues
    '502\s*Bad\s*Gateway',
    '503\s*Service\s*Unavailable',
    'connection\s*(refused|reset|timeout)',
    'Copilot\s*CLI\s*failed.*with\s*no\s*output',  # CLI access issues
    'missing\s*Copilot\s*access',
    'insufficient\s*scopes'
)
```

### Exit Code Signals

- Exit code 124 = timeout (ALWAYS infrastructure)
- Exit code != 0 with no output = likely infrastructure (access/network)

## Code Quality Failure Patterns

These failures indicate actual code problems (SHOULD block PR):

### Explicit Verdict Keywords

```powershell
$codeQualityKeywords = @(
    'Security\s*vulnerability',
    'SQL\s*injection',
    'XSS',
    'Missing\s*tests',
    'No\s*test\s*coverage',
    'Code\s*smell',
    'Anti-pattern'
)
```

### Verdict Parsing

If output contains `VERDICT: (CRITICAL_FAIL|REJECTED|FAIL)` with code quality keywords, categorize as CODE_QUALITY.

## Decision Tree

```
Is exit code 124?
  YES → INFRASTRUCTURE (timeout)
  NO  → Continue

Does message match infrastructure pattern?
  YES → INFRASTRUCTURE
  NO  → Continue

Does stderr match infrastructure pattern?
  YES → INFRASTRUCTURE
  NO  → Continue

Is verdict CRITICAL_FAIL/REJECTED/FAIL with code quality keywords?
  YES → CODE_QUALITY
  NO  → Continue

Is output empty?
  YES → INFRASTRUCTURE (likely access/network)
  NO  → CODE_QUALITY (default)
```

## Implementation Recommendation

**Location**: `.github/scripts/AIReviewCommon.psm1`

Add function:
```powershell
function Get-FailureCategory {
    <#
    .SYNOPSIS
        Categorize failure as INFRASTRUCTURE or CODE_QUALITY
    
    .PARAMETER Message
        Verdict message from AI output
    
    .PARAMETER Stderr
        Stderr from Copilot CLI
    
    .PARAMETER ExitCode
        Exit code from Copilot CLI
    
    .PARAMETER Verdict
        Parsed verdict (PASS, WARN, CRITICAL_FAIL, etc.)
    
    .OUTPUTS
        String - "INFRASTRUCTURE" or "CODE_QUALITY"
    #>
}
```

**Usage in Workflow**:
1. Call `Get-FailureCategory` for each agent's results in aggregate step
2. Store category alongside verdict in artifacts
3. Update final verdict logic to ignore infrastructure failures
4. Add category column to PR comment table

## Edge Cases

1. **Concurrent failures**: If both infrastructure and code quality failures occur, code quality wins (PR should block)
2. **Partial output with timeout**: Categorize as infrastructure
3. **Empty verdict with warnings**: Check content for code quality keywords
4. **Retry exhaustion**: Maintain infrastructure category for metrics even after retries exhausted

## Metrics to Track

- Infrastructure failure rate (by agent)
- Code quality failure rate (by agent)
- False positive rate (infrastructure causing blocks)
- Retry success rate (from #328)

## Implementation Status

**Completed**: 2025-12-24 (Session 01, Commit feea262)

**Changes**:
1. Added `Get-FailureCategory` function to `.github/scripts/AIReviewCommon.psm1`
2. Updated `.github/workflows/ai-pr-quality-gate.yml` to compute categories
3. Infrastructure-only failures now downgrade to WARN (PR not blocked)
4. PR comments show Category column in Review Summary table

**Key Behavior**:
- Infrastructure-only failures → WARN (PR not blocked)
- Any CODE_QUALITY failure → CRITICAL_FAIL (PR blocked)
- Mixed failures → CODE_QUALITY wins (PR blocked)

**Session Log**: `.agents/sessions/2025-12-24-session-01-failure-categorization.md`

## Related

- Issue #328: Retry logic for infrastructure failures (COMPLETED)
- Issue #329: Failure categorization (COMPLETED - this implementation)
- Memory [ai-quality-gate-efficiency-analysis](ai-quality-gate-efficiency-analysis.md): Cost analysis
- Analysis document: `.agents/analysis/002-ai-quality-gate-failure-patterns.md`
