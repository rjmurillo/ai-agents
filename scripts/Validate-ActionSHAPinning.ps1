<#
.SYNOPSIS
    Validates that all GitHub Actions in workflows are pinned to commit SHA, not version tags.

.DESCRIPTION
    Scans all GitHub workflow files (.github/workflows/*.yml and *.yaml) to ensure third-party
    actions are pinned to immutable commit SHAs rather than mutable version tags.
    
    This enforces supply chain security best practices per:
    - .agents/governance/PROJECT-CONSTRAINTS.md#security-constraints
    - .agents/steering/security-practices.md#github-actions-security
    
    Version tags (e.g., @v4, @v3.2.1) can be moved by compromised maintainers to point to
    malicious code. SHA pinning ensures reviewed code cannot be silently replaced.

.PARAMETER Path
    Base path to scan for workflows. Default: current directory.

.PARAMETER CI
    CI mode - returns non-zero exit code if violations found.

.PARAMETER Format
    Output format: "console", "markdown", or "json".
    Default: "console"

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1 -CI

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1 -Format markdown

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1 -Path /path/to/repo -CI
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Path = ".",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [ValidateSet("console", "markdown", "json")]
    [string]$Format = "console"
)

#region Color Output
$ColorReset = "`e[0m"
$ColorRed = "`e[31m"
$ColorYellow = "`e[33m"
$ColorGreen = "`e[32m"
$ColorCyan = "`e[36m"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    if ($Format -eq "console") {
        Write-Host "${Color}${Message}${ColorReset}"
    }
}
#endregion

#region Main Validation Logic

# Resolve path to absolute
$Path = Resolve-Path $Path -ErrorAction Stop

# Find all workflow files
$workflowPattern = Join-Path $Path ".github/workflows/*.y*ml"
$workflowFiles = Get-ChildItem -Path $workflowPattern -File -ErrorAction SilentlyContinue

if (-not $workflowFiles) {
    Write-ColorOutput "No workflow files found in $Path/.github/workflows/" $ColorYellow
    if ($Format -eq "json") {
        @{
            summary = @{
                total = 0
                violations = 0
                compliant = 0
            }
            files = @()
        } | ConvertTo-Json -Depth 10
    }
    exit 0
}

Write-ColorOutput "Scanning $($workflowFiles.Count) workflow file(s)..." $ColorCyan

# Regex patterns
# Matches: uses: <action>@v<number> (with optional dots and more numbers)
# Examples: @v4, @v3.2, @v1.2.3
$versionTagPattern = '^\s*uses:\s+([^@]+)@(v\d+(?:\.\d+)*(?:\.\d+)?)\s*(?:#.*)?$'

# Matches: uses: <action>@<40 hex chars> (SHA)
$shaPattern = '^\s*uses:\s+([^@]+)@([a-f0-9]{40})\s*(?:#.*)?$'

# Matches: uses: ./ or uses: ./.github/ (local actions)
$localActionPattern = '^\s*uses:\s+\./'

$violations = @()
$compliantFiles = @()

foreach ($file in $workflowFiles) {
    $content = Get-Content $file.FullName -Raw
    $lines = $content -split "`n"
    
    $fileViolations = @()
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        $lineNum = $i + 1
        
        # Skip local actions (relative paths)
        if ($line -match $localActionPattern) {
            continue
        }
        
        # Check for version tag pattern
        if ($line -match $versionTagPattern) {
            # Verify it's not actually a SHA (would be caught by both patterns)
            if ($line -notmatch $shaPattern) {
                $action = $Matches[1]
                $tag = $Matches[2]
                
                $fileViolations += [PSCustomObject]@{
                    File = $file.Name
                    FilePath = $file.FullName
                    Line = $lineNum
                    Action = $action
                    Tag = $tag
                    LineContent = $line.Trim()
                }
            }
        }
    }
    
    if ($fileViolations.Count -gt 0) {
        $violations += $fileViolations
    } else {
        $compliantFiles += $file.Name
    }
}

#endregion

#region Output

$totalFiles = $workflowFiles.Count
$violationCount = $violations.Count
$compliantCount = $compliantFiles.Count

if ($Format -eq "console") {
    Write-ColorOutput ""
    Write-ColorOutput "=== GitHub Actions SHA Pinning Validation ===" $ColorCyan
    Write-ColorOutput ""
    Write-ColorOutput "Total workflow files: $totalFiles" $ColorCyan
    Write-ColorOutput "Compliant files: $compliantCount" $ColorGreen
    Write-ColorOutput "Files with violations: $($violations | Select-Object -ExpandProperty File -Unique).Count" $ColorRed
    Write-ColorOutput "Total violations: $violationCount" $ColorRed
    Write-ColorOutput ""
    
    if ($violations.Count -gt 0) {
        Write-ColorOutput "Violations found:" $ColorRed
        Write-ColorOutput ""
        
        foreach ($v in $violations) {
            Write-ColorOutput "  $($v.File):$($v.Line)" $ColorYellow
            Write-ColorOutput "    Action: $($v.Action)" $ColorYellow
            Write-ColorOutput "    Current: uses: $($v.Action)@$($v.Tag)" $ColorRed
            Write-ColorOutput "    Required: uses: $($v.Action)@<SHA> # $($v.Tag)" $ColorGreen
            Write-ColorOutput ""
        }
        
        Write-ColorOutput "To find SHA for a version tag:" $ColorCyan
        Write-ColorOutput "  gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'" $ColorCyan
        Write-ColorOutput ""
        Write-ColorOutput "Example:" $ColorCyan
        Write-ColorOutput "  gh api repos/actions/checkout/git/ref/tags/v4.2.2 --jq '.object.sha'" $ColorCyan
        Write-ColorOutput ""
        Write-ColorOutput "Reference: .agents/steering/security-practices.md#github-actions-security" $ColorCyan
    } else {
        Write-ColorOutput "✅ All GitHub Actions are SHA-pinned" $ColorGreen
    }
}
elseif ($Format -eq "markdown") {
    Write-Output "# GitHub Actions SHA Pinning Validation"
    Write-Output ""
    Write-Output "## Summary"
    Write-Output ""
    Write-Output "| Metric | Count |"
    Write-Output "|--------|-------|"
    Write-Output "| Total workflow files | $totalFiles |"
    Write-Output "| Compliant files | $compliantCount |"
    Write-Output "| Files with violations | $($violations | Select-Object -ExpandProperty File -Unique | Measure-Object).Count |"
    Write-Output "| Total violations | $violationCount |"
    Write-Output ""
    
    if ($violations.Count -gt 0) {
        Write-Output "## Violations"
        Write-Output ""
        Write-Output "| File | Line | Action | Current Reference | Required Format |"
        Write-Output "|------|------|--------|-------------------|-----------------|"
        
        foreach ($v in $violations) {
            Write-Output "| $($v.File) | $($v.Line) | $($v.Action) | @$($v.Tag) | @\<SHA\> # $($v.Tag) |"
        }
        
        Write-Output ""
        Write-Output "## How to Fix"
        Write-Output ""
        Write-Output "Find the commit SHA for each version tag:"
        Write-Output ""
        Write-Output '```bash'
        Write-Output "gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'"
        Write-Output '```'
        Write-Output ""
        Write-Output "Example:"
        Write-Output ""
        Write-Output '```bash'
        Write-Output "gh api repos/actions/checkout/git/ref/tags/v4.2.2 --jq '.object.sha'"
        Write-Output '```'
        Write-Output ""
        Write-Output "**Reference**: [security-practices.md](../.agents/steering/security-practices.md#github-actions-security)"
    } else {
        Write-Output "✅ All GitHub Actions are SHA-pinned"
    }
}
elseif ($Format -eq "json") {
    $output = @{
        summary          = @{
            total               = $totalFiles
            violations          = $violationCount
            compliant           = $compliantCount
            filesWithViolations = ($violations | Select-Object -ExpandProperty File -Unique).Count
        }
        violations       = @($violations | ForEach-Object {
                @{
                    file        = $_.File
                    filePath    = $_.FilePath
                    line        = $_.Line
                    action      = $_.Action
                    currentTag  = $_.Tag
                    lineContent = $_.LineContent
                }
            })
        compliantFiles   = @($compliantFiles)
    }
    
    $output | ConvertTo-Json -Depth 10
}

#endregion

#region Exit Code

if ($CI -and $violations.Count -gt 0) {
    exit 1
}

exit 0

#endregion
