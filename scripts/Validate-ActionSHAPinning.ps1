<#
.SYNOPSIS
    Validates that all GitHub Actions are pinned to commit SHA, not version tags.

.DESCRIPTION
    Scans all workflow files in .github/workflows/ for third-party action references.
    Ensures actions are pinned to commit SHA (40 hex characters) rather than mutable
    version tags (e.g., @v4, @v3.2.1).
    
    Implements security constraint from PROJECT-CONSTRAINTS.md and security-practices.md.

.PARAMETER Path
    Base path to scan. Default: current directory.

.PARAMETER CI
    CI mode - returns non-zero exit code on failures.

.PARAMETER Format
    Output format: "console", "markdown", or "json".
    Default: "console"

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1 -CI

.EXAMPLE
    .\Validate-ActionSHAPinning.ps1 -Format markdown
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
        Write-Output "${Color}${Message}${ColorReset}"
    }
}
#endregion

#region Main Logic

# Resolve path
$resolvedPath = Resolve-Path $Path -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Path not found: $Path"
    exit 1
}

# Find all workflow files
$workflowPath = Join-Path $resolvedPath ".github/workflows"
if (-not (Test-Path $workflowPath)) {
    Write-ColorOutput "No .github/workflows directory found at $resolvedPath" $ColorYellow
    if ($Format -eq "json") {
        @{
            status = "skipped"
            message = "No workflows directory"
            violations = @()
        } | ConvertTo-Json -Depth 10
    }
    exit 0
}

$workflowFiles = @(Get-ChildItem -Path $workflowPath -Filter "*.yml" -File -ErrorAction SilentlyContinue)
$workflowFiles += @(Get-ChildItem -Path $workflowPath -Filter "*.yaml" -File -ErrorAction SilentlyContinue)

if ($workflowFiles.Count -eq 0) {
    Write-ColorOutput "No workflow files found in $workflowPath" $ColorYellow
    if ($Format -eq "json") {
        @{
            status = "skipped"
            message = "No workflow files"
            violations = @()
        } | ConvertTo-Json -Depth 10
    }
    exit 0
}

Write-ColorOutput "Scanning $($workflowFiles.Count) workflow file(s)..." $ColorCyan

# Regex pattern to detect version tag usage
# Matches: uses: <action>@v<digits>[.<digits>]*
# Excludes: 40 hex character SHAs, local actions (./)
# Note: Accounts for YAML list markers (-)
$versionTagPattern = '^\s*-?\s*uses:\s+([^@]+)@(v\d+(?:\.\d+)*)\s*(?:#.*)?$'

$violations = @()

foreach ($file in $workflowFiles) {
    $content = Get-Content -Path $file.FullName -Raw
    $lines = $content -split "`r?`n"
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        
        # Skip local actions (uses: ./)
        if ($line -match '^\s*uses:\s+\.\/') {
            continue
        }
        
        # Check for version tag pattern
        if ($line -match $versionTagPattern) {
            $action = $Matches[1]
            $tag = $Matches[2]
            $lineNum = $i + 1
            
            $violations += [PSCustomObject]@{
                File = $file.Name
                FullPath = $file.FullName
                Line = $lineNum
                Action = $action
                Tag = $tag
                Content = $line.Trim()
            }
        }
    }
}

#endregion

#region Output

if ($violations.Count -eq 0) {
    Write-ColorOutput "✅ All GitHub Actions are SHA-pinned" $ColorGreen
    Write-ColorOutput "   Scanned $($workflowFiles.Count) workflow file(s)" $ColorCyan
    
    if ($Format -eq "json") {
        @{
            status = "pass"
            filesScanned = $workflowFiles.Count
            violations = @()
        } | ConvertTo-Json -Depth 10
    }
    elseif ($Format -eq "markdown") {
        Write-Output "## GitHub Actions SHA Pinning Validation"
        Write-Output ""
        Write-Output "**Status**: ✅ PASS"
        Write-Output ""
        Write-Output "**Files Scanned**: $($workflowFiles.Count)"
        Write-Output ""
        Write-Output "All GitHub Actions are properly pinned to commit SHA."
    }
    
    exit 0
}
else {
    Write-ColorOutput "❌ GitHub Actions MUST be pinned to SHA, not version tags" $ColorRed
    Write-ColorOutput "" $ColorReset
    Write-ColorOutput "Found $($violations.Count) violation(s):" $ColorYellow
    Write-ColorOutput "" $ColorReset
    
    if ($Format -eq "console") {
        foreach ($v in $violations) {
            Write-ColorOutput "  $($v.File):$($v.Line)" $ColorRed
            Write-ColorOutput "    uses: $($v.Action)@$($v.Tag)" $ColorYellow
        }
        
        Write-ColorOutput "" $ColorReset
        Write-ColorOutput "Required pattern:" $ColorCyan
        Write-ColorOutput "  uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2" $ColorGreen
        Write-ColorOutput "" $ColorReset
        Write-ColorOutput "To find SHA for a version tag:" $ColorCyan
        Write-ColorOutput "  gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'" $ColorCyan
        Write-ColorOutput "" $ColorReset
        Write-ColorOutput "Reference:" $ColorCyan
        Write-ColorOutput "  .agents/steering/security-practices.md#github-actions-security" $ColorCyan
        Write-ColorOutput "  .agents/governance/PROJECT-CONSTRAINTS.md#security-constraints" $ColorCyan
    }
    elseif ($Format -eq "markdown") {
        Write-Output "## GitHub Actions SHA Pinning Validation"
        Write-Output ""
        Write-Output "**Status**: ❌ FAIL"
        Write-Output ""
        Write-Output "**Files Scanned**: $($workflowFiles.Count)"
        Write-Output ""
        Write-Output "**Violations Found**: $($violations.Count)"
        Write-Output ""
        Write-Output "### Violations"
        Write-Output ""
        Write-Output "| File | Line | Action | Tag |"
        Write-Output "|------|------|--------|-----|"
        
        foreach ($v in $violations) {
            Write-Output "| $($v.File) | $($v.Line) | ``$($v.Action)`` | ``$($v.Tag)`` |"
        }
        
        Write-Output ""
        Write-Output "### Required Pattern"
        Write-Output ""
        Write-Output '```yaml'
        Write-Output "uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2"
        Write-Output '```'
        Write-Output ""
        Write-Output "### How to Fix"
        Write-Output ""
        Write-Output "Find SHA for version tag:"
        Write-Output '```bash'
        Write-Output "gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'"
        Write-Output '```'
        Write-Output ""
        Write-Output "**References**:"
        Write-Output "- `.agents/steering/security-practices.md#github-actions-security`"
        Write-Output "- `.agents/governance/PROJECT-CONSTRAINTS.md#security-constraints`"
    }
    elseif ($Format -eq "json") {
        @{
            status = "fail"
            filesScanned = $workflowFiles.Count
            violationCount = $violations.Count
            violations = $violations | ForEach-Object {
                @{
                    file = $_.File
                    line = $_.Line
                    action = $_.Action
                    tag = $_.Tag
                    content = $_.Content
                }
            }
        } | ConvertTo-Json -Depth 10
    }
    
    if ($CI) {
        exit 1
    }
    else {
        exit 0
    }
}

#endregion
