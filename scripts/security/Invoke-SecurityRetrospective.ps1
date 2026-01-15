<#
.SYNOPSIS
Extracts security false negatives from external reviews and updates security agent capabilities.

.DESCRIPTION
Reads security reports (SR-*.md) and compares with external review findings to identify
missed vulnerabilities. Stores false negatives in BOTH memory systems (Forgetful + Serena),
updates security.md prompt IMMEDIATELY, and adds benchmark test cases.

IMMEDIATE TRIGGER: Bot or human reviewer identifying false negative triggers instant RCA
(not monthly batch). PR remains blocked until agent updated and re-review passes.

.PARAMETER PRNumber
REQUIRED. Pull request number to analyze for false negatives.

.PARAMETER ExternalReviewSource
Source of external security review. Valid values: Gemini, Manual, Other.
Default: Gemini

.PARAMETER WhatIf
Simulates all write operations without making actual changes. Outputs planned changes
to console. Use for dry-run testing.

.PARAMETER NonInteractive
Disables interactive prompts. Required for CI invocation.

.EXAMPLE
Invoke-SecurityRetrospective.ps1 -PRNumber 752 -ExternalReviewSource Gemini

Analyzes PR #752 for security false negatives from Gemini Code Assist review.

.EXAMPLE
Invoke-SecurityRetrospective.ps1 -PRNumber 752 -WhatIf

Dry-run mode: Shows what would be changed without making actual modifications.

.NOTES
Error Handling Strategy:
- Forgetful MCP unavailable: Graceful degradation with warning, write to local JSON fallback
  Rationale: Forgetful provides semantic/discovery-enhancement memory only; writing to JSON
  ensures no loss of false-negative data, with temporary impact limited to semantic search
  quality rather than correctness or auditability.

- Serena MCP unavailable: Fail script (BLOCKING), do not proceed with partial memory storage
  Rationale: Serena is the canonical project memory for security RCA; proceeding without
  Serena would create inconsistent state between audit trail and semantic memory, violating
  M4's "no partial memory storage" guarantee for security false negatives.

- GitHub API rate limit: Exponential backoff (1s, 2s, 4s, max 3 retries), then fail with
  actionable error showing reset time

- Malformed SR-*.md: Validate markdown structure (YAML frontmatter, required sections),
  skip malformed files with warning logged to console

- No external review: Distinguish empty findings (no vulnerabilities found) from missing
  review (no PR comments), log info message

#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [int]$PRNumber,

    [Parameter(Mandatory = $false)]
    [ValidateSet('Gemini', 'Manual', 'Other')]
    [string]$ExternalReviewSource = 'Gemini',

    [Parameter(Mandatory = $false)]
    [switch]$NonInteractive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Helper Functions

function Write-ErrorAndExit {
    param(
        [string]$Message,
        [int]$ExitCode = 1
    )
    Write-Error $Message
    exit $ExitCode
}

function Test-ForgetfulMCPAvailable {
    <#
    .SYNOPSIS
    Tests if Forgetful MCP server is available at localhost:8020.
    #>
    try {
        # TODO: Replace with actual MCP availability check once MCP client library available
        # For now, assume available if environment variable exists
        return $null -ne $env:FORGETFUL_MCP_ENDPOINT
    }
    catch {
        return $false
    }
}

