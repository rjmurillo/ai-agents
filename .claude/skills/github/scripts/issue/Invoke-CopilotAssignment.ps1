<#
.SYNOPSIS
    Synthesizes context and assigns GitHub Copilot to an issue.

.DESCRIPTION
    Fetches issue comments, extracts context from trusted sources (maintainers, AI agents),
    generates a synthesis comment with @copilot mention, and assigns copilot-swe-agent.

    Idempotent: If a synthesis comment already exists (detected via marker), it updates
    the existing comment rather than creating a duplicate.

.PARAMETER IssueNumber
    The issue number to synthesize context for (required).

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER ConfigPath
    Path to copilot-synthesis.yml config file. Defaults to .claude/skills/github/copilot-synthesis.yml.

.PARAMETER SkipAssignment
    Skip the copilot-swe-agent assignment. Use when assignment is handled
    separately with a COPILOT_GITHUB_TOKEN (workflow pattern).

.PARAMETER WhatIf
    Preview the synthesis comment without posting or assigning.

.EXAMPLE
    .\Invoke-CopilotAssignment.ps1 -IssueNumber 123

.EXAMPLE
    .\Invoke-CopilotAssignment.ps1 -IssueNumber 123 -SkipAssignment

.EXAMPLE
    .\Invoke-CopilotAssignment.ps1 -IssueNumber 123 -WhatIf

.NOTES
    Exit Codes:
        0 = Success (includes idempotent update)
        1 = Invalid parameters
        2 = Issue not found
        3 = API error
        4 = Not authenticated
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [int]$IssueNumber,

    [string]$Owner,

    [string]$Repo,

    [string]$ConfigPath,

    [switch]$SkipAssignment
)

# Import shared helpers - reuse existing functions (DRY)
$modulePath = Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1"
Import-Module $modulePath -Force

#region Configuration

function Get-SynthesisConfig {
    <#
    .SYNOPSIS
        Loads the copilot-synthesis.yml configuration.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param(
        [string]$ConfigPath
    )

    # Default configuration (used if config file not found)
    $defaultConfig = @{
        trusted_sources = @{
            maintainers = @("rjmurillo")
            ai_agents   = @("rjmurillo-bot", "coderabbitai[bot]", "copilot[bot]", "cursor[bot]", "github-actions[bot]")
        }
        extraction_patterns = @{
            coderabbit = @{
                implementation_plan = "## Implementation"
                related_issues      = "🔗 Similar Issues"
                related_prs         = "🔗 Related PRs"
            }
            ai_triage = @{
                marker   = "<!-- AI-ISSUE-TRIAGE -->"
            }
        }
        synthesis = @{
            marker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
        }
    }

    if (-not $ConfigPath) {
        # Default to .claude/skills/github/copilot-synthesis.yml relative to repo root
        $repoRoot = git rev-parse --show-toplevel 2>$null
        if ($repoRoot) {
            $ConfigPath = Join-Path $repoRoot ".claude" "skills" "github" "copilot-synthesis.yml"
        }
    }

    if (-not $ConfigPath -or -not (Test-Path $ConfigPath)) {
        return $defaultConfig
    }

    # Parse YAML-like config
    try {
        $content = Get-Content $ConfigPath -Raw
        # Deep copy to avoid modifying defaultConfig (shallow Clone() would share nested refs)
        $config = $defaultConfig | ConvertTo-Json -Depth 10 | ConvertFrom-Json -AsHashtable

        # Extract maintainers (use non-greedy quantifier with boundary to prevent over-matching)
        if ($content -match 'maintainers:\s*((?:\s+-\s+\S+)+?)(?=\s*\w+:|$)') {
            $config.trusted_sources.maintainers = $Matches[1] -split "`n" | ForEach-Object {
                if ($_ -match '^\s+-\s+(\S+)') { $Matches[1] }
            } | Where-Object { $_ }
        }

        # Extract ai_agents (use non-greedy quantifier with boundary to prevent over-matching)
        if ($content -match 'ai_agents:\s*((?:\s+-\s+\S+)+?)(?=\s*\w+:|$)') {
            $config.trusted_sources.ai_agents = $Matches[1] -split "`n" | ForEach-Object {
                if ($_ -match '^\s+-\s+(\S+)') { $Matches[1] }
            } | Where-Object { $_ }
        }

        # Extract synthesis marker (allow comments/blank lines between synthesis: and marker:)
        # Use (?s) for single-line mode (. matches newlines) with non-greedy match
        if ($content -match '(?s)synthesis:.*?marker:\s*"([^"]+)"') {
            $config.synthesis.marker = $Matches[1]
        }

        return $config
    }
    catch {
        Write-Warning "Failed to parse config, using defaults: $_"
        return $defaultConfig
    }
}

