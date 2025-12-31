---
name: PowerShell Patterns
applyTo: "**/*.ps1,**/*.psm1"
priority: 8
version: 1.0.0
status: active
---

# PowerShell Coding Patterns

**Status**: Active
**Applies to**: `**/*.ps1`, `**/*.psm1`

This steering file provides PowerShell coding standards and patterns for the implementer agent when working with PowerShell scripts.

## String Interpolation Safety

### Problem: Scope Qualifier Ambiguity

PowerShell interprets `$variable:` as a scope qualifier (like `$global:var`, `$script:var`). When a colon follows a variable in a double-quoted string, PowerShell expects a scope name, causing syntax errors.

### Examples

```powershell
# RISKY - Can cause syntax error
"Failed to get PR #$PullRequest: $errorDetails"

# SAFE - Subexpression syntax
"Failed to get PR #$($PullRequest): $errorDetails"

# SAFE - Braced variable syntax
"Failed to get PR #${PullRequest}: $errorDetails"

# SAFE - Single quotes (no interpolation)
'Failed to get PR #' + $PullRequest + ': ' + $errorDetails

# SAFE - Format operator
"Failed to get PR #{0}: {1}" -f $PullRequest, $errorDetails
```

### Rule

**ALWAYS** use `$($var)` or `${var}` when a variable is followed by a colon in double-quoted strings.

### Detection

PSScriptAnalyzer can help catch syntax issues during static analysis. See the pre-commit hook configuration for automated enforcement.

## Here-String Syntax

### Problem: Terminator Position

Here-string terminators (`"@` or `'@`) **must** start at column 0 with no leading whitespace.

### Examples

```powershell
# WRONG - Terminator is indented (causes error)
$content = @"
Some content here
  "@    # ERROR: The string is missing the terminator

# CORRECT - Terminator at column 0
$content = @"
Some content here
"@
```

### Detection

Error message: `The string is missing the terminator: "@`

## Parameter Conventions

### Standard Parameters

Use these approved verbs with consistent parameter names:

| Verb | Purpose | Common Parameters |
|------|---------|-------------------|
| `Get-` | Retrieve data | `-Name`, `-Id`, `-Filter` |
| `Set-` | Modify existing | `-Name`, `-Value`, `-PassThru` |
| `New-` | Create new | `-Name`, `-Path` |
| `Remove-` | Delete | `-Name`, `-Force`, `-WhatIf` |
| `Test-` | Validate/check | `-Path`, `-Quiet` |
| `Invoke-` | Execute action | `-Method`, `-Arguments` |

### Parameter Validation

Always validate parameters:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Name,

    [Parameter()]
    [ValidateRange(1, 100)]
    [int]$Count = 10,

    [Parameter()]
    [ValidateSet('Low', 'Medium', 'High')]
    [string]$Priority = 'Medium'
)
```

## Error Handling

### Standard Pattern

```powershell
# Set strict mode at script start
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    # Main logic here
    $result = Invoke-Operation -Name $Name
    Write-Output $result
}
catch {
    Write-Error "Operation failed: $_"
    exit 1
}
```

### Exit Codes

Follow project standard exit codes (see ADR-032):

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid parameters |
| 2 | Authentication failure |
| 3 | API error |
| 4 | Resource not found |
| 5 | Permission denied |

## Anti-Patterns to Avoid

### Do NOT Use

1. **Aliases in scripts** - Use `Get-Content` not `gc`, `ForEach-Object` not `%`
2. **Suppress errors silently** - Always handle or log errors
3. **Hardcoded paths** - Use `$PSScriptRoot` or parameters
4. **Missing CmdletBinding** - Always use for advanced functions
5. **Positional parameters in calls** - Use named parameters for clarity

### Example: Refactoring Anti-Patterns

```powershell
# BAD
gc $file | % { $_ -replace 'old', 'new' } | sc $out

# GOOD
Get-Content -Path $file |
    ForEach-Object { $_ -replace 'old', 'new' } |
    Set-Content -Path $out
```

## Module Structure

### Standard Layout

```text
ModuleName/
├── ModuleName.psd1      # Module manifest
├── ModuleName.psm1      # Main module file
├── Public/              # Exported functions
│   ├── Get-Item.ps1
│   └── Set-Item.ps1
├── Private/             # Internal functions
│   └── helpers.ps1
└── Tests/               # Pester tests
    └── ModuleName.Tests.ps1
```

### Export Pattern

```powershell
# In .psm1 file
$Public = @(Get-ChildItem -Path "$PSScriptRoot/Public/*.ps1" -ErrorAction SilentlyContinue)
$Private = @(Get-ChildItem -Path "$PSScriptRoot/Private/*.ps1" -ErrorAction SilentlyContinue)

foreach ($file in @($Public + $Private)) {
    try {
        . $file.FullName
    }
    catch {
        Write-Error "Failed to import $($file.FullName): $_"
    }
}

Export-ModuleMember -Function $Public.BaseName
```

## Comment-Based Help

### Template

```powershell
function Get-Example {
    <#
    .SYNOPSIS
        Brief description of function.

    .DESCRIPTION
        Detailed description of what the function does.

    .PARAMETER Name
        Description of the Name parameter.

    .EXAMPLE
        Get-Example -Name "Test"
        Description of what this example does.

    .OUTPUTS
        System.String. Returns the result.

    .NOTES
        Author: Team
        Version: 1.0.0
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    # Function body
}
```

## Related Resources

- Serena memory: `powershell-string-safety`
- Serena memory: `powershell-array-handling`
- ADR-032: Exit code standardization (pending)
- PSScriptAnalyzer: Automated linting

---

*Last updated: 2025-12-30 | Source: Issue #84, PR #79 retrospective*
