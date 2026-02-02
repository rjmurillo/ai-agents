# Pre-PR Validation Checklist

**Date**: 2026-01-01
**Source**: PR #730 CI failures root cause analysis
**Atomicity Score**: 90%

## Statement

Before creating or updating a PR, complete ALL validation steps locally to prevent CI failures.

## Checklist

### 1. Memory/Skill File Naming (ADR-017)

```powershell
# Check for 'skill-' prefix violations in changed memory files
git diff --cached --name-only | Where-Object { $_ -match '\.serena/memories/skill-.*\.md$' }
```

**Requirement**: Files in `.serena/memories/` MUST NOT start with `skill-` prefix. Use `{domain}-{description}` format.

### 2. Pester Tests

```powershell
# Run tests for changed PowerShell files
Invoke-Pester -Path 'tests/*.Tests.ps1' -PassThru
```

**Requirement**: All tests MUST pass before PR submission.

### 3. Script Syntax Validation

```powershell
# Validate all changed .ps1 files have valid syntax
Get-ChildItem -Recurse -Filter "*.ps1" | ForEach-Object {
    try {
        $null = [ScriptBlock]::Create((Get-Content $_.FullName -Raw))
        Write-Host "Valid: $($_.Name)" -ForegroundColor Green
    } catch {
        Write-Host "Invalid: $($_.Name)" -ForegroundColor Red
        Write-Host $_.Exception.Message
    }
}
```

**Requirement**: All PowerShell scripts MUST parse without errors.

### 4. Style Guide Compliance

```powershell
# Check ErrorActionPreference setting
Select-String -Pattern 'ErrorActionPreference.*=.*SilentlyContinue' -Path "*.ps1" -Recurse
```

**Requirement**: Scripts MUST use `$ErrorActionPreference = 'Stop'` (not 'SilentlyContinue').

### 5. Markdown Linting

```bash
npx markdownlint-cli2 --fix "**/*.md"
```

**Warning**: Do NOT run linting on .ps1 files - it corrupts PowerShell comment terminators (`#>` becomes `# >`).

## Root Cause Analysis (PR #730)

| Failure | Root Cause | Prevention |
|---------|------------|------------|
| Memory validation fail | `skill-usage-mandatory.md` used `skill-` prefix | Check ADR-017 naming before commit |
| Pester test fail | PSGallery not in firewall allowlist | Pre-existing infra issue |
| Reviewer feedback | `$ErrorActionPreference = 'SilentlyContinue'` | Follow style guide |
| Script parse error | Linting corrupted `#>` to `# >` | Don't lint .ps1 files |

## Procedure Gap Identified

PR was submitted without running local tests first. The CI failures could have been caught locally.

## Related

- ADR-017: Skill File Atomicity
- ADR-005: PowerShell-Only Scripting
- .gemini/styleguide.md: ErrorActionPreference requirements

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