#endregion

#region Context Extraction (script-specific logic)

function Get-MaintainerGuidance {
    <#
    .SYNOPSIS
        Extracts key decisions from maintainer comments.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,
        [string[]]$Maintainers
    )

    $maintainerComments = $Comments | Where-Object {
        $Maintainers -contains $_.user.login
    }

    if ($maintainerComments.Count -eq 0) {
        return $null
    }

    $guidance = @()
    foreach ($comment in $maintainerComments) {
        $lines = $comment.body -split "`n"
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            # Match numbered items (1. xxx) or bullet points (- xxx, * xxx)
            if ($trimmed -match '^\d+\.\s+(.+)$' -or $trimmed -match '^[-*]\s+(.+)$') {
                $item = $Matches[1]
                # Skip checkbox items or too short
                if ($item.Length -gt 10 -and $item -notmatch '^\[[ x]\]') {
                    $guidance += $item
                }
            }
        }
    }

    return $guidance
}

function Get-CodeRabbitPlan {
    <#
    .SYNOPSIS
        Extracts implementation plan from CodeRabbit comments.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,
        [hashtable]$Patterns
    )

    $rabbitComments = $Comments | Where-Object { $_.user.login -eq "coderabbitai" }
    if ($rabbitComments.Count -eq 0) { return $null }

    $plan = @{ Implementation = $null; RelatedIssues = @(); RelatedPRs = @() }

    # Use patterns from config
    $implPattern = [regex]::Escape($Patterns.implementation_plan)
    $issuesPattern = [regex]::Escape($Patterns.related_issues)
    $prsPattern = [regex]::Escape($Patterns.related_prs)

    foreach ($comment in $rabbitComments) {
        $body = $comment.body

        # Extract Implementation section using config pattern
        if ($body -match "$implPattern([\s\S]*?)(?=##|$)") {
            $plan.Implementation = $Matches[1].Trim()
        }

        # Extract related issues using config pattern (wrap in @() to ensure array)
        if ($body -match "$issuesPattern([\s\S]*?)(?=##|🔗|$)") {
            $plan.RelatedIssues = @([regex]::Matches($Matches[1], '#(\d+)') | ForEach-Object { "#$($_.Groups[1].Value)" })
        }

        # Extract related PRs using config pattern (wrap in @() to ensure array)
        if ($body -match "$prsPattern([\s\S]*?)(?=##|🔗|$)") {
            $plan.RelatedPRs = @([regex]::Matches($Matches[1], '#(\d+)') | ForEach-Object { "#$($_.Groups[1].Value)" })
        }
    }

    return $plan
}

