---
id: "54fc5859-c240-44e3-82c8-2a50c0565af3"
title: "Create Shared Helper Modules for Session Initialization"
assignee: ""
status: 0
createdAt: "1767766935987"
updatedAt: "1767767096948"
type: ticket
---

# Create Shared Helper Modules for Session Initialization

## Objective

Extract reusable functions from file:.claude/skills/session-init/scripts/New-SessionLog.ps1 into shared modules to support both the deprecated script and the new orchestrator during the transition period.

## Scope

**In Scope**:
- Create `file:.claude/skills/session-init/modules/GitHelpers.psm1` with git state functions
- Create `file:.claude/skills/session-init/modules/TemplateHelpers.psm1` with template population functions
- Extract and refactor functions from New-SessionLog.ps1:
  - `Get-GitInfo` → GitHelpers.psm1
  - `New-PopulatedSessionLog` → TemplateHelpers.psm1
  - `Get-DescriptiveKeywords` → TemplateHelpers.psm1
- Add Pester tests for shared modules
- Update New-SessionLog.ps1 to import and use shared modules (maintain functionality)

**Out of Scope**:
- Creating new phase scripts (handled in separate ticket)
- Deprecating New-SessionLog.ps1 (handled in separate ticket)
- Hook integration (handled in separate ticket)

## Spec References

- **Tech Plan**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/23a7f44b-69e7-4399-a164-c8eedf67b455 (Migration Strategy - Function Extraction)
- **Epic Brief**: spec:a8a106d4-2d31-4e19-ba45-021348587a7e/5312ae6b-3c86-4b02-ae5d-9ae3a14daf8a (Root Cause #3: Commit SHA Format)

## Acceptance Criteria

1. GitHelpers.psm1 created with functions:
   - `Get-GitInfo` - Returns hashtable with RepoRoot, Branch, Commit (short SHA), Status
   - Commit SHA uses `git rev-parse --short HEAD` (not `git log --oneline -1`)
   - Comprehensive error handling with specific exception types

2. TemplateHelpers.psm1 created with functions:
   - `New-PopulatedSessionLog` - Replaces placeholders in template
   - `Get-DescriptiveKeywords` - Extracts keywords from objective for filename
   - Validates placeholders before and after replacement

3. Pester tests added:
   - `.claude/skills/session-init/tests/GitHelpers.Tests.ps1`
   - `.claude/skills/session-init/tests/TemplateHelpers.Tests.ps1`
   - 80%+ code coverage for all functions

4. New-SessionLog.ps1 updated to import shared modules:
   - Existing functionality preserved
   - All existing tests still pass
   - No breaking changes

## Dependencies

None. This is a foundational refactoring that other tickets depend on.

## Implementation Notes

**Commit SHA Fix** (from analysis document):

```powershell
# Before (in New-SessionLog.ps1)
$commitOutput = git log --oneline -1 2>&1
$commit = $commitOutput.Trim()

# After (in GitHelpers.psm1)
$commitOutput = git rev-parse --short HEAD 2>&1
if ($LASTEXITCODE -ne 0) { 
    throw [System.InvalidOperationException]::new("Failed to get HEAD SHA: $commitOutput") 
}
$commit = $commitOutput.Trim()
```

**Module Structure**:
- Both modules follow existing patterns from file:scripts/lib/Install-Common.psm1
- Use `Export-ModuleMember -Function` to expose public functions
- Include comprehensive error handling with specific exception types
- Follow PowerShell best practices per file:.PSScriptAnalyzerSettings.psd1