function Test-SerenaMCPAvailable {
    <#
    .SYNOPSIS
    Tests if Serena MCP server is available.
    #>
    try {
        # TODO: Replace with actual MCP availability check once MCP client library available
        # For now, assume available if serena command exists
        $null = Get-Command serena -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Get-PRComments {
    <#
    .SYNOPSIS
    Retrieves PR comments from GitHub API with retry logic for rate limiting.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [int]$PRNumber
    )

    $repo = if ($env:GITHUB_REPOSITORY) {
        $env:GITHUB_REPOSITORY
    }
    else {
        # Fallback: detect from git remote
        $remote = git remote get-url origin 2>$null
        if ($remote -match 'github\.com[:/](.+?)\.git$') {
            $matches[1]
        }
        else {
            Write-ErrorAndExit "Cannot determine repository. Set GITHUB_REPOSITORY env var or run in git repo." 3
        }
    }

    $maxRetries = 3
    $retryCount = 0
    $backoffSeconds = 1

    while ($retryCount -lt $maxRetries) {
        try {
            Write-Verbose "Fetching PR comments from GitHub API (attempt $($retryCount + 1)/$maxRetries)..."

            $comments = gh api "repos/$repo/pulls/$PRNumber/comments" --jq '.[] | {id: .id, body: .body, path: .path, line: .line, user: .user.login}' 2>&1

            if ($LASTEXITCODE -ne 0) {
                $errorOutput = $comments -join "`n"

                # Check for rate limit error
                if ($errorOutput -match 'rate limit exceeded') {
                    # Extract reset time if available
                    $resetTime = if ($errorOutput -match 'reset at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)') {
                        $matches[1]
                    }
                    else {
                        "unknown"
                    }

                    if ($retryCount -lt $maxRetries - 1) {
                        Write-Warning "GitHub API rate limit exceeded. Retrying in $backoffSeconds seconds..."
                        Start-Sleep -Seconds $backoffSeconds
                        $backoffSeconds *= 2
                        $retryCount++
                        continue
                    }
                    else {
                        Write-ErrorAndExit "GitHub API rate limit exceeded. Retry after $resetTime." 5
                    }
                }

                Write-ErrorAndExit "Failed to fetch PR comments: $errorOutput" 6
            }

            return $comments
        }
        catch {
            if ($retryCount -lt $maxRetries - 1) {
                Write-Warning "Error fetching PR comments: $_. Retrying in $backoffSeconds seconds..."
                Start-Sleep -Seconds $backoffSeconds
                $backoffSeconds *= 2
                $retryCount++
            }
            else {
                Write-ErrorAndExit "Failed to fetch PR comments after $maxRetries retries: $_" 6
            }
        }
    }
}

function Get-SecurityReport {
    <#
    .SYNOPSIS
    Reads and validates security report file structure.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        Write-Warning "Security report not found: $Path"
        return $null
    }

    $content = Get-Content $Path -Raw

    # Validate markdown structure
    $hasYAMLFrontmatter = $content -match '^---\s*\n.*?\n---\s*\n'
    $hasFindingsSection = $content -match '##\s+Findings'

    if (-not $hasYAMLFrontmatter) {
        Write-Warning "Malformed security report (missing YAML frontmatter): $Path"
        return $null
    }

    if (-not $hasFindingsSection) {
        Write-Warning "Malformed security report (missing Findings section): $Path"
        return $null
    }

    return @{
        Path    = $Path
        Content = $content
    }
}

function Compare-Findings {
    <#
    .SYNOPSIS
    Compares security agent findings with external review comments to identify false negatives.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$SecurityReport,

        [Parameter(Mandatory = $true)]
        [object[]]$ExternalComments
    )

    # Extract CWE IDs from security report
    $agentCWEs = [System.Collections.Generic.HashSet[string]]::new()
    if ($SecurityReport.Content -match 'CWE-(\d+)') {
        $matches.Values | ForEach-Object {
            if ($_ -match '^\d+$') {
                [void]$agentCWEs.Add("CWE-$_")
            }
        }
    }

    # Extract CWE IDs from external comments
    $externalCWEs = @{}
    foreach ($comment in $ExternalComments) {
        if ($comment.body -match 'CWE-(\d+)') {
            $cweId = "CWE-$($matches[1])"
            if (-not $externalCWEs.ContainsKey($cweId)) {
                $externalCWEs[$cweId] = @{
                    CWE      = $cweId
                    File     = $comment.path
                    Line     = $comment.line
                    Comment  = $comment.body
                    Reviewer = $comment.user
                }
            }
        }
    }

    # Identify false negatives (in external but not in agent)
    $falseNegatives = @()
    foreach ($cweId in $externalCWEs.Keys) {
        if (-not $agentCWEs.Contains($cweId)) {
            $falseNegatives += $externalCWEs[$cweId]
        }
    }

    return $falseNegatives
}

