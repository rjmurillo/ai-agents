<#
.SYNOPSIS
    Updates the causal graph from episode data.

.DESCRIPTION
    Processes episode files and updates the causal graph with:
    - Decision nodes and their relationships
    - Event nodes and causal chains
    - Outcome tracking and success rates
    - Pattern extraction from repeated sequences

.PARAMETER EpisodePath
    Path to a specific episode file, or directory containing episodes.
    Defaults to .agents/memory/episodes/

.PARAMETER Since
    Only process episodes since this date.

.PARAMETER DryRun
    Show what would be updated without making changes.

.EXAMPLE
    ./Update-CausalGraph.ps1

.EXAMPLE
    ./Update-CausalGraph.ps1 -Since (Get-Date).AddDays(-7)

.EXAMPLE
    ./Update-CausalGraph.ps1 -EpisodePath ".agents/memory/episodes/episode-2026-01-01-session-126.json"

.NOTES
    Task: M-005 (Phase 2A Memory System)
    ADR: ADR-038 Reflexion Memory Schema
#>
[CmdletBinding()]
param(
    [string]$EpisodePath = (Join-Path $PSScriptRoot ".." ".." ".." ".." ".agents" "memory" "episodes"),

    [datetime]$Since,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import the ReflexionMemory module
$modulePath = Join-Path $PSScriptRoot "ReflexionMemory.psm1"
if (-not (Test-Path $modulePath)) {
    Write-Error "ReflexionMemory module not found at: $modulePath"
    exit 1
}
Import-Module $modulePath -Force

#region Helper Functions

function Get-EpisodeFile {
    <#
    .SYNOPSIS
        Gets episode files to process.
    #>
    param(
        [string]$Path,
        [Nullable[datetime]]$Since
    )

    if (Test-Path $Path -PathType Leaf) {
        return @(Get-Item $Path)
    }

    if (-not (Test-Path $Path)) {
        return @()
    }

    try {
        $files = Get-ChildItem -Path $Path -Filter "episode-*.json" -ErrorAction Stop
    }
    catch {
        Write-Warning "Failed to read episode files from '$Path': $($_.Exception.Message)"
        return @()
    }

    if ($Since) {
        $files = $files | Where-Object {
            try {
                $content = Get-Content $_.FullName -Raw | ConvertFrom-Json
                $episodeDate = [datetime]::Parse($content.timestamp)
                return $episodeDate -ge $Since
            }
            catch {
                Write-Warning "Skipping malformed episode file: $($_.FullName) - $($_.Exception.Message)"
                return $false
            }
        }
    }

    return $files
}

function Get-DecisionPattern {
    <#
    .SYNOPSIS
        Extracts decision patterns from an episode.
    #>
    param(
        [PSCustomObject]$Episode
    )

    $patterns = @()

    # Look for decision sequences that led to outcomes
    $successDecisions = $Episode.decisions | Where-Object { $_.outcome -eq "success" }
    $failureDecisions = $Episode.decisions | Where-Object { $_.outcome -eq "failure" }

    # Success patterns
    foreach ($decision in $successDecisions) {
        $trigger = $decision.context
        if (-not $trigger) { $trigger = "When $($decision.type) decision needed" }

        $patterns += @{
            name        = "$($decision.type) pattern"
            description = "Pattern from $($Episode.id)"
            trigger     = $trigger
            action      = $decision.chosen
            success     = $true
        }
    }

    # Failure patterns (anti-patterns)
    foreach ($decision in $failureDecisions) {
        $trigger = $decision.context
        if (-not $trigger) { $trigger = "When $($decision.type) decision needed" }

        $patterns += @{
            name        = "$($decision.type) anti-pattern"
            description = "Anti-pattern from $($Episode.id)"
            trigger     = $trigger
            action      = "AVOID: $($decision.chosen)"
            success     = $false
        }
    }

    return $patterns
}

function Build-CausalChain {
    <#
    .SYNOPSIS
        Builds causal chains from episode events.
    #>
    param(
        [PSCustomObject]$Episode
    )

    $chains = @()

    # Look for error -> recovery chains
    $errors = $Episode.events | Where-Object { $_.type -eq "error" }
    foreach ($error in $errors) {
        # Find recovery events that might follow
        $errorIndex = [array]::IndexOf($Episode.events, $error)
        $followingEvents = $Episode.events | Select-Object -Skip ($errorIndex + 1) -First 5

        $recovery = $followingEvents | Where-Object {
            $_.type -eq "milestone" -and $_.content -match 'fix|recover|resolve'
        } | Select-Object -First 1

        if ($recovery) {
            $chains += @{
                from_type = "error"
                from_label = $error.content
                to_type = "outcome"
                to_label = $recovery.content
                edge_type = "causes"
                weight = 0.8
            }
        }
    }

    # Look for decision -> outcome chains
    foreach ($decision in $Episode.decisions) {
        # Find events that might be caused by this decision
        $relatedEvents = $Episode.events | Where-Object {
            $_.content -match ($decision.chosen -split '\s+' | Select-Object -First 3 | Join-String -Separator '|')
        }

        foreach ($event in $relatedEvents) {
            $chains += @{
                from_type = "decision"
                from_label = $decision.chosen
                to_type = $event.type
                to_label = $event.content
                edge_type = "causes"
                weight = 0.6
            }
        }
    }

    return $chains
}

#endregion

#region Main Execution

Write-Host "Updating causal graph..." -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "[DRY RUN] No changes will be made" -ForegroundColor Yellow
}

