# Testing Skills

**Extracted**: 2025-12-20
**Source**: PR #79 retrospective analysis

## Skill-Testing-003: Basic Execution Validation

**Statement**: After creating PowerShell script, verify it loads without syntax errors by running `Import-Module` or displaying help.

**Context**: PowerShell script development

**Evidence**: PR #79 - Get-PRContext.ps1 had syntax error that would have been caught by basic load test

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10 - Catches runtime errors before commit

**Created**: 2025-12-20

**Pattern**:

```powershell
# After creating or modifying a PowerShell script

# Option 1: Test module import (for .psm1 files)
Import-Module ./path/to/Module.psm1 -Force -ErrorAction Stop
Write-Host "✓ Module loaded successfully" -ForegroundColor Green

# Option 2: Test script execution (for .ps1 files with functions)
. ./path/to/Script.ps1
Get-Command -Name MyFunction -ErrorAction Stop
Write-Host "✓ Script loaded successfully" -ForegroundColor Green

# Option 3: Display help (for scripts with comment-based help)
Get-Help ./path/to/Script.ps1 -ErrorAction Stop
Write-Host "✓ Help displayed successfully" -ForegroundColor Green

# Option 4: Basic syntax check (fastest)
$null = [System.Management.Automation.PSParser]::Tokenize(
    (Get-Content ./path/to/Script.ps1 -Raw), 
    [ref]$null
)
Write-Host "✓ Syntax valid" -ForegroundColor Green
```

**When to Use**:

- After creating a new PowerShell script
- After making significant changes to existing script
- Before committing changes to version control
- As part of pre-commit hook validation

**What It Catches**:

- Syntax errors (missing braces, quotes, etc.)
- Undefined variables in strict mode
- Invalid parameter definitions
- Malformed function signatures
- Module dependency issues

**What It Doesn't Catch**:

- Logic errors
- Runtime errors with specific inputs
- Performance issues
- Security vulnerabilities

**Best Practice Workflow**:

1. Write/modify PowerShell script
2. Run basic execution validation (this skill)
3. Run static analysis (PSScriptAnalyzer - see Skill-CI-001)
4. Write Pester tests (see Skill-Test-Pester-005)
5. Commit to version control

**Related Skills**:

- Skill-CI-001: Pre-commit syntax validation (automated check)
- Skill-Test-Pester-005: Test-first development
- Skill-Test-Pester-001: Pester 5.x discovery phase pattern

**Validation**: 1 (PR #79)

---

## Related Files

- Pre-commit hooks: `.githooks/pre-commit`
- Test files: `scripts/tests/*.Tests.ps1`
- Source: PR #79 retrospective
