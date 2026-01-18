# PostToolUse Hooks

## Overview

PostToolUse hooks are triggered automatically by Claude Code after file Write/Edit operations. They enable non-blocking, automatic workflows like linting, formatting, and security scanning.

## Execution Model

**Trigger**: After `Write` or `Edit` tool use
**Input**: JSON via stdin containing tool parameters and context
**Exit Requirement**: **Always exit 0** (non-blocking)

PostToolUse hooks must never fail the primary operation. All errors should be logged as warnings, and the hook should always exit with code 0.

## Available Hooks

| Hook | Purpose | File Types | Performance |
|------|---------|------------|-------------|
| `Invoke-MarkdownAutoLint.ps1` | Auto-format markdown files | `*.md` | <2s |
| `Invoke-CodeQLQuickScan.ps1` | Security scan for code files | `*.py`, `*.yml` (workflows) | 5-30s |

## Hook Input Format

Hooks receive JSON via stdin:

```json
{
  "tool_input": {
    "file_path": "/absolute/path/to/file.ext",
    "content": "file content..."
  },
  "cwd": "/project/directory",
  "tool_name": "Write"
}
```

**Key Fields:**

- `tool_input.file_path`: Absolute path to the file that was written/edited
- `cwd`: Project directory (fallback: use `$env:CLAUDE_PROJECT_DIR`)
- `tool_name`: Tool that triggered the hook (`Write` or `Edit`)

## Writing a New Hook

### Template

```powershell
<#
.SYNOPSIS
    Brief description of what the hook does.

.DESCRIPTION
    Detailed description including:
    - What file types trigger this hook
    - What operation it performs
    - Performance characteristics

.NOTES
    Hook Type: PostToolUse
    Matcher: Write|Edit
    Filter: File type criteria (e.g., *.py, *.md)
    Exit Codes:
        0 = Always (non-blocking hook, all errors are warnings)

.LINK
    Related documentation or planning documents
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'  # Non-blocking hook

function Get-FilePathFromInput {
    param($HookInput)
    if ($HookInput.PSObject.Properties['tool_input'] -and
        $HookInput.tool_input.PSObject.Properties['file_path']) {
        return $HookInput.tool_input.file_path
    }
    return $null
}

function Get-ProjectDirectory {
    param($HookInput)
    if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
        return $env:CLAUDE_PROJECT_DIR
    }
    return $HookInput.cwd
}

function Test-ShouldProcessFile {
    <#
    .SYNOPSIS
        Determines if file should trigger hook logic.
    #>
    param([string]$FilePath)

    if ([string]::IsNullOrWhiteSpace($FilePath)) {
        return $false
    }

    if (-not (Test-Path $FilePath)) {
        Write-Verbose "File does not exist: $FilePath"
        return $false
    }

    # Add file type filtering logic here
    # Example: $FilePath.EndsWith('.ext', [StringComparison]::OrdinalIgnoreCase)

    return $true
}

try {
    # Check if stdin is available
    if (-not [Console]::IsInputRedirected) {
        exit 0
    }

    $inputJson = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($inputJson)) {
        exit 0
    }

    $hookInput = $inputJson | ConvertFrom-Json -ErrorAction Stop
    $filePath = Get-FilePathFromInput -HookInput $hookInput

    # Filter: Only process relevant file types
    if (-not (Test-ShouldProcessFile -FilePath $filePath)) {
        exit 0
    }

    $projectDir = Get-ProjectDirectory -HookInput $hookInput
    $previousLocation = Get-Location

    try {
        if (-not [string]::IsNullOrWhiteSpace($projectDir)) {
            Set-Location $projectDir
        }

        # TODO: Implement hook logic here
        # Example: Run linter, formatter, scanner, etc.

        Write-Output "`n**Hook Name**: Processed ``$filePath```n"
    }
    finally {
        Set-Location $previousLocation
    }
}
catch [System.ArgumentException], [System.InvalidOperationException] {
    Write-Verbose "Hook: Failed to parse input JSON - $($_.Exception.Message)"
}
catch [System.IO.IOException], [System.UnauthorizedAccessException] {
    Write-Verbose "Hook: File system error for $filePath - $($_.Exception.Message)"
}
catch {
    Write-Verbose "Hook unexpected error: $($_.Exception.GetType().FullName) - $($_.Exception.Message)"
}

# Always exit 0 (non-blocking hook)
exit 0
```