function Get-AITriageInfo {
    <#
    .SYNOPSIS
        Extracts triage information from AI Triage comments.

    .DESCRIPTION
        Parses AI Triage comments to extract Priority and Category.
        Supports two formats:
        - Markdown table: | **Priority** | `P1` |
        - Plain text: Priority: P1

    .PARAMETER Comments
        An array of issue comment objects from the GitHub API.

    .PARAMETER TriageMarker
        The HTML comment marker used to identify AI Triage comments.

    .EXAMPLE
        $triageInfo = Get-AITriageInfo -Comments $issueComments -TriageMarker "<!-- AI-ISSUE-TRIAGE -->"
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,
        [string]$TriageMarker
    )

    $triageComment = $Comments | Where-Object {
        $_.body -match [regex]::Escape($TriageMarker)
    } | Select-Object -First 1

    if (-not $triageComment) { return $null }

    $triage = @{ Priority = $null; Category = $null }
    $body = $triageComment.body

    # Extract Priority and Category using shared logic (DRY)
    foreach ($field in @('Priority', 'Category')) {
        # Match Markdown table format: | **Priority** | `P1` |
        if ($body -match "\*\*$field\*\*[^``]*``([^``]+)``") {
            $triage[$field] = $Matches[1]
        }
        # Fallback to plain text format: Priority: P1
        elseif ($body -match "$field[:\s]+(\S+)") {
            $triage[$field] = $Matches[1]
        }
    }

    return $triage
}

#endregion

#region Synthesis Generation

function New-SynthesisComment {
    <#
    .SYNOPSIS
        Generates the synthesis comment body.
    #>
    [CmdletBinding()]
    param(
        [string]$Marker,
        [array]$MaintainerGuidance,
        [hashtable]$CodeRabbitPlan,
        [hashtable]$AITriage
    )

    $timestamp = Get-Date -AsUTC -Format "yyyy-MM-dd HH:mm:ss UTC"

    $body = @"
$Marker

@copilot Here is synthesized context for this issue:

"@

    # Maintainer Guidance section
    if ($MaintainerGuidance -and $MaintainerGuidance.Count -gt 0) {
        $body += "`n## Maintainer Guidance`n`n"
        foreach ($item in $MaintainerGuidance | Select-Object -First 10) {
            $body += "- $item`n"
        }
    }

    # AI Agent Recommendations section (include RelatedPRs in visibility check)
    $hasAIContent = ($CodeRabbitPlan -and ($CodeRabbitPlan.Implementation -or $CodeRabbitPlan.RelatedIssues.Count -gt 0 -or $CodeRabbitPlan.RelatedPRs.Count -gt 0)) -or $AITriage

    if ($hasAIContent) {
        $body += "`n## AI Agent Recommendations`n`n"

        if ($AITriage) {
            if ($AITriage.Priority) { $body += "- **Priority**: $($AITriage.Priority)`n" }
            if ($AITriage.Category) { $body += "- **Category**: $($AITriage.Category)`n" }
        }

        if ($CodeRabbitPlan) {
            if ($CodeRabbitPlan.RelatedIssues.Count -gt 0) {
                $body += "- **Related Issues**: $($CodeRabbitPlan.RelatedIssues -join ', ')`n"
            }
            if ($CodeRabbitPlan.RelatedPRs.Count -gt 0) {
                $body += "- **Related PRs**: $($CodeRabbitPlan.RelatedPRs -join ', ')`n"
            }
            if ($CodeRabbitPlan.Implementation) {
                $body += "`n**CodeRabbit Implementation Plan**:`n$($CodeRabbitPlan.Implementation)`n"
            }
        }
    }

    $body += "`n---`n*Generated: $timestamp*"
    return $body
}