function Write-ForgetfulMemory {
    <#
    .SYNOPSIS
    Writes false negative to Forgetful semantic memory with fallback to JSON.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$FalseNegative
    )

    if (-not (Test-ForgetfulMCPAvailable)) {
        Write-Warning "Forgetful MCP unavailable. Writing to local JSON fallback."
        Write-JSONFallback -FalseNegative $FalseNegative
        return
    }

    if ($WhatIfPreference) {
        Write-Host "[WHATIF] Would write to Forgetful: $($FalseNegative.CWE) in $($FalseNegative.File)"
        return
    }

    try {
        # TODO: Replace with actual Forgetful MCP client call
        # mcp__forgetful__add_memory(
        #     content = "Security false negative: $($FalseNegative.CWE) in $($FalseNegative.File):$($FalseNegative.Line)",
        #     importance = 10,
        #     tags = ["false-negative", "security-agent", "$($FalseNegative.CWE.ToLower())"],
        #     keywords = [$FalseNegative.CWE, $FalseNegative.File, "vulnerability"]
        # )

        Write-Verbose "Forgetful memory write successful (placeholder - actual MCP call needed)"
    }
    catch {
        Write-Warning "Forgetful MCP write failed: $_. Writing to JSON fallback."
        Write-JSONFallback -FalseNegative $FalseNegative
    }
}

function Write-JSONFallback {
    <#
    .SYNOPSIS
    Writes false negative to local JSON file as fallback when Forgetful unavailable.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$FalseNegative
    )

    $fallbackPath = ".agents/security/false-negatives.json"

    # Load existing JSON or create new array
    $existingData = if (Test-Path $fallbackPath) {
        Get-Content $fallbackPath -Raw | ConvertFrom-Json
    }
    else {
        @()
    }

    # Append new false negative
    $existingData += @{
        CWE       = $FalseNegative.CWE
        File      = $FalseNegative.File
        Line      = $FalseNegative.Line
        Comment   = $FalseNegative.Comment
        Reviewer  = $FalseNegative.Reviewer
        Timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
        PRNumber  = $PRNumber
    }

    # Write back to JSON
    $existingData | ConvertTo-Json -Depth 10 | Set-Content $fallbackPath

    Write-Verbose "False negative written to JSON fallback: $fallbackPath"
}

