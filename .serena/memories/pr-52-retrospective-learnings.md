# PR #52 Retrospective Learnings

## Summary

Three issues were identified by automated review bots after PR #52 was submitted and fixed in commit 4815d56. This memory captures the key learnings for future reference.

## Issues Found

### Issue 1: CRITICAL - Untracked File Detection (cursor[bot])

- **File:** .githooks/pre-commit:300
- **Problem:** Used `git diff --quiet` which doesn't detect untracked files
- **Fix:** Replaced with unconditional `git add` (idempotent)
- **Learning:** `git add` is idempotent - prefer over conditional staging in hooks

### Issue 2: WhatIf+PassThru Return Value (Copilot)

- **File:** scripts/Sync-McpConfig.ps1:171
- **Problem:** When WhatIf prevents write, PassThru returns nothing
- **Fix:** Added `else { if ($PassThru) { return $false } }`
- **Learning:** ShouldProcess + PassThru requires else-branch handling

### Issue 3: Missing Test Coverage (Copilot)

- **File:** scripts/tests/Sync-McpConfig.Tests.ps1:218
- **Problem:** No test for WhatIf+PassThru combination
- **Fix:** Added test case
- **Learning:** Test parameter combinations: n + C(n,2) tests minimum

## Root Causes

1. **Edge Case Blindness:** Focused on happy path, missing edge cases
2. **Test Organization Gap:** Tests by feature, not by parameter combinations
3. **Tool Knowledge Gap:** Didn't know `git diff --quiet` limitation
4. **Test-After Pattern:** Tests written after implementation

## Prevention Strategies

### Git Hooks

```bash
# ✅ Prefer (idempotent)
if [ -f "$FILE" ]; then
    git add -- "$FILE"
fi

# ❌ Avoid (misses untracked)
if ! git diff --quiet -- "$FILE"; then
    git add -- "$FILE"
fi
```

### PowerShell Testing

- Test parameter combinations: n individual + C(n,2) pairs
- For 2 params (WhatIf, PassThru): 2 + 1 = 3 tests minimum
- Always include "Parameter Combinations" context

### PowerShell ShouldProcess Pattern

```powershell
if ($PSCmdlet.ShouldProcess(...)) {
    if ($PassThru) { return $true }
} else {
    if ($PassThru) { return $false }  # Required!
}
```

### Integration Testing

- Always test first-time setup (config files don't exist)
- Test idempotent behavior (running twice)

## Reviewer Signal Quality

| Reviewer | Signal | Validated |
|----------|--------|-----------|
| cursor[bot] | 100% | 4/4 bugs found |
| Copilot | ~60% | 2/2 valid in PR #52 |
| CodeRabbit | Low | Duplicate + summary |

## Success Metrics

1. Edge cases found during development (not review): >80%
2. Parameter combination coverage: 100%
3. First-time setup testing: 100%
4. Test-first adoption for cmdlets: >70%

## Related Files

- `.agents/retrospective/PR-52-review-issues.md` - Full analysis
- `.agents/pr-comments/PR-52/comments.md` - Comment map
- `.agents/pr-comments/PR-52/summary.md` - Session summary
