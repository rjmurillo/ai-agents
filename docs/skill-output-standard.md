# Skill Output Format Standard

> **ADR**: [ADR-044](../.agents/architecture/ADR-044-skill-output-format-standardization.md)
> **Status**: Accepted
> **Applies to**: All skill scripts under `.claude/skills/`

## Overview

All skill scripts MUST produce output in a consistent envelope format. This enables agents to reliably parse results while preserving human-readable output for interactive use.

## Quick Start

```powershell
# 1. Import the module
Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "SkillOutput.psm1") -Force

# 2. Add -OutputFormat parameter to your param block
param(
    # ... your existing params ...
    [ValidateSet('JSON', 'Human', 'Auto')]
    [string]$OutputFormat = 'Auto'
)

# 3. Use Write-SkillOutput for success
Write-SkillOutput -Data $result -OutputFormat $OutputFormat `
    -HumanSummary "PR #42: All checks passing" -Status PASS `
    -ScriptName 'My-Script.ps1'

# 4. Use Write-SkillError for failures
Write-SkillError -Message "PR #999 not found" -ExitCode 2 -ErrorType NotFound `
    -OutputFormat $OutputFormat -ScriptName 'My-Script.ps1'
exit 2
```

## JSON Envelope Schema

### Success Response

```json
{
  "Success": true,
  "Data": {
    "Number": 42,
    "Title": "Add feature X",
    "AllPassing": true
  },
  "Error": null,
  "Metadata": {
    "Script": "Get-PRChecks.ps1",
    "Version": "1.0.0",
    "Timestamp": "2026-03-08T12:00:00.0000000Z"
  }
}
```

### Error Response

```json
{
  "Success": false,
  "Data": null,
  "Error": {
    "Message": "PR #999 not found in owner/repo",
    "Code": 2,
    "Type": "NotFound"
  },
  "Metadata": {
    "Script": "Get-PRChecks.ps1",
    "Version": "1.0.0",
    "Timestamp": "2026-03-08T12:00:00.0000000Z"
  }
}
```

## OutputFormat Parameter

| Value | Behavior |
|-------|----------|
| `JSON` | Emits only valid JSON to stdout. No `Write-Host` output. |
| `Human` | Emits color-coded `[STATUS] summary` via `Write-Host`. |
| `Auto` (default) | Resolves to `JSON` in CI/redirected contexts, `Human` when interactive. |

Auto-detection logic:

1. If `$env:CI`, `$env:GITHUB_ACTIONS`, or `$env:TF_BUILD` is set → `JSON`
2. If `[Console]::IsOutputRedirected` → `JSON`
3. Otherwise → `Human`

## Error Types

Aligned with [ADR-035 exit codes](../.agents/architecture/ADR-035-exit-code-standardization.md):

| Type | Exit Code | Description |
|------|-----------|-------------|
| `InvalidParams` | 1 | Invalid parameters |
| `NotFound` | 2 | Resource not found |
| `ApiError` | 3 | GitHub API error |
| `AuthError` | 4 | Not authenticated |
| `Timeout` | 7 | Timeout reached |
| `General` | varies | Other errors |

## Human Status Indicators

| Status | Color | Use When |
|--------|-------|----------|
| `PASS` | Green | Operation succeeded |
| `FAIL` | Red | Operation failed |
| `WARNING` | Yellow | Partial success or timeout |
| `INFO` | Cyan | Informational result |

## Validation

Use the validator to check output compliance:

```bash
pwsh .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest 1 -OutputFormat JSON \
  | pwsh scripts/Validate-SkillOutput.ps1
```

The JSON schema is at `.agents/schemas/skill-output.schema.json`.

## Migration Checklist

When migrating an existing skill to the standard format:

- [ ] Add `-OutputFormat` parameter with `[ValidateSet('JSON', 'Human', 'Auto')]`
- [ ] Import `SkillOutput.psm1`
- [ ] Replace `Write-Output ($obj | ConvertTo-Json ...)` with `Write-SkillOutput`
- [ ] Replace inline error JSON with `Write-SkillError`
- [ ] Remove `Write-Host` calls that duplicate JSON output
- [ ] Verify JSON mode produces only valid JSON (no mixed content)
- [ ] Update tests to validate envelope structure

## Migrated Skills

| Script | Status |
|--------|--------|
| `Get-PRChecks.ps1` | ✅ Migrated |
| `Get-PRContext.ps1` | ✅ Migrated |
| `Get-PRReviewComments.ps1` | ✅ Migrated |

## Available Helpers

From `SkillOutput.psm1`:

| Function | Purpose |
|----------|---------|
| `Write-SkillOutput` | Emit standardized success envelope |
| `Write-SkillError` | Emit standardized error envelope |
| `Get-OutputFormat` | Resolve Auto → JSON or Human |