function Test-HasSynthesizableContent {
    <#
    .SYNOPSIS
        Checks if there's any content worth synthesizing.

    .DESCRIPTION
        Evaluates extracted issue context to determine if a synthesis comment
        should be created. Returns true if any of the following exist:
        - Maintainer guidance from comments
        - AI triage information (priority, category)
        - CodeRabbit plan (implementation details, related issues/PRs)

        If no content exists, synthesis should be skipped to avoid empty comments.
        For this purpose, $null, empty strings (""), and whitespace-only strings
        are all treated as "no content" and do not cause synthesis to run.

    .PARAMETER MaintainerGuidance
        Array of guidance items extracted from maintainer comments.

    .PARAMETER CodeRabbitPlan
        Hashtable containing CodeRabbit analysis (Implementation, RelatedIssues, RelatedPRs).

    .PARAMETER AITriage
        Hashtable containing AI triage metadata (Priority, Category).

    .EXAMPLE
        $hasContent = Test-HasSynthesizableContent -MaintainerGuidance @() -CodeRabbitPlan $null -AITriage $null
        # Returns: $false (no content to synthesize)

    .EXAMPLE
        $triage = @{ Priority = "P1"; Category = "bug" }
        $hasContent = Test-HasSynthesizableContent -MaintainerGuidance @() -CodeRabbitPlan $null -AITriage $triage
        # Returns: $true (triage info exists)
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [array]$MaintainerGuidance,
        [hashtable]$CodeRabbitPlan,
        [hashtable]$AITriage
    )

    # Check maintainer guidance
    if ($MaintainerGuidance -and $MaintainerGuidance.Count -gt 0) {
        return $true
    }

    # Check AI triage (use IsNullOrWhiteSpace to properly handle empty strings)
    if ($AITriage -and (
            -not [string]::IsNullOrWhiteSpace([string]$AITriage.Priority) -or
            -not [string]::IsNullOrWhiteSpace([string]$AITriage.Category)
        )) {
        return $true
    }

    # Check CodeRabbit plan (add null checks before accessing Count for strict mode safety)
    if ($CodeRabbitPlan) {
        if ($CodeRabbitPlan.Implementation -or
            ($CodeRabbitPlan.RelatedIssues -and $CodeRabbitPlan.RelatedIssues.Count -gt 0) -or
            ($CodeRabbitPlan.RelatedPRs -and $CodeRabbitPlan.RelatedPRs.Count -gt 0)) {
            return $true
        }
    }

    return $false
}

function Find-ExistingSynthesis {
    <#
    .SYNOPSIS
        Finds existing synthesis comment by marker.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,
        [string]$Marker
    )

    return $Comments | Where-Object {
        $_.body -match [regex]::Escape($Marker)
    } | Select-Object -First 1
}

function Set-CopilotAssignee {
    <#
    .SYNOPSIS
        Assigns copilot-swe-agent to the issue.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,
        [Parameter(Mandatory)]
        [string]$Repo,
        [Parameter(Mandatory)]
        [int]$IssueNumber
    )

    $result = gh issue edit $IssueNumber --repo "$Owner/$Repo" --add-assignee "copilot-swe-agent" 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to assign copilot-swe-agent: $result"
        return $false
    }
    return $true
}

#endregion

#region Main Execution

# Authenticate
Assert-GhAuthenticated

# Resolve repository
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Host "Processing issue #$IssueNumber in $Owner/$Repo" -ForegroundColor Cyan

# Load configuration
$config = Get-SynthesisConfig -ConfigPath $ConfigPath

# Fetch issue details (for title display)
$issueData = gh api "repos/$Owner/$Repo/issues/$IssueNumber" 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($issueData -match "Not Found") { Write-ErrorAndExit "Issue #$IssueNumber not found in $Owner/$Repo" 2 }
    Write-ErrorAndExit "Failed to get issue: $issueData" 3
}
$issue = $issueData | ConvertFrom-Json
Write-Host "Issue: $($issue.title)" -ForegroundColor Gray

# Fetch comments using shared module function (wrap in @() to ensure array even if empty)
$comments = @(Get-IssueComments -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber)
Write-Host "Found $($comments.Count) comments" -ForegroundColor Gray

# Build trusted users list and filter using shared module function
$trustedUsers = @($config.trusted_sources.maintainers) + @($config.trusted_sources.ai_agents)
$trustedComments = @(Get-TrustedSourceComments -Comments $comments -TrustedUsers $trustedUsers)
Write-Host "Found $($trustedComments.Count) comments from trusted sources" -ForegroundColor Gray

# Extract context
$maintainerGuidance = Get-MaintainerGuidance -Comments $trustedComments -Maintainers $config.trusted_sources.maintainers
$codeRabbitPlan = Get-CodeRabbitPlan -Comments $trustedComments -Patterns $config.extraction_patterns.coderabbit
$aiTriage = Get-AITriageInfo -Comments $trustedComments -TriageMarker $config.extraction_patterns.ai_triage.marker