# Get episode files
$episodeFiles = @(Get-EpisodeFile -Path $EpisodePath -Since $Since)

if ($episodeFiles.Count -eq 0) {
    Write-Host "No episode files found to process." -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($episodeFiles.Count) episode(s) to process" -ForegroundColor Gray

$stats = @{
    episodes_processed = 0
    nodes_added = 0
    edges_added = 0
    patterns_added = 0
}

foreach ($file in $episodeFiles) {
    Write-Host "`nProcessing: $($file.Name)" -ForegroundColor Cyan

    try {
        $content = Get-Content $file.FullName -Raw -Encoding UTF8 -ErrorAction Stop
        $episode = $content | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Write-Warning "Failed to process episode file '$($file.FullName)': $($_.Exception.Message)"
        continue
    }

    # Add decision nodes
    foreach ($decision in $episode.decisions) {
        $nodeLabel = "$($decision.type): $($decision.chosen)"

        if (-not $DryRun) {
            try {
                $node = Add-CausalNode -Type "decision" -Label $nodeLabel -EpisodeId $episode.id
                if ($node) { $stats.nodes_added++ }
            }
            catch {
                Write-Warning "Failed to add decision node '$nodeLabel': $($_.Exception.Message)"
            }
        }
        else {
            Write-Host "  [DRY] Would add node: $nodeLabel" -ForegroundColor Gray
        }
    }

    # Add event nodes
    foreach ($event in $episode.events) {
        $nodeLabel = "$($event.type): $($event.content)"

        if (-not $DryRun) {
            try {
                $node = Add-CausalNode -Type $event.type -Label $nodeLabel -EpisodeId $episode.id
                if ($node) { $stats.nodes_added++ }
            }
            catch {
                Write-Warning "Failed to add event node '$nodeLabel': $($_.Exception.Message)"
            }
        }
        else {
            Write-Host "  [DRY] Would add node: $nodeLabel" -ForegroundColor Gray
        }
    }

    # Add outcome node
    $outcomeLabel = "Outcome: $($episode.outcome) - $($episode.task)"
    if (-not $DryRun) {
        try {
            $outcomeNode = Add-CausalNode -Type "outcome" -Label $outcomeLabel -EpisodeId $episode.id
            if ($outcomeNode) { $stats.nodes_added++ }
        }
        catch {
            Write-Warning "Failed to add outcome node '$outcomeLabel': $($_.Exception.Message)"
        }
    }

    # Build and add causal chains
    $chains = Build-CausalChain -Episode $episode

    foreach ($chain in $chains) {
        if (-not $DryRun) {
            try {
                # First ensure nodes exist
                $fromNode = Add-CausalNode -Type $chain.from_type -Label $chain.from_label -EpisodeId $episode.id
                $toNode = Add-CausalNode -Type $chain.to_type -Label $chain.to_label -EpisodeId $episode.id

                if ($fromNode -and $toNode) {
                    $edge = Add-CausalEdge -SourceId $fromNode.id -TargetId $toNode.id -Type $chain.edge_type -Weight $chain.weight
                    if ($edge) { $stats.edges_added++ }
                }
            }
            catch {
                Write-Warning "Failed to add causal chain '$($chain.from_label) -> $($chain.to_label)': $($_.Exception.Message)"
            }
        }
        else {
            Write-Host "  [DRY] Would add edge: $($chain.from_label) --[$($chain.edge_type)]--> $($chain.to_label)" -ForegroundColor Gray
        }
    }

    # Extract and add patterns
    $patterns = Get-DecisionPattern -Episode $episode

    foreach ($pattern in $patterns) {
        if (-not $DryRun) {
            try {
                $successRate = if ($pattern.success) { 1.0 } else { 0.0 }
                $p = Add-Pattern -Name $pattern.name -Description $pattern.description -Trigger $pattern.trigger -Action $pattern.action -SuccessRate $successRate
                if ($p) { $stats.patterns_added++ }
            }
            catch {
                Write-Warning "Failed to add pattern '$($pattern.name)': $($_.Exception.Message)"
            }
        }
        else {
            Write-Host "  [DRY] Would add pattern: $($pattern.name)" -ForegroundColor Gray
        }
    }

    $stats.episodes_processed++
}

# Summary
Write-Host "`n" -NoNewline
Write-Host "═" * 50 -ForegroundColor Green
Write-Host "Causal Graph Update Complete" -ForegroundColor Green
Write-Host "═" * 50 -ForegroundColor Green
Write-Host "  Episodes processed: $($stats.episodes_processed)" -ForegroundColor Gray
Write-Host "  Nodes added:        $($stats.nodes_added)" -ForegroundColor Gray
Write-Host "  Edges added:        $($stats.edges_added)" -ForegroundColor Gray
Write-Host "  Patterns added:     $($stats.patterns_added)" -ForegroundColor Gray

if ($DryRun) {
    Write-Host "`n[DRY RUN] No actual changes were made" -ForegroundColor Yellow
}

# Return stats for pipeline usage
[PSCustomObject]$stats

#endregion
