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
    Path to copilot-synthesis.yml config file. Defaults to .github/copilot-synthesis.yml.

.PARAMETER WhatIf
    Preview the synthesis comment without posting or assigning.

.EXAMPLE
    .\Invoke-CopilotAssignment.ps1 -IssueNumber 123

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

    [string]$ConfigPath
)

# Import shared helpers
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

    if (-not $ConfigPath) {
        # Default to .github/copilot-synthesis.yml relative to repo root
        $repoRoot = git rev-parse --show-toplevel 2>$null
        if ($repoRoot) {
            $ConfigPath = Join-Path $repoRoot ".github" "copilot-synthesis.yml"
        }
    }

    if (-not $ConfigPath -or -not (Test-Path $ConfigPath)) {
        # Return default configuration
        return @{
            trusted_sources = @{
                maintainers = @("rjmurillo", "rjmurillo-bot")
                ai_agents   = @("coderabbitai", "github-actions")
            }
            extraction_patterns = @{
                coderabbit = @{
                    implementation_plan = "## Implementation"
                    related_issues      = "🔗 Similar Issues"
                    related_prs         = "🔗 Related PRs"
                }
                ai_triage = @{
                    marker   = "<!-- AI-ISSUE-TRIAGE -->"
                    priority = "Priority"
                    category = "Category"
                }
            }
            synthesis = @{
                marker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
            }
        }
    }

    # Parse YAML (PowerShell-YAML module or manual parsing)
    try {
        $content = Get-Content $ConfigPath -Raw
        # Simple YAML-like parsing for our flat structure
        $config = @{
            trusted_sources = @{
                maintainers = @()
                ai_agents   = @()
            }
            extraction_patterns = @{
                coderabbit = @{}
                ai_triage  = @{}
            }
            synthesis = @{
                marker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
            }
        }

        # Extract maintainers
        if ($content -match 'maintainers:\s*((?:\s+-\s+\S+)+)') {
            $maintainerLines = $Matches[1] -split "`n" | Where-Object { $_ -match '^\s+-\s+(\S+)' }
            $config.trusted_sources.maintainers = $maintainerLines | ForEach-Object {
                if ($_ -match '^\s+-\s+(\S+)') { $Matches[1] }
            }
        }

        # Extract ai_agents
        if ($content -match 'ai_agents:\s*((?:\s+-\s+\S+)+)') {
            $agentLines = $Matches[1] -split "`n" | Where-Object { $_ -match '^\s+-\s+(\S+)' }
            $config.trusted_sources.ai_agents = $agentLines | ForEach-Object {
                if ($_ -match '^\s+-\s+(\S+)') { $Matches[1] }
            }
        }

        # Extract synthesis marker
        if ($content -match 'marker:\s*"([^"]+)"') {
            $config.synthesis.marker = $Matches[1]
        }

        return $config
    }
    catch {
        Write-Warning "Failed to parse config, using defaults: $_"
        return Get-SynthesisConfig -ConfigPath $null
    }
}

#endregion

#region Issue Context Extraction

function Get-IssueComments {
    <#
    .SYNOPSIS
        Fetches all comments for an issue.
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

    $comments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$IssueNumber/comments"
    return $comments
}

function Get-IssueDetails {
    <#
    .SYNOPSIS
        Fetches issue details including body.
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

    $result = gh api "repos/$Owner/$Repo/issues/$IssueNumber" 2>&1

    if ($LASTEXITCODE -ne 0) {
        if ($result -match "Not Found") {
            Write-ErrorAndExit "Issue #$IssueNumber not found in $Owner/$Repo" 2
        }
        Write-ErrorAndExit "Failed to get issue: $result" 3
    }

    return $result | ConvertFrom-Json
}

function Get-TrustedSourceComments {
    <#
    .SYNOPSIS
        Filters comments to those from trusted sources.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,

        [hashtable]$Config
    )

    $trustedUsers = @()
    $trustedUsers += $Config.trusted_sources.maintainers
    $trustedUsers += $Config.trusted_sources.ai_agents

    $filtered = $Comments | Where-Object {
        $author = $_.user.login
        $trustedUsers -contains $author
    }

    return $filtered
}

