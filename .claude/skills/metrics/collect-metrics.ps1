<#
.SYNOPSIS
    Agent Metrics Collection Utility for PowerShell

.DESCRIPTION
    Collects and reports metrics on agent usage from git history.
    Implements the 8 key metrics defined in docs/agent-metrics.md.

.PARAMETER Since
    Number of days to analyze (default: 30)

.PARAMETER Output
    Output format: Json, Markdown, Summary (default: Summary)

.PARAMETER RepoPath
    Repository path (default: current directory)

.EXAMPLE
    .\collect-metrics.ps1
    Collects metrics for the last 30 days and displays summary

.EXAMPLE
    .\collect-metrics.ps1 -Since 90 -Output Markdown
    Collects 90 days of metrics and outputs as markdown

.EXAMPLE
    .\collect-metrics.ps1 -Output Json | ConvertFrom-Json
    Outputs metrics as JSON for programmatic use

.NOTES
  EXIT CODES:
  0  - Success: Metrics collected and output successfully
  1  - Error: Path not found or not a git repository

  See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter()]
    [int]$Since = 30,

    [Parameter()]
    [ValidateSet("Json", "Markdown", "Summary")]
    [string]$Output = "Summary",

    [Parameter()]
    [string]$RepoPath = "."
)

# Agent patterns to detect in commit messages
$AgentPatterns = @(
    '(?i)\b(orchestrator|analyst|architect|implementer|security|qa|devops|critic|planner|explainer|task-generator|high-level-advisor|independent-thinker|memory|skillbook|retrospective|roadmap|pr-comment-responder)\b\s*(agent)?'
    '(?i)reviewed\s+by:?\s*(security|architect|analyst|qa|implementer)'
    '(?i)agent:\s*(\w+)'
    '(?i)\[(\w+)-agent\]'
)

# Infrastructure file patterns
$InfrastructurePatterns = @(
    '^\.github/workflows/.*\.(yml|yaml)$'
    '^\.github/actions/'
    '^\.githooks/'
    '^build/'
    '^scripts/'
    'Dockerfile'
    'docker-compose'
    '\.tf$'
    '\.tfvars$'
    '\.env'
    '\.agents/'
)

# Commit type patterns (conventional commits)
$CommitTypePatterns = @{
    'feature'  = '^feat(\(.+\))?:'
    'fix'      = '^fix(\(.+\))?:'
    'docs'     = '^docs(\(.+\))?:'
    'refactor' = '^refactor(\(.+\))?:'
    'test'     = '^test(\(.+\))?:'
    'chore'    = '^chore(\(.+\))?:'
    'ci'       = '^ci(\(.+\))?:'
    'perf'     = '^perf(\(.+\))?:'
    'style'    = '^style(\(.+\))?:'
}

function Get-CommitsSince {
    param(
        [int]$Days,
        [string]$Path
    )

    $sinceDate = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
    $logFormat = "%H|%s|%an|%ae|%ad"

    $output = git -C $Path log --since="$sinceDate" --format="$logFormat" --date=short 2>$null

    if (-not $output) {
        return @()
    }

    $commits = @()
    foreach ($line in $output -split "`n") {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $parts = $line -split '\|', 5
        if ($parts.Count -ge 5) {
            $commits += [PSCustomObject]@{
                Hash    = $parts[0]
                Subject = $parts[1]
                Author  = $parts[2]
                Email   = $parts[3]
                Date    = $parts[4]
            }
        }
    }

    return $commits
}