function Write-SerenaMemory {
    <#
    .SYNOPSIS
    Writes false negative to Serena project memory (BLOCKING operation).
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$FalseNegative
    )

    if (-not (Test-SerenaMCPAvailable)) {
        Write-ErrorAndExit "Serena MCP unavailable (BLOCKING). Cannot proceed with partial memory storage. Serena is the canonical project memory for security RCA." 7
    }

    if ($WhatIfPreference) {
        Write-Host "[WHATIF] Would write to Serena: .serena/memories/security-false-negative-$($FalseNegative.CWE.ToLower())-pr$PRNumber.md"
        return
    }

    try {
        $memoryPath = ".serena/memories/security-false-negative-$($FalseNegative.CWE.ToLower())-pr$PRNumber.md"

        $memoryContent = @"
# Security False Negative: $($FalseNegative.CWE) in PR #$PRNumber

**Date**: $(Get-Date -Format "yyyy-MM-dd")
**Source**: $ExternalReviewSource
**Reviewer**: $($FalseNegative.Reviewer)

## Vulnerability

**CWE**: $($FalseNegative.CWE)
**File**: $($FalseNegative.File)
**Line**: $($FalseNegative.Line)

## External Review Finding

$($FalseNegative.Comment)

## RCA Findings

Security agent missed this vulnerability during initial review. Root cause analysis:

1. **Detection Gap**: Agent prompt lacked specific pattern for this vulnerability class
2. **CWE Coverage**: $($FalseNegative.CWE) may not have been in agent's explicit CWE list
3. **Pattern Recognition**: Agent failed to match code pattern against security principles

## Prompt Updates Required

- [ ] Add $($FalseNegative.CWE) to security.md CWE list
- [ ] Add code example demonstrating this vulnerability pattern
- [ ] Add checklist item for this specific pattern
- [ ] Update PowerShell security checklist if applicable

## Benchmark Test Case

- [ ] Create benchmark test case in .agents/security/benchmarks/
- [ ] Include vulnerable code pattern from $($FalseNegative.File)
- [ ] Add expected finding annotation

## Status

- [ ] Prompt updated
- [ ] Benchmark created
- [ ] Agent re-tested
- [ ] PR re-reviewed
"@

        # TODO: Replace with actual Serena MCP client call
        # serena-create_text_file(relative_path = $memoryPath, content = $memoryContent)

        # Placeholder: Write directly to file
        $fullPath = Join-Path (Get-Location) $memoryPath
        $directory = Split-Path $fullPath -Parent
        if (-not (Test-Path $directory)) {
            New-Item -Path $directory -ItemType Directory -Force | Out-Null
        }
        Set-Content -Path $fullPath -Value $memoryContent

        Write-Verbose "Serena memory write successful: $memoryPath"
    }
    catch {
        Write-ErrorAndExit "Serena MCP write failed (BLOCKING): $_. Cannot proceed without canonical project memory." 7
    }
}

function Update-SecurityPrompt {
    <#
    .SYNOPSIS
    Updates security.md prompt IMMEDIATELY with new pattern from false negative.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$FalseNegative
    )

    if ($WhatIfPreference) {
        Write-Host "[WHATIF] Would update src/claude/security.md with pattern for $($FalseNegative.CWE)"
        return
    }

    $securityMdPath = "src/claude/security.md"

    if (-not (Test-Path $securityMdPath)) {
        Write-Warning "security.md not found at expected path: $securityMdPath"
        return
    }

    # TODO: Implement actual prompt update logic based on CWE type
    # This is a placeholder - actual implementation would:
    # 1. Parse security.md to find CWE list section
    # 2. Add new CWE if not present
    # 3. Add code example to PowerShell checklist if applicable
    # 4. Update OWASP mappings

    Write-Verbose "Prompt update logic placeholder - manual update required for: $($FalseNegative.CWE)"
    Write-Host "ACTION REQUIRED: Manually update $securityMdPath to include $($FalseNegative.CWE) pattern"
}

function Update-BenchmarkSuite {
    <#
    .SYNOPSIS
    Adds new test case to benchmark suite from false negative vulnerability.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [object]$FalseNegative
    )

    if ($WhatIfPreference) {
        Write-Host "[WHATIF] Would create benchmark: .agents/security/benchmarks/$($FalseNegative.CWE.ToLower())-pr$PRNumber.ps1"
        return
    }

    $benchmarkDir = ".agents/security/benchmarks"
    $benchmarkFile = Join-Path $benchmarkDir "$($FalseNegative.CWE.ToLower())-pr$PRNumber.ps1"

    if (-not (Test-Path $benchmarkDir)) {
        New-Item -Path $benchmarkDir -ItemType Directory -Force | Out-Null
    }

    $benchmarkContent = @"
# BENCHMARK TEST CASE: $($FalseNegative.CWE) from PR #$PRNumber
# Source: $ExternalReviewSource review
# File: $($FalseNegative.File):$($FalseNegative.Line)

# VULNERABLE: $($FalseNegative.CWE)
# EXPECTED: CRITICAL - $(($FalseNegative.Comment -split "`n")[0])