function Get-MaintainerGuidance {
    <#
    .SYNOPSIS
        Extracts key decisions from maintainer comments.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,

        [hashtable]$Config
    )

    $maintainerComments = $Comments | Where-Object {
        $Config.trusted_sources.maintainers -contains $_.user.login
    }

    if ($maintainerComments.Count -eq 0) {
        return $null
    }

    $guidance = @()
    foreach ($comment in $maintainerComments) {
        # Extract bullet points and numbered items
        $body = $comment.body
        $lines = $body -split "`n"

        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            # Match numbered items (1. xxx) or bullet points (- xxx, * xxx)
            if ($trimmed -match '^[\d]+\.\s+(.+)$' -or $trimmed -match '^[-*]\s+(.+)$') {
                $item = $Matches[1]
                # Skip if it's a checkbox item or too short
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

        [hashtable]$Config
    )

    $rabbitComments = $Comments | Where-Object {
        $_.user.login -eq "coderabbitai"
    }

    if ($rabbitComments.Count -eq 0) {
        return $null
    }

    $plan = @{
        Implementation = $null
        RelatedIssues  = @()
        RelatedPRs     = @()
    }

    foreach ($comment in $rabbitComments) {
        $body = $comment.body

        # Extract Implementation section
        if ($body -match '## Implementation([\s\S]*?)(?=##|$)') {
            $plan.Implementation = $Matches[1].Trim()
        }

        # Extract related issues
        if ($body -match '🔗 Similar Issues([\s\S]*?)(?=##|🔗|$)') {
            $issueSection = $Matches[1]
            $issueMatches = [regex]::Matches($issueSection, '#(\d+)')
            $plan.RelatedIssues = $issueMatches | ForEach-Object { "#$($_.Groups[1].Value)" }
        }

        # Extract related PRs
        if ($body -match '🔗 Related PRs([\s\S]*?)(?=##|🔗|$)') {
            $prSection = $Matches[1]
            $prMatches = [regex]::Matches($prSection, '#(\d+)')
            $plan.RelatedPRs = $prMatches | ForEach-Object { "#$($_.Groups[1].Value)" }
        }
    }

    return $plan
}

function Get-AITriageInfo {
    <#
    .SYNOPSIS
        Extracts triage information from AI Triage comments.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,

        [hashtable]$Config
    )

    $triageMarker = $Config.extraction_patterns.ai_triage.marker

    $triageComment = $Comments | Where-Object {
        $_.body -match [regex]::Escape($triageMarker)
    } | Select-Object -First 1

    if (-not $triageComment) {
        return $null
    }

    $triage = @{
        Priority = $null
        Category = $null
    }

    $body = $triageComment.body

    # Extract Priority
    if ($body -match 'Priority[:\s]+(\S+)') {
        $triage.Priority = $Matches[1]
    }

    # Extract Category
    if ($body -match 'Category[:\s]+(\S+)') {
        $triage.Category = $Matches[1]
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
        [hashtable]$Config,

        [array]$MaintainerGuidance,

        [hashtable]$CodeRabbitPlan,

        [hashtable]$AITriage,

        [string]$IssueTitle
    )

    $marker = $Config.synthesis.marker
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss UTC"

    $body = @"
$marker

@copilot Here is synthesized context for this issue:

"@

    # Maintainer Guidance section
    if ($MaintainerGuidance -and $MaintainerGuidance.Count -gt 0) {
        $body += @"

## Maintainer Guidance

"@
        foreach ($item in $MaintainerGuidance | Select-Object -First 10) {
            $body += "- $item`n"
        }
    }

    # AI Agent Recommendations section
    $hasAIContent = ($CodeRabbitPlan -and ($CodeRabbitPlan.Implementation -or $CodeRabbitPlan.RelatedIssues.Count -gt 0)) -or $AITriage

    if ($hasAIContent) {
        $body += @"

## AI Agent Recommendations

"@

        if ($AITriage) {
            if ($AITriage.Priority) {
                $body += "- **Priority**: $($AITriage.Priority)`n"
            }
            if ($AITriage.Category) {
                $body += "- **Category**: $($AITriage.Category)`n"
            }
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

    # Add timestamp footer
    $body += @"

---
*Generated: $timestamp*
"@

    return $body
}

#endregion

#region Idempotent Operations

function Find-ExistingSynthesis {
    <#
    .SYNOPSIS
        Finds existing synthesis comment by marker.
    #>
    [CmdletBinding()]
    param(
        [array]$Comments,

        [hashtable]$Config
    )

    $marker = $Config.synthesis.marker

    $existing = $Comments | Where-Object {
        $_.body -match [regex]::Escape($marker)
    } | Select-Object -First 1

    return $existing
}

function Update-IssueComment {
    <#
    .SYNOPSIS
        Updates an existing issue comment.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [long]$CommentId,

        [Parameter(Mandatory)]
        [string]$Body
    )

    $result = gh api "repos/$Owner/$Repo/issues/comments/$CommentId" -X PATCH -f body=$Body 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorAndExit "Failed to update comment: $result" 3
    }

    return $result | ConvertFrom-Json
}