# Check if there's any content to synthesize
$hasContent = Test-HasSynthesizableContent `
    -MaintainerGuidance $maintainerGuidance `
    -CodeRabbitPlan $codeRabbitPlan `
    -AITriage $aiTriage

# Check for existing synthesis comment (idempotency)
$existingSynthesis = Find-ExistingSynthesis -Comments $comments -Marker $config.synthesis.marker

if ($PSCmdlet.ShouldProcess("Issue #$IssueNumber", "Post synthesis comment and assign Copilot")) {
    $response = $null
    $action = "Skipped"

    if ($hasContent) {
        # Generate synthesis only if there's content
        $synthesisBody = New-SynthesisComment `
            -Marker $config.synthesis.marker `
            -MaintainerGuidance $maintainerGuidance `
            -CodeRabbitPlan $codeRabbitPlan `
            -AITriage $aiTriage

        if ($existingSynthesis) {
            # Update existing using shared module function
            Write-Host "Updating existing synthesis comment (ID: $($existingSynthesis.id))" -ForegroundColor Yellow
            $response = Update-IssueComment -Owner $Owner -Repo $Repo -CommentId $existingSynthesis.id -Body $synthesisBody
            $action = "Updated"
        }
        else {
            # Create new using shared module function
            Write-Host "Creating new synthesis comment" -ForegroundColor Green
            $response = New-IssueComment -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber -Body $synthesisBody
            $action = "Created"
        }
        Write-Host "$action synthesis comment: $($response.html_url)" -ForegroundColor Green
    }
    else {
        Write-Host "No synthesizable content found - skipping synthesis comment" -ForegroundColor Yellow
    }

    # Assign Copilot (skip if -SkipAssignment is set - workflow handles it with COPILOT_GITHUB_TOKEN)
    $assigned = $false
    if (-not $SkipAssignment) {
        Write-Host "Assigning copilot-swe-agent..." -ForegroundColor Cyan
        $assigned = Set-CopilotAssignee -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber
        if ($assigned) { Write-Host "Assigned copilot-swe-agent to issue #$IssueNumber" -ForegroundColor Green }
    }
    else {
        Write-Host "Skipping assignment (handled by workflow with COPILOT_GITHUB_TOKEN)" -ForegroundColor Gray
    }

    # Output result
    [PSCustomObject]@{
        Success      = $true
        Action       = $action
        IssueNumber  = $IssueNumber
        CommentId    = & { if ($response) { $response.id } else { $null } }
        CommentUrl   = & { if ($response) { $response.html_url } else { $null } }
        Assigned     = $assigned
        Marker       = $config.synthesis.marker
    }

    # Explicit exit 0 to clear any lingering $LASTEXITCODE from failed native commands (e.g., gh issue edit)
    exit 0
}
else {
    # WhatIf mode
    if ($hasContent) {
        $synthesisBody = New-SynthesisComment `
            -Marker $config.synthesis.marker `
            -MaintainerGuidance $maintainerGuidance `
            -CodeRabbitPlan $codeRabbitPlan `
            -AITriage $aiTriage

        Write-Host "`n=== SYNTHESIS PREVIEW ===" -ForegroundColor Cyan
        Write-Host $synthesisBody
        Write-Host "=== END PREVIEW ===" -ForegroundColor Cyan

        if ($existingSynthesis) {
            Write-Host "`nWould UPDATE existing comment (ID: $($existingSynthesis.id))" -ForegroundColor Yellow
        }
        else {
            Write-Host "`nWould CREATE new synthesis comment" -ForegroundColor Green
        }
    }
    else {
        Write-Host "`nNo synthesizable content found - would SKIP synthesis comment" -ForegroundColor Yellow
    }
    Write-Host "Would ASSIGN copilot-swe-agent to issue #$IssueNumber" -ForegroundColor Cyan
}

#endregion
