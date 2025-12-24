# Analysis: AI Quality Gate Failure Patterns

## 1. Objective and Scope

**Objective**: Identify and categorize failure patterns in AI Quality Gate to distinguish infrastructure failures from code quality failures.

**Scope**:
- Analyze `.github/workflows/ai-pr-quality-gate.yml` workflow
- Identify `.github/actions/ai-review` composite action failure modes
- Examine `AIReviewCommon.psm1` verdict handling
- Document patterns for Issue #329 implementation
- **EXCLUDED**: Implementation of categorization logic (deferred to implementer)

## 2. Context

### Current State

The AI Quality Gate workflow runs 6 agents in parallel (security, qa, analyst, architect, devops, roadmap). Each agent uses the `ai-review` composite action which invokes GitHub Copilot CLI.

**Problem**: All failures are treated equally, causing:
- Infrastructure failures (timeouts, rate limits) cascade to CRITICAL_FAIL
- False negatives on good PRs due to transient infrastructure issues
- Wasted premium API requests on re-runs (50-80% waste per memory)
- User confusion about what needs fixing

**Background**: Issue #328 adds retry logic for infrastructure failures. Issue #329 (this research) adds categorization to prevent infrastructure failures from blocking PRs.

## 3. Approach

**Methodology**:
1. Read workflow and action source code
2. Trace failure paths from CLI invocation to verdict aggregation
3. Extract error message patterns from code comments and diagnostic logic
4. Review memory `ai-quality-gate-efficiency-analysis` for real-world examples
5. Review Issues #328 and #329 for expected patterns

**Tools Used**:
- Read tool for source code analysis
- GitHub CLI for issue context
- Serena memory for historical findings

**Limitations**:
- Cannot access historical GitHub Actions logs (requires GitHub API pagination)
- Patterns inferred from code and documentation, not all empirically verified
- Some edge cases may exist in production not covered in diagnostic code

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Copilot CLI timeout after N minutes | `.github/actions/ai-review/action.yml:522-527` | High |
| Non-zero exit code with no output | `.github/actions/ai-review/action.yml:538-568` | High |
| Rate limiting patterns | Issue #328, #329 examples | Medium |
| Network errors (502, 503) | Issue #329 examples | Medium |
| CRITICAL_FAIL verdict on CLI failure | `.github/actions/ai-review/action.yml:524, 563` | High |
| Verdict parsing logic | `.github/actions/ai-review/action.yml:598-650` | High |
| Aggregation uses Merge-Verdicts | `.github/workflows/ai-pr-quality-gate.yml:243` | High |
| Final verdict blocks on CRITICAL_FAIL/REJECTED/FAIL | `.github/workflows/ai-pr-quality-gate.yml:396-399` | High |

### Facts (Verified)

**Failure Injection Points**:
1. **Copilot CLI Invocation** (`.github/actions/ai-review/action.yml:459-596`)
   - Exit code 124 = timeout (line 522)
   - Exit code != 0 = CLI failure (line 528)
   - No stdout + no stderr = likely missing Copilot access (line 538-563)

2. **Verdict Parsing** (`.github/actions/ai-review/action.yml:598-650`)
   - Cannot parse verdict = CRITICAL_FAIL (line 619)
   - Verdict determines exit code (line 635-638)

3. **Verdict Aggregation** (`.github/workflows/ai-pr-quality-gate.yml:222-253`)
   - Uses `Merge-Verdicts` from `AIReviewCommon.psm1`
   - Priority: CRITICAL_FAIL/REJECTED/FAIL > WARN > PASS (module lines 303-315)

4. **Final Gate** (`.github/workflows/ai-pr-quality-gate.yml:391-401`)
   - Exits 1 if verdict in ['CRITICAL_FAIL', 'REJECTED', 'FAIL']
   - Blocks PR merge

**Error Message Patterns from Source Code**:

Infrastructure patterns identified in `.github/actions/ai-review/action.yml`:
- Line 524: `"AI review timed out after ${TIMEOUT_MINUTES} minutes"`
- Line 563: `"Copilot CLI failed (exit code $EXIT_CODE) with no output - likely missing Copilot access"`
- Line 566: `"Copilot CLI failed (exit code $EXIT_CODE)"`
- Line 544-560: Diagnostic messages about missing Copilot access, invalid PAT, network issues, rate limiting

**Diagnostic Patterns** (`.github/actions/ai-review/action.yml:182-343`):
- Line 286: `"test_prompt: TIMEOUT"` from diagnostic run
- Line 290: `"test_prompt: FAILED"` from diagnostic run
- Line 310: `"NO_OUTPUT - likely missing Copilot access"`

### Hypotheses (Unverified)

1. Rate limit errors from GitHub API may manifest as stderr output with specific text patterns
2. Network errors (502, 503) would appear in stderr from `curl` or Copilot CLI
3. Transient failures may have different patterns than persistent configuration issues

## 5. Results

### Infrastructure Failure Patterns

Failures that indicate temporary infrastructure issues (should NOT block PR):

| Pattern Type | Regex/Match Pattern | Confidence |
|--------------|---------------------|------------|
| **Timeout** | `timed out after \d+ minutes` | High |
| **Timeout** | `timeout` (case-insensitive) | Medium |
| **Rate Limit** | `rate limit` (case-insensitive) | High |
| **Rate Limit** | `429` (HTTP status) | High |
| **Network** | `network error` (case-insensitive) | High |
| **Network** | `502 Bad Gateway` | High |
| **Network** | `503 Service Unavailable` | High |
| **Network** | `connection (refused\|reset\|timeout)` | Medium |
| **CLI Failure** | `Copilot CLI failed.*with no output` | High |
| **CLI Failure** | Exit code 124 (timeout) | High |
| **Auth/Access** | `missing Copilot access` | High |
| **Auth/Access** | `insufficient scopes` | Medium |

### Code Quality Failure Patterns

Failures that indicate actual code problems (SHOULD block PR):

| Pattern Type | Regex/Match Pattern | Confidence |
|--------------|---------------------|------------|
| **Explicit Verdict** | `VERDICT:\s*(CRITICAL_FAIL\|REJECTED\|FAIL)` | High |
| **Security** | `Security vulnerability` | High |
| **Security** | `SQL injection` | High |
| **Security** | `XSS` | High |
| **Testing** | `Missing tests` | High |
| **Testing** | `No test coverage` | High |
| **Quality** | `Code smell` | Medium |
| **Design** | `Anti-pattern` | Medium |

### Ambiguous Patterns

Patterns that need context to categorize:

| Pattern | Requires Investigation |
|---------|------------------------|
| Generic error with stderr but no output | Examine stderr content |
| Exit code != 0 with parseable output | Check if output contains verdict |
| Empty output | Distinguish timeout vs access issue |

## 6. Discussion

### Current Failure Flow

```
Copilot CLI Invocation
  └─> Exit Code
      ├─> 124 (timeout) → CRITICAL_FAIL (infrastructure)
      ├─> 0 (success) → Parse verdict
      └─> Other → Check output
          ├─> No output → CRITICAL_FAIL (likely infrastructure)
          └─> Has output → Parse verdict or CRITICAL_FAIL
```

### Categorization Decision Tree

