# Workflow False Positive: Verdict Parsing Context Contamination

**Date**: 2025-12-28
**Issue**: PR #465 blocked by CRITICAL_FAIL from analyst agent
**Root Cause**: Verdict parsing regex matches context strings, not actual verdicts
**Classification**: Workflow infrastructure bug (not code quality issue)

## Pattern Identification

False positive verdict when:
1. PR links to or includes issue context in agent input
2. Issue description contains verdict keywords: "CRITICAL_FAIL", "REJECTED", "PASS"
3. Analyst/security/qa agent outputs include this context
4. `Get-Verdict()` function in AIReviewCommon.psm1 matches keyword without context filtering

## Evidence

**File**: `.github/scripts/AIReviewCommon.psm1` lines 162-169

```powershell
# Fall back to keyword detection
if ($Output -match 'CRITICAL_FAIL|critical failure|severe issue') {
    return 'CRITICAL_FAIL'
}
```

**Problem**: Regex has no context awareness. Matches "CRITICAL_FAIL" anywhere in output, including:
- Issue problem statements ("❌ QA: CRITICAL_FAIL - New validation logic has zero test coverage")
- Code examples/anti-patterns
- Quoted context from linked issues

**Should be**: Only match `VERDICT: CRITICAL_FAIL` pattern (explicit verdict declarations)

## Mitigation

1. **Immediate**: Require agents to output explicit `VERDICT: [KEYWORD]` pattern
2. **Short-term**: Update `Get-Verdict()` to skip non-verdict context sections
3. **Long-term**: Add strict mode enforcement in workflow

## Cases Affected

Any PR that:
- Links to or quotes issues with "CRITICAL_FAIL" in problem statement
- Has agent context that includes historical issue descriptions
- Analyst/QA agents receive full issue context in their input prompts

## Test Case

Create unit test:
```powershell
$output = @"
Issue Context:
❌ QA: CRITICAL_FAIL - New validation logic has zero test coverage

## Verdict
VERDICT: PASS - PR fixes the issue above with comprehensive tests
"@

$verdict = Get-Verdict -Output $output
# Should return: 'PASS'
# Currently returns: 'CRITICAL_FAIL' (false positive)
```

## Related Verdicts

- COMPLETENESS_VERDICT: PASS (indicates requirements satisfied)
- TRACE_VERDICT: CRITICAL_FAIL (contaminated by context)

When these conflict, completeness pass + context-tainted failure = **false positive** (approve PR).

## Implementation Checklist

- [ ] Verify explicit VERDICT: pattern in all agent prompts
- [ ] Add StrictMode parameter to Get-Verdict()
- [ ] Skip code fences and quoted sections in keyword fallback
- [ ] Document verdict parsing rules in AIReviewCommon.psm1
- [ ] Add unit tests with context contamination cases
- [ ] Add integration test for PR with linked issues