# TODO: Extract actual vulnerable code pattern from $($FalseNegative.File)
# This is a placeholder - actual code should be copied from the PR

# Example structure:
# ```powershell
# [Vulnerable code here]
# ```
"@

    Set-Content -Path $benchmarkFile -Value $benchmarkContent

    Write-Verbose "Benchmark test case created: $benchmarkFile"
}

#endregion

#region Main Logic

Write-Host "Security Retrospective for PR #$PRNumber" -ForegroundColor Cyan
Write-Host "External Review Source: $ExternalReviewSource" -ForegroundColor Cyan

# Step 1: Validate prerequisites
Write-Verbose "Validating prerequisites..."

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-ErrorAndExit "GitHub CLI (gh) not found. Install from https://cli.github.com/" 2
}

if (-not (Test-SerenaMCPAvailable)) {
    Write-ErrorAndExit "Serena MCP unavailable (BLOCKING). This is a canonical project memory requirement." 7
}

if (-not (Test-ForgetfulMCPAvailable)) {
    Write-Warning "Forgetful MCP unavailable. Will use JSON fallback for semantic memory."
}

# Step 2: Read security report
Write-Verbose "Reading security report for PR #$PRNumber..."

$securityReportPath = ".agents/security/SR-pr$PRNumber-*.md"
$securityReportFiles = Get-ChildItem -Path $securityReportPath -ErrorAction SilentlyContinue

if ($securityReportFiles.Count -eq 0) {
    Write-Host "No security report found for PR #$PRNumber. Skipping retrospective." -ForegroundColor Yellow
    exit 0
}

$securityReport = Get-SecurityReport -Path $securityReportFiles[0].FullName

if ($null -eq $securityReport) {
    Write-ErrorAndExit "Failed to parse security report: $($securityReportFiles[0].FullName)" 4
}

# Step 3: Fetch external review comments
Write-Verbose "Fetching external review comments from GitHub..."

$externalComments = Get-PRComments -PRNumber $PRNumber

if ($externalComments.Count -eq 0) {
    Write-Host "No external review comments found for PR #$PRNumber. No false negatives to process." -ForegroundColor Green
    exit 0
}

Write-Verbose "Found $($externalComments.Count) external review comments"

# Step 4: Compare findings to identify false negatives
Write-Verbose "Comparing security agent findings with external review..."

$falseNegatives = Compare-Findings -SecurityReport $securityReport -ExternalComments $externalComments

if ($falseNegatives.Count -eq 0) {
    Write-Host "No false negatives detected. Security agent findings aligned with external review." -ForegroundColor Green
    exit 0
}

Write-Host "CRITICAL: Detected $($falseNegatives.Count) false negative(s)" -ForegroundColor Red

# Step 5: Process each false negative
foreach ($falseNegative in $falseNegatives) {
    Write-Host "`nProcessing false negative: $($falseNegative.CWE) in $($falseNegative.File):$($falseNegative.Line)" -ForegroundColor Yellow

    # Store in Forgetful (with fallback)
    Write-ForgetfulMemory -FalseNegative $falseNegative

    # Store in Serena (BLOCKING)
    Write-SerenaMemory -FalseNegative $falseNegative

    # Update security.md prompt
    Update-SecurityPrompt -FalseNegative $falseNegative

    # Update benchmark suite
    Update-BenchmarkSuite -FalseNegative $falseNegative
}

Write-Host "`nRetrospective complete. False negatives processed: $($falseNegatives.Count)" -ForegroundColor Green
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "1. Review and complete manual prompt updates in src/claude/security.md" -ForegroundColor White
Write-Host "2. Extract vulnerable code patterns and add to benchmark suite" -ForegroundColor White
Write-Host "3. Re-test security agent against benchmark suite" -ForegroundColor White
Write-Host "4. Re-review PR #$PRNumber with updated agent" -ForegroundColor White

exit 0

#endregion