function New-IssueComment {
    <#
    .SYNOPSIS
        Creates a new issue comment.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$IssueNumber,

        [Parameter(Mandatory)]
        [string]$Body
    )

    $result = gh api "repos/$Owner/$Repo/issues/$IssueNumber/comments" -X POST -f body=$Body 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorAndExit "Failed to post comment: $result" 3
    }

    return $result | ConvertFrom-Json
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

# Fetch issue details
$issue = Get-IssueDetails -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber
Write-Host "Issue: $($issue.title)" -ForegroundColor Gray

# Fetch comments
$comments = Get-IssueComments -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber
Write-Host "Found $($comments.Count) comments" -ForegroundColor Gray

# Extract context from trusted sources
$trustedComments = Get-TrustedSourceComments -Comments $comments -Config $config
Write-Host "Found $($trustedComments.Count) comments from trusted sources" -ForegroundColor Gray

$maintainerGuidance = Get-MaintainerGuidance -Comments $trustedComments -Config $config
$codeRabbitPlan = Get-CodeRabbitPlan -Comments $trustedComments -Config $config
$aiTriage = Get-AITriageInfo -Comments $trustedComments -Config $config

# Generate synthesis
$synthesisBody = New-SynthesisComment `
    -Config $config `
    -MaintainerGuidance $maintainerGuidance `
    -CodeRabbitPlan $codeRabbitPlan `
    -AITriage $aiTriage `
    -IssueTitle $issue.title

# Check for existing synthesis comment (idempotency)
$existingSynthesis = Find-ExistingSynthesis -Comments $comments -Config $config

if ($PSCmdlet.ShouldProcess("Issue #$IssueNumber", "Post synthesis comment and assign Copilot")) {
    if ($existingSynthesis) {
        # Update existing comment
        Write-Host "Updating existing synthesis comment (ID: $($existingSynthesis.id))" -ForegroundColor Yellow
        $response = Update-IssueComment -Owner $Owner -Repo $Repo -CommentId $existingSynthesis.id -Body $synthesisBody
        $action = "Updated"
    }
    else {
        # Create new comment
        Write-Host "Creating new synthesis comment" -ForegroundColor Green
        $response = New-IssueComment -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber -Body $synthesisBody
        $action = "Created"
    }

    # Assign Copilot
    Write-Host "Assigning copilot-swe-agent..." -ForegroundColor Cyan
    $assigned = Set-CopilotAssignee -Owner $Owner -Repo $Repo -IssueNumber $IssueNumber

    # Output result
    $output = [PSCustomObject]@{
        Success      = $true
        Action       = $action
        IssueNumber  = $IssueNumber
        CommentId    = $response.id
        CommentUrl   = $response.html_url
        Assigned     = $assigned
        Marker       = $config.synthesis.marker
    }

    Write-Output $output
    Write-Host "$action synthesis comment: $($response.html_url)" -ForegroundColor Green
    if ($assigned) {
        Write-Host "Assigned copilot-swe-agent to issue #$IssueNumber" -ForegroundColor Green
    }
}
else {
    # WhatIf mode - show what would be done
    Write-Host "`n=== SYNTHESIS PREVIEW ===" -ForegroundColor Cyan
    Write-Host $synthesisBody
    Write-Host "=== END PREVIEW ===" -ForegroundColor Cyan

    if ($existingSynthesis) {
        Write-Host "`nWould UPDATE existing comment (ID: $($existingSynthesis.id))" -ForegroundColor Yellow
    }
    else {
        Write-Host "`nWould CREATE new synthesis comment" -ForegroundColor Green
    }
    Write-Host "Would ASSIGN copilot-swe-agent to issue #$IssueNumber" -ForegroundColor Cyan
}

#endregion