```
Is exit code 124?
  YES → INFRASTRUCTURE (timeout)
  NO  → Continue

Does output match infrastructure pattern?
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

### Key Insights

1. **Exit code alone is insufficient**: Exit code 1 can be infrastructure OR code quality
2. **Message content is critical**: Must inspect verdict message and stderr
3. **"No output" is infrastructure**: CLI producing no output almost always indicates access/network issues
4. **Timeout is always infrastructure**: Exit code 124 is unambiguous
5. **Verdict keywords help**: Security/testing vocabulary in verdict indicates code quality

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Implement pattern matching in PowerShell module | Centralized logic, reusable across workflows | Low |
| P0 | Add `Get-FailureCategory` function to `AIReviewCommon.psm1` | Follows existing module patterns | Low |
| P1 | Update verdict aggregation to separate categories | Prevents infrastructure failures from cascading | Medium |
| P1 | Add category column to PR comment table | User visibility into failure type | Low |
| P2 | Log categorization decisions for observability | Helps refine patterns over time | Low |
| P2 | Collect metrics on category distribution | Informs future optimizations | Medium |

### Recommended Implementation Location

**Primary**: `.github/scripts/AIReviewCommon.psm1`

Add new function:
```powershell
function Get-FailureCategory {
    param(
        [string]$Message,
        [string]$Stderr,
        [int]$ExitCode,
        [string]$Verdict
    )
    # Returns "INFRASTRUCTURE" or "CODE_QUALITY"
}
```

**Secondary**: `.github/workflows/ai-pr-quality-gate.yml`

Update aggregation step to:
1. Call `Get-FailureCategory` for each agent's results
2. Store category alongside verdict
3. Pass category to final verdict logic
4. Include category in PR comment

**Tertiary**: `.github/actions/ai-review/action.yml`

Consider adding category as output:
```yaml
outputs:
  category:
    description: 'Failure category (INFRASTRUCTURE or CODE_QUALITY)'
    value: ${{ steps.categorize.outputs.category }}
```

## 8. Conclusion

**Verdict**: Proceed with implementation

**Confidence**: High

**Rationale**: Clear patterns identified from source code analysis. Infrastructure patterns are distinct enough to categorize with high confidence. Categorization logic is straightforward and low-risk.

### User Impact

**What changes for you**: PR comments will show which failures are infrastructure issues vs code problems. Infrastructure failures won't block merge once retry logic (#328) is implemented.

**Effort required**: No user action needed. Workflow changes are transparent.

**Risk if ignored**: Continued false CRITICAL_FAIL verdicts on good PRs, wasted API requests, user confusion about what to fix.

## 9. Appendices

### Sources Consulted

- `.github/workflows/ai-pr-quality-gate.yml` - Main workflow orchestration
- `.github/actions/ai-review/action.yml` - Copilot CLI invocation and error handling
- `.github/scripts/AIReviewCommon.psm1` - Verdict parsing and aggregation
- Issue #328: Retry logic specification
- Issue #329: Categorization specification
- Memory `ai-quality-gate-efficiency-analysis`: Real-world failure analysis from PR #156

### Data Transparency

**Found**:
- Timeout pattern (exit code 124)
- No output pattern with detailed diagnostics
- Verdict parsing fallback logic
- Aggregation priority rules
- Final gate blocking logic

**Not Found**:
- Historical log examples of rate limit errors (requires GitHub API access)
- Empirical verification of 502/503 patterns (not observed in recent runs)
- stderr patterns for network errors (not captured in source code)

### Proposed Regex Patterns

Infrastructure detection (PowerShell):
```powershell
$infrastructurePatterns = @(
    'timed?\s*out',
    'timeout',
    'rate\s*limit',
    '429',
    'network\s*error',
    '502\s*Bad\s*Gateway',
    '503\s*Service\s*Unavailable',
    'connection\s*(refused|reset|timeout)',
    'Copilot\s*CLI\s*failed.*with\s*no\s*output',
    'missing\s*Copilot\s*access',
    'insufficient\s*scopes'
)

# Match any pattern (case-insensitive)
$category = if ($Message -match ($infrastructurePatterns -join '|')) {
    'INFRASTRUCTURE'
} else {
    'CODE_QUALITY'
}
```

Code quality detection (optional, for explicit matching):
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

### Edge Cases to Consider

1. **Concurrent infrastructure and code failures**: If 2 agents fail, one infrastructure and one code quality, the PR should still block (code quality wins)
2. **Partial output with timeout**: If CLI times out mid-response, may have partial verdict - categorize as infrastructure
3. **Retry exhaustion**: If retry logic (#328) exhausts attempts, final verdict should still reflect infrastructure category for metrics
4. **Empty verdict with warnings in output**: If output has no VERDICT: line but has security warnings, treat as code quality failure
