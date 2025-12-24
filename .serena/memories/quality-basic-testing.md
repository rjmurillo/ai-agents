# Basic Execution Validation

**Statement**: After creating PowerShell script, verify it loads without syntax errors

**Context**: PowerShell script development

**Evidence**: PR #79 - Get-PRContext.ps1 had syntax error that would have been caught by basic load test

**Atomicity**: 88%

**Impact**: 8/10

## Validation Options

```powershell
# Option 1: Test module import (for .psm1 files)
Import-Module ./path/to/Module.psm1 -Force -ErrorAction Stop
Write-Host "✓ Module loaded successfully" -ForegroundColor Green

# Option 2: Test script execution (for .ps1 files)
. ./path/to/Script.ps1
Get-Command -Name MyFunction -ErrorAction Stop

# Option 3: Basic syntax check (fastest)
$null = [System.Management.Automation.PSParser]::Tokenize(
    (Get-Content ./path/to/Script.ps1 -Raw),
    [ref]$null
)
Write-Host "✓ Syntax valid" -ForegroundColor Green
```

## What It Catches

- Syntax errors (missing braces, quotes)
- Undefined variables in strict mode
- Invalid parameter definitions
- Malformed function signatures
- Module dependency issues

## What It Doesn't Catch

- Logic errors
- Runtime errors with specific inputs
- Performance issues
- Security vulnerabilities

## When to Use

- After creating a new PowerShell script
- After making significant changes
- Before committing to version control
