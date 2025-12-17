# PR Comment Map: PR #52

**Generated**: 2025-12-17 19:57:00
**PR**: feat: MCP config sync utility and pre-commit architecture documentation
**Branch**: feat/add-mcp-config → main
**Total Comments**: 13 (12 review + 1 issue)
**Reviewers**: @Copilot, @coderabbitai[bot], @cursor[bot], @rjmurillo

## Comment Index

| ID | Author | Type | Path/Line | Status | Priority | Plan Ref |
|----|--------|------|-----------|--------|----------|----------|
| 2628172986 | @Copilot | review | scripts/Sync-McpConfig.ps1#174 | ✅ Resolved | - | Fixed in 4815d56 |
| 2628173019 | @Copilot | review | scripts/tests/Sync-McpConfig.Tests.ps1#269 | ✅ Resolved | - | Fixed in 4815d56 |
| 2628175065 | @cursor[bot] | review | .githooks/pre-commit#311 | ✅ Resolved | - | Fixed in 4815d56 |
| 2628221771 | @coderabbitai[bot] | review | scripts/Sync-McpConfig.ps1#174 | ✅ Resolved | - | Fixed in 4815d56 |
| 2628287285 | @rjmurillo | review | .githooks/pre-commit#311 | Reply | - | - |
| 2628287444 | @rjmurillo | review | scripts/Sync-McpConfig.ps1#174 | Reply | - | - |
| 2628287551 | @rjmurillo | review | scripts/tests/Sync-McpConfig.Tests.ps1#269 | Reply | - | - |
| 2628287657 | @rjmurillo | review | scripts/Sync-McpConfig.ps1#174 | Reply | - | - |
| 2628289067 | @coderabbitai[bot] | review | scripts/Sync-McpConfig.ps1#174 | Confirmation | - | - |
| 2628305876 | @cursor[bot] | review | .githooks/pre-commit#311 | ✅ Resolved | - | Fixed in b4c9353 |
| 2628408490 | @rjmurillo | review | .githooks/pre-commit#311 | Reply | - | - |
| 2628441553 | @cursor[bot] | review | .githooks/pre-commit#303 | 👀 Acknowledged | TBD | Pending analysis |
| 3666680250 | @coderabbitai[bot] | issue | - | Info | - | Bot coordination notice |

## Comments Detail

### Comment 2628441553 (@cursor[bot]) - **ACTIVE**

**Type**: Review
**Path**: .githooks/pre-commit
**Line**: 303
**Created**: 2025-12-17T19:54:33Z
**Status**: 👀 Acknowledged
**Severity**: Medium

**Context**:
```diff
            if [ $SYNC_EXIT -eq 0 ]; then
                # Script succeeded - check if files were actually synced
                if echo "$SYNC_OUTPUT" | grep -q "True"; then
```

**Comment**:
> ### Bug: Grep pattern matches path substring, causing false positives
>
> The `grep -q "True"` check searches the entire script output for the substring "True". The PowerShell script includes file paths in its `Write-Host` output (e.g., "MCP config already in sync: $DestinationPath"). If the repository path contains "True" (like `/Users/TrueUser/repo/`), the grep matches even when the script returns `$false` (files already in sync). This causes `FILES_FIXED=1` to be set incorrectly and displays "Synced: mcp.json" when nothing was synced. Using `grep -q '^True$'` would match only the exact return value line.

**Analysis**: Pending - requires Quick Fix analysis
**Priority**: TBD - High (cursor[bot] has 100% actionability rate)
**Plan**: `.agents/pr-comments/PR-52/2628441553-plan.md`
**Resolution**: Pending

---

## Previously Resolved Comments (Summary)

### Comment 2628172986 (@Copilot) - ✅ Resolved in 4815d56
- **Issue**: Missing explicit return value when WhatIf is used with PassThru
- **Resolution**: Added explicit `return $false` in else block

### Comment 2628173019 (@Copilot) - ✅ Resolved in 4815d56
- **Issue**: Missing test coverage for WhatIf + PassThru combination
- **Resolution**: Added test case at line 218

### Comment 2628175065 (@cursor[bot]) - ✅ Resolved in 4815d56
- **Issue**: Newly created mcp.json not staged by pre-commit (git diff doesn't detect untracked files)
- **Resolution**: Replaced `git diff --quiet` with unconditional `git add`

### Comment 2628221771 (@coderabbitai[bot]) - ✅ Resolved in 4815d56
- **Issue**: PassThru doesn't return a value when WhatIf is used
- **Resolution**: Same fix as 2628172986 - added explicit return value
- **Confirmed**: @coderabbitai[bot] confirmed in comment 2628289067

### Comment 2628305876 (@cursor[bot]) - ✅ Resolved in b4c9353
- **Issue**: Incorrect status message and flag when files already synced
- **Resolution**: Hook now uses `-PassThru` to capture sync status