function Get-CommitFiles {
    param(
        [string]$CommitHash,
        [string]$Path
    )

    $output = git -C $Path diff-tree --no-commit-id --name-only -r $CommitHash 2>$null
    return $output -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

function Find-AgentsInText {
    param([string]$Text)

    $agents = @{}

    foreach ($pattern in $AgentPatterns) {
        $matches = [regex]::Matches($Text, $pattern, 'IgnoreCase')
        foreach ($match in $matches) {
            $agent = $match.Groups[1].Value.ToLower()
            if ($agent -and $agent -ne 'agent') {
                $agents[$agent] = $true
            }
        }
    }

    return $agents.Keys
}

function Get-CommitType {
    param([string]$Subject)

    foreach ($type in $CommitTypePatterns.Keys) {
        if ($Subject -match $CommitTypePatterns[$type]) {
            return $type
        }
    }

    return 'other'
}

function Test-InfrastructureFile {
    param([string]$FilePath)

    foreach ($pattern in $InfrastructurePatterns) {
        if ($FilePath -match $pattern) {
            return $true
        }
    }

    return $false
}

function Get-Metrics {
    param(
        [string]$Path,
        [int]$Days
    )

    $commits = Get-CommitsSince -Days $Days -Path $Path

    # Initialize collectors
    $agentInvocations = @{}
    $commitsWithAgents = 0
    $commitsByType = @{}
    $commitsWithAgentByType = @{}
    $infrastructureCommits = 0
    $infrastructureWithSecurity = 0

    foreach ($commit in $commits) {
        $files = Get-CommitFiles -CommitHash $commit.Hash -Path $Path
        $subject = $commit.Subject
        $commitType = Get-CommitType -Subject $subject

        # Detect agents
        $agents = Find-AgentsInText -Text $subject

        # Track agent invocations
        foreach ($agent in $agents) {
            if (-not $agentInvocations.ContainsKey($agent)) {
                $agentInvocations[$agent] = 0
            }
            $agentInvocations[$agent]++
        }

        # Track coverage
        if (-not $commitsByType.ContainsKey($commitType)) {
            $commitsByType[$commitType] = 0
            $commitsWithAgentByType[$commitType] = 0
        }
        $commitsByType[$commitType]++

        if ($agents.Count -gt 0) {
            $commitsWithAgents++
            $commitsWithAgentByType[$commitType]++
        }

        # Infrastructure review tracking
        $hasInfra = $files | Where-Object { Test-InfrastructureFile -FilePath $_ } | Select-Object -First 1
        if ($hasInfra) {
            $infrastructureCommits++
            if ($agents -contains 'security') {
                $infrastructureWithSecurity++
            }
        }
    }

    $totalCommits = $commits.Count
    $totalInvocations = ($agentInvocations.Values | Measure-Object -Sum).Sum

    # Build metrics object
    $metrics = @{
        period = @{
            days         = $Days
            start_date   = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
            end_date     = (Get-Date).ToString("yyyy-MM-dd")
            total_commits = $totalCommits
        }

        metric_1_invocation_rate = @{
            agents           = @{}
            total_invocations = if ($totalInvocations) { $totalInvocations } else { 0 }
        }

        metric_2_coverage = @{
            total_commits      = $totalCommits
            commits_with_agent = $commitsWithAgents
            coverage_rate      = if ($totalCommits -gt 0) { [Math]::Round($commitsWithAgents / $totalCommits * 100, 1) } else { 0 }
            target            = 50
            by_type           = @{}
            status            = if ($totalCommits -gt 0 -and ($commitsWithAgents / $totalCommits * 100) -ge 50) { "on_track" } else { "behind" }
        }

        metric_4_infrastructure_review = @{
            infrastructure_commits = $infrastructureCommits
            with_security_review   = $infrastructureWithSecurity
            review_rate           = if ($infrastructureCommits -gt 0) { [Math]::Round($infrastructureWithSecurity / $infrastructureCommits * 100, 1) } else { 0 }
            target                = 100
            status                = if ($infrastructureCommits -eq 0 -or $infrastructureWithSecurity / $infrastructureCommits -ge 1) { "on_track" } else { "behind" }
        }

        metric_5_distribution = @{}
    }

    # Populate agent invocations
    foreach ($agent in $agentInvocations.Keys | Sort-Object { $agentInvocations[$_] } -Descending) {
        $count = $agentInvocations[$agent]
        $rate = if ($totalInvocations -gt 0) { [Math]::Round($count / $totalInvocations * 100, 1) } else { 0 }
        $metrics.metric_1_invocation_rate.agents[$agent] = @{
            count = $count
            rate  = $rate
        }
        $metrics.metric_5_distribution[$agent] = $rate
    }

    # Populate coverage by type
    foreach ($type in $commitsByType.Keys) {
        $total = $commitsByType[$type]
        $withAgent = $commitsWithAgentByType[$type]
        $metrics.metric_2_coverage.by_type[$type] = @{
            total      = $total
            with_agent = $withAgent
            rate       = if ($total -gt 0) { [Math]::Round($withAgent / $total * 100, 1) } else { 0 }
        }
    }

    return $metrics
}

function Format-Summary {
    param($Metrics)

    $lines = @(
        "=" * 60
        "AGENT METRICS SUMMARY"
        "=" * 60
        ""
        "Period: $($Metrics.period.start_date) to $($Metrics.period.end_date)"
        "Total Commits Analyzed: $($Metrics.period.total_commits)"
        ""
        "-" * 40
        "METRIC 1: INVOCATION RATE BY AGENT"
        "-" * 40
    )

    $agents = $Metrics.metric_1_invocation_rate.agents
    if ($agents.Count -gt 0) {
        foreach ($agent in $agents.Keys) {
            $data = $agents[$agent]
            $lines += "  {0,-20} {1,4} ({2,5:F1}%)" -f $agent, $data.count, $data.rate
        }
    } else {
        $lines += "  No agent invocations detected"
    }

    $lines += @(
        ""
        "-" * 40
        "METRIC 2: AGENT COVERAGE"
        "-" * 40
    )

    $coverage = $Metrics.metric_2_coverage
    $lines += "  Overall: $($coverage.coverage_rate)% (Target: $($coverage.target)%)"
    $lines += "  Status: $($coverage.status.ToUpper())"

    $lines += @(
        ""
        "-" * 40
        "METRIC 4: INFRASTRUCTURE REVIEW RATE"
        "-" * 40
    )

    $infra = $Metrics.metric_4_infrastructure_review
    $lines += "  Infrastructure Commits: $($infra.infrastructure_commits)"
    $lines += "  With Security Review: $($infra.with_security_review)"
    $lines += "  Review Rate: $($infra.review_rate)% (Target: $($infra.target)%)"
    $lines += "  Status: $($infra.status.ToUpper())"

    $lines += @(
        ""
        "=" * 60
    )

    return $lines -join "`n"
}

function Format-Markdown {
    param($Metrics)

    $lines = @(
        "# Agent Metrics Report"
        ""
        "## Report Period"
        ""
        "**From**: $($Metrics.period.start_date)"
        "**To**: $($Metrics.period.end_date)"
        "**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
        ""
        "---"
        ""
        "## Executive Summary"
        ""
        "| Metric | Current | Target | Status |"
        "|--------|---------|--------|--------|"
    )

    $coverage = $Metrics.metric_2_coverage
    $infra = $Metrics.metric_4_infrastructure_review

    $coverageStatus = if ($coverage.status -eq 'on_track') { 'On Track' } else { 'Behind' }
    $infraStatus = if ($infra.status -eq 'on_track') { 'On Track' } else { 'Behind' }

    $lines += "| Agent Coverage | $($coverage.coverage_rate)% | $($coverage.target)% | $coverageStatus |"
    $lines += "| Infrastructure Review | $($infra.review_rate)% | $($infra.target)% | $infraStatus |"

    $lines += @(
        ""
        "---"
        ""
        "## Metric 1: Invocation Rate by Agent"
        ""
        "| Agent | Invocations | Rate |"
        "|-------|-------------|------|"
    )

    $agents = $Metrics.metric_1_invocation_rate.agents
    if ($agents.Count -gt 0) {
        foreach ($agent in $agents.Keys) {
            $data = $agents[$agent]
            $lines += "| $agent | $($data.count) | $($data.rate)% |"
        }
    } else {
        $lines += "| *No agents detected* | 0 | 0% |"
    }

    $lines += @(
        ""
        "**Total Invocations**: $($Metrics.metric_1_invocation_rate.total_invocations)"
        ""
        "---"
        ""
        "## Metric 2: Agent Coverage by Commit Type"
        ""
        "| Commit Type | Total | With Agent | Coverage |"
        "|-------------|-------|------------|----------|"
    )

    foreach ($type in $Metrics.metric_2_coverage.by_type.Keys) {
        $data = $Metrics.metric_2_coverage.by_type[$type]
        $lines += "| $type | $($data.total) | $($data.with_agent) | $($data.rate)% |"
    }

    $lines += @(
        ""
        "---"
        ""
        "## Metric 4: Infrastructure Review Rate"
        ""
        "- **Infrastructure Commits**: $($infra.infrastructure_commits)"
        "- **With Security Review**: $($infra.with_security_review)"
        "- **Review Rate**: $($infra.review_rate)%"
        "- **Target**: $($infra.target)%"
        ""
        "---"
        ""
        "*Generated by collect-metrics.ps1*"
    )

    return $lines -join "`n"
}

# Main execution
$resolvedPath = Resolve-Path $RepoPath -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Path not found: $RepoPath"
    exit 1
}

if (-not (Test-Path (Join-Path $resolvedPath ".git"))) {
    Write-Error "$resolvedPath is not a git repository"
    exit 1
}

$metrics = Get-Metrics -Path $resolvedPath -Days $Since

switch ($Output) {
    "Json" {
        $metrics | ConvertTo-Json -Depth 10
    }
    "Markdown" {
        Format-Markdown -Metrics $metrics
    }
    default {
        Format-Summary -Metrics $metrics
    }
}