### Best Practices

1. **Always Exit 0**: Hooks must never block the user's primary operation
2. **Fast Execution**: Target <5 seconds; use timeouts for longer operations
3. **Graceful Degradation**: If dependencies missing, exit silently
4. **Verbose Logging**: Use `Write-Verbose` for debugging (not `Write-Host`)
5. **User-Facing Messages**: Use `Write-Output` for status messages shown to user
6. **File Type Filtering**: Only process files relevant to the hook
7. **Error Handling**: Catch all exceptions, log as warnings, never throw

### File Type Filtering Examples

```powershell
# Markdown files only
if (-not $FilePath.EndsWith('.md', [StringComparison]::OrdinalIgnoreCase)) {
    exit 0
}

# Python files only
if (-not $FilePath.EndsWith('.py', [StringComparison]::OrdinalIgnoreCase)) {
    exit 0
}

# GitHub Actions workflows only
if ($FilePath.EndsWith('.yml', [StringComparison]::OrdinalIgnoreCase) -or
    $FilePath.EndsWith('.yaml', [StringComparison]::OrdinalIgnoreCase)) {
    $normalizedPath = $FilePath -replace '\\', '/'
    if ($normalizedPath -match '\.github/workflows/') {
        # Process workflow file
    }
}
```

### Performance Guidelines

| Hook Type | Target Time | Max Time |
|-----------|-------------|----------|
| Formatting/Linting | <2s | 5s |
| Quick Security Scan | <15s | 30s |
| Full Analysis | Avoid in PostToolUse | Use pre-commit instead |

Use timeouts for operations that may exceed target time:

```powershell
$job = Start-Job -ScriptBlock {
    # Long-running operation
}

$completed = Wait-Job -Job $job -Timeout 30
if ($null -eq $completed) {
    Stop-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    Write-Warning "Operation timed out after 30 seconds"
    Write-Output "`n**Hook WARNING**: Operation timed out`n"
}
else {
    $result = Receive-Job -Job $job
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    # Process result
}
```

## Testing Hooks

### Manual Testing

```powershell
# Create test input
$testInput = @{
    tool_input = @{
        file_path = "/path/to/test/file.py"
    }
    cwd = "/path/to/project"
    tool_name = "Write"
} | ConvertTo-Json

# Pipe to hook
$testInput | pwsh .claude/hooks/PostToolUse/YourHook.ps1
```

### Automated Testing

Use Pester for automated testing:

```powershell
Describe "PostToolUse Hook Tests" {
    It "Exits with code 0 (non-blocking)" {
        $testInput = @{
            tool_input = @{ file_path = "test.py" }
            cwd = $PSScriptRoot
        } | ConvertTo-Json

        $testInput | pwsh ./YourHook.ps1
        $LASTEXITCODE | Should -Be 0
    }

    It "Gracefully handles missing file" {
        $testInput = @{
            tool_input = @{ file_path = "nonexistent.py" }
            cwd = $PSScriptRoot
        } | ConvertTo-Json

        { $testInput | pwsh ./YourHook.ps1 } | Should -Not -Throw
    }
}
```

## Debugging

### Enable Verbose Output

```powershell
$VerbosePreference = 'Continue'
pwsh .claude/hooks/PostToolUse/YourHook.ps1 -Verbose
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Hook not running | File type not matched | Check file extension filter |
| Hook running slow | No timeout on long operation | Add timeout with `Start-Job` |
| User sees errors | Using `throw` instead of `Write-Warning` | Catch all exceptions, exit 0 |
| Hook blocks user | Not exiting with 0 | Ensure all code paths exit 0 |

## References

- **Invoke-MarkdownAutoLint.ps1**: Reference implementation for simple hooks
- **Invoke-CodeQLQuickScan.ps1**: Reference implementation for complex hooks with timeouts
- **ADR-035**: Exit code standardization
- **Claude Code Hooks Documentation**: <https://code.claude.com/docs/en/hooks>
