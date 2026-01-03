<#
.SYNOPSIS
    Health check for all memory system tiers.

.DESCRIPTION
    Validates that all components of the four-tier memory system are operational.
    Returns structured status for each tier to enable agent decision-making.

    Tier 0: Working Memory - Always available (Claude context)
    Tier 1: Semantic Memory - Serena + Forgetful
    Tier 2: Episodic Memory - Episodes directory and module
    Tier 3: Causal Memory - Causal graph and patterns

.PARAMETER Format
    Output format: Json (default) or Table.

.PARAMETER Verbose
    Include detailed diagnostic information.

.EXAMPLE
    ./Test-MemoryHealth.ps1

.EXAMPLE
    ./Test-MemoryHealth.ps1 -Format Table

.NOTES
    Task: M-005 (Phase 2A Memory System)
    ADR: ADR-037, ADR-038
#>
[CmdletBinding()]
param(
    [ValidateSet('Json', 'Table')]
    [string]$Format = 'Json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Helper Functions

function Test-SerenaAvailable {
    <#
    .SYNOPSIS
        Check if Serena memories are accessible.
    #>
    $serenaPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".serena" "memories"

    if (-not (Test-Path $serenaPath)) {
        return @{
            available = $false
            message   = "Serena memories directory not found: $serenaPath"
            count     = 0
        }
    }

    try {
        $memories = Get-ChildItem -Path $serenaPath -Filter "*.md" -ErrorAction Stop
        $count = @($memories).Count

        return @{
            available = $true
            message   = "Serena available with $count memories"
            count     = $count
            path      = $serenaPath
        }
    }
    catch [System.UnauthorizedAccessException] {
        return @{
            available = $false
            message   = "Permission denied accessing Serena memories: $($_.Exception.Message)"
            count     = -1
            path      = $serenaPath
        }
    }
    catch {
        return @{
            available = $false
            message   = "Failed to enumerate Serena memories: $($_.Exception.Message)"
            count     = -1
            path      = $serenaPath
        }
    }
}

function Test-ForgetfulAvailable {
    <#
    .SYNOPSIS
        Check if Forgetful MCP is accessible.
    #>
    # Forgetful runs on localhost:8020 - check if reachable
    try {
        $uri = "http://localhost:8020/mcp"
        $response = Invoke-WebRequest -Uri $uri -Method Get -TimeoutSec 5 -ErrorAction Stop
        return @{
            available = $true
            message   = "Forgetful MCP reachable at $uri"
            endpoint  = $uri
        }
    }
    catch {
        return @{
            available = $false
            message   = "Forgetful MCP not reachable: $($_.Exception.Message)"
            endpoint  = "http://localhost:8020/mcp"
        }
    }
}

function Test-EpisodesAvailable {
    <#
    .SYNOPSIS
        Check if episodic memory storage is accessible.
    #>
    $episodesPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".agents" "memory" "episodes"

    if (-not (Test-Path $episodesPath)) {
        return @{
            available = $false
            message   = "Episodes directory not found: $episodesPath"
            count     = 0
        }
    }

    try {
        $episodes = Get-ChildItem -Path $episodesPath -Filter "episode-*.json" -ErrorAction Stop
        $count = @($episodes).Count

        return @{
            available = $true
            message   = "Episodes directory available with $count episodes"
            count     = $count
            path      = $episodesPath
        }
    }
    catch [System.UnauthorizedAccessException] {
        return @{
            available = $false
            message   = "Permission denied accessing episodes: $($_.Exception.Message)"
            count     = -1
            path      = $episodesPath
        }
    }
    catch {
        return @{
            available = $false
            message   = "Failed to enumerate episodes: $($_.Exception.Message)"
            count     = -1
            path      = $episodesPath
        }
    }
}

function Test-CausalGraphAvailable {
    <#
    .SYNOPSIS
        Check if causal memory storage is accessible.
    #>
    $causalityPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".agents" "memory" "causality"
    $graphPath = Join-Path $causalityPath "causal-graph.json"

    if (-not (Test-Path $causalityPath)) {
        return @{
            available = $false
            message   = "Causality directory not found: $causalityPath"
            nodes     = 0
            edges     = 0
            patterns  = 0
        }
    }

    if (-not (Test-Path $graphPath)) {
        return @{
            available = $true
            message   = "Causality directory exists but graph not initialized"
            nodes     = 0
            edges     = 0
            patterns  = 0
            path      = $causalityPath
        }
    }

    try {
        $graph = Get-Content $graphPath -Raw | ConvertFrom-Json
        $nodeCount = @($graph.nodes).Count
        $edgeCount = @($graph.edges).Count
        $patternCount = @($graph.patterns).Count

        return @{
            available = $true
            message   = "Causal graph loaded: $nodeCount nodes, $edgeCount edges, $patternCount patterns"
            nodes     = $nodeCount
            edges     = $edgeCount
            patterns  = $patternCount
            path      = $graphPath
        }
    }
    catch {
        return @{
            available = $false
            message   = "Failed to parse causal graph: $($_.Exception.Message)"
            nodes     = 0
            edges     = 0
            patterns  = 0
        }
    }
}

function Test-ModulesAvailable {
    <#
    .SYNOPSIS
        Check if required PowerShell modules are loadable.
    #>
    $modules = @(
        @{ Name = "MemoryRouter"; Path = Join-Path $PSScriptRoot "MemoryRouter.psm1" }
        @{ Name = "ReflexionMemory"; Path = Join-Path $PSScriptRoot "ReflexionMemory.psm1" }
    )

    $results = @()

    foreach ($module in $modules) {
        if (Test-Path $module.Path) {
            try {
                Import-Module $module.Path -Force -ErrorAction Stop
                $results += @{
                    name      = $module.Name
                    available = $true
                    message   = "Module loadable"
                    path      = $module.Path
                }
            }
            catch {
                $results += @{
                    name      = $module.Name
                    available = $false
                    message   = "Module failed to load: $($_.Exception.Message)"
                    path      = $module.Path
                }
            }
        }
        else {
            $results += @{
                name      = $module.Name
                available = $false
                message   = "Module file not found"
                path      = $module.Path
            }
        }
    }

    return $results
}

#endregion

#region Main Execution

$health = @{
    timestamp = (Get-Date).ToString("o")
    overall   = "healthy"
    tiers     = @{}
    modules   = @()
    recommendations = @()
}

# Tier 0: Working Memory (always available - Claude context)
$health.tiers["tier0_working"] = @{
    name      = "Working Memory"
    available = $true
    message   = "Claude context window (always available)"
}

# Tier 1: Semantic Memory
$serena = Test-SerenaAvailable
$forgetful = Test-ForgetfulAvailable

$health.tiers["tier1_semantic"] = @{
    name      = "Semantic Memory"
    available = $serena.available  # Serena is required, Forgetful is optional
    serena    = $serena
    forgetful = $forgetful
    message   = if ($serena.available -and $forgetful.available) {
        "Full semantic memory: Serena + Forgetful"
    }
    elseif ($serena.available) {
        "Degraded: Serena only (use -LexicalOnly)"
    }
    else {
        "UNAVAILABLE: Serena not accessible"
    }
}

if (-not $forgetful.available) {
    $health.recommendations += "Forgetful MCP unavailable - use -LexicalOnly flag for Search-Memory"
}

# Tier 2: Episodic Memory
$episodes = Test-EpisodesAvailable

$health.tiers["tier2_episodic"] = @{
    name      = "Episodic Memory"
    available = $episodes.available
    episodes  = $episodes
    message   = $episodes.message
}

if ($episodes.available -and $episodes.count -eq 0) {
    $health.recommendations += "No episodes found - run Extract-SessionEpisode.ps1 on completed sessions"
}

# Tier 3: Causal Memory
$causal = Test-CausalGraphAvailable

$health.tiers["tier3_causal"] = @{
    name      = "Causal Memory"
    available = $causal.available
    graph     = $causal
    message   = $causal.message
}

if ($causal.available -and $causal.nodes -eq 0) {
    $health.recommendations += "Causal graph empty - run Update-CausalGraph.ps1 after extracting episodes"
}

# Modules
$health.modules = Test-ModulesAvailable

$moduleIssues = $health.modules | Where-Object { -not $_.available }
if ($moduleIssues) {
    $health.overall = "degraded"
    foreach ($issue in $moduleIssues) {
        $health.recommendations += "Module $($issue.name) unavailable: $($issue.message)"
    }
}

# Overall status
$tierIssues = $health.tiers.Values | Where-Object { -not $_.available }
if ($tierIssues) {
    $criticalTiers = $tierIssues | Where-Object { $_.name -in @("Semantic Memory") }
    if ($criticalTiers) {
        $health.overall = "unhealthy"
    }
    else {
        $health.overall = "degraded"
    }
}

# Output
if ($Format -eq 'Table') {
    Write-Host "`nMemory System Health Check" -ForegroundColor Cyan
    Write-Host "=" * 50 -ForegroundColor Cyan
    Write-Host "Timestamp: $($health.timestamp)"
    Write-Host "Overall: " -NoNewline
    switch ($health.overall) {
        "healthy" { Write-Host "HEALTHY" -ForegroundColor Green }
        "degraded" { Write-Host "DEGRADED" -ForegroundColor Yellow }
        "unhealthy" { Write-Host "UNHEALTHY" -ForegroundColor Red }
    }

    Write-Host "`nTiers:" -ForegroundColor White
    foreach ($tier in $health.tiers.GetEnumerator() | Sort-Object Key) {
        $status = if ($tier.Value.available) { "[OK]" } else { "[X]" }
        $color = if ($tier.Value.available) { "Green" } else { "Red" }
        Write-Host "  $status $($tier.Value.name): $($tier.Value.message)" -ForegroundColor $color
    }

    Write-Host "`nModules:" -ForegroundColor White
    foreach ($module in $health.modules) {
        $status = if ($module.available) { "[OK]" } else { "[X]" }
        $color = if ($module.available) { "Green" } else { "Red" }
        Write-Host "  $status $($module.name): $($module.message)" -ForegroundColor $color
    }

    if ($health.recommendations.Count -gt 0) {
        Write-Host "`nRecommendations:" -ForegroundColor Yellow
        foreach ($rec in $health.recommendations) {
            Write-Host "  - $rec" -ForegroundColor Yellow
        }
    }
}
else {
    $health | ConvertTo-Json -Depth 5
}

#endregion
