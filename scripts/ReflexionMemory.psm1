<#
.SYNOPSIS
    Reflexion Memory module for episodic replay and causal reasoning.

.DESCRIPTION
    Implements ADR-038 Reflexion Memory Schema with:
    - Episodic memory storage and retrieval
    - Causal graph management
    - Pattern extraction and what-if analysis

    Tier Architecture:
    - Tier 0: Working memory (context window - managed by Claude)
    - Tier 1: Semantic memory (Serena + Forgetful - ADR-037)
    - Tier 2: Episodic memory (this module)
    - Tier 3: Causal memory (this module)

.NOTES
    Task: M-005 (Phase 2A Memory System)
    ADR: ADR-038 Reflexion Memory Schema
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Configuration

$script:EpisodesPath = Join-Path $PSScriptRoot ".." ".agents" "episodes"
$script:CausalityPath = Join-Path $PSScriptRoot ".." ".agents" "causality"
$script:CausalGraphFile = Join-Path $script:CausalityPath "causal-graph.json"

#endregion

#region Private Functions

function Get-CausalGraph {
    <#
    .SYNOPSIS
        Loads the causal graph from disk.
    #>
    [CmdletBinding()]
    param()

    if (-not (Test-Path $script:CausalGraphFile)) {
        return @{
            version  = "1.0"
            updated  = (Get-Date).ToString("o")
            nodes    = @()
            edges    = @()
            patterns = @()
        }
    }

    $content = Get-Content -Path $script:CausalGraphFile -Raw -Encoding UTF8
    return $content | ConvertFrom-Json -AsHashtable
}

function Save-CausalGraph {
    <#
    .SYNOPSIS
        Saves the causal graph to disk.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Graph
    )

    $Graph.updated = (Get-Date).ToString("o")

    $json = $Graph | ConvertTo-Json -Depth 10
    Set-Content -Path $script:CausalGraphFile -Value $json -Encoding UTF8
}

function Get-NextNodeId {
    <#
    .SYNOPSIS
        Gets the next available node ID.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Graph
    )

    if (-not $Graph.nodes -or $Graph.nodes.Count -eq 0) {
        return "n001"
    }

    $ids = @()
    foreach ($node in $Graph.nodes) {
        $idStr = if ($node -is [hashtable]) { $node['id'] } else { $node.id }
        if ($idStr -match '^n(\d+)$') {
            $ids += [int]$Matches[1]
        }
    }

    if ($ids.Count -eq 0) {
        return "n001"
    }

    $maxId = ($ids | Measure-Object -Maximum).Maximum
    return "n{0:D3}" -f ([int]$maxId + 1)
}

function Get-NextPatternId {
    <#
    .SYNOPSIS
        Gets the next available pattern ID.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Graph
    )

    if (-not $Graph.patterns -or $Graph.patterns.Count -eq 0) {
        return "p001"
    }

    $ids = @()
    foreach ($pattern in $Graph.patterns) {
        $idStr = if ($pattern -is [hashtable]) { $pattern['id'] } else { $pattern.id }
        if ($idStr -match '^p(\d+)$') {
            $ids += [int]$Matches[1]
        }
    }

    if ($ids.Count -eq 0) {
        return "p001"
    }

    $maxId = ($ids | Measure-Object -Maximum).Maximum
    return "p{0:D3}" -f ([int]$maxId + 1)
}

#endregion

#region Episode Functions

function Get-Episode {
    <#
    .SYNOPSIS
        Retrieves an episode by session ID.

    .PARAMETER SessionId
        The session identifier (e.g., "2026-01-01-session-126").

    .EXAMPLE
        Get-Episode -SessionId "2026-01-01-session-126"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SessionId
    )

    $episodeFile = Join-Path $script:EpisodesPath "episode-$SessionId.json"

    if (-not (Test-Path $episodeFile)) {
        return $null
    }

    $content = Get-Content -Path $episodeFile -Raw -Encoding UTF8
    return $content | ConvertFrom-Json
}

function Get-Episodes {
    <#
    .SYNOPSIS
        Retrieves episodes matching criteria.

    .PARAMETER Outcome
        Filter by outcome: success, partial, failure.

    .PARAMETER Since
        Filter episodes since this date.

    .PARAMETER MaxResults
        Maximum number of episodes to return.

    .EXAMPLE
        Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)
    #>
    [CmdletBinding()]
    param(
        [ValidateSet("success", "partial", "failure")]
        [string]$Outcome,

        [datetime]$Since,

        [ValidateRange(1, 100)]
        [int]$MaxResults = 20
    )

    $episodes = @()

    if (-not (Test-Path $script:EpisodesPath)) {
        return $episodes
    }

    $files = Get-ChildItem -Path $script:EpisodesPath -Filter "episode-*.json" -ErrorAction SilentlyContinue

    foreach ($file in $files) {
        $content = Get-Content -Path $file.FullName -Raw -Encoding UTF8
        $episode = $content | ConvertFrom-Json

        # Apply filters
        if ($Outcome -and $episode.outcome -ne $Outcome) {
            continue
        }

        if ($Since) {
            $episodeDate = [datetime]::Parse($episode.timestamp)
            if ($episodeDate -lt $Since) {
                continue
            }
        }

        $episodes += $episode

        if ($episodes.Count -ge $MaxResults) {
            break
        }
    }

    return $episodes | Sort-Object -Property timestamp -Descending
}

function New-Episode {
    <#
    .SYNOPSIS
        Creates a new episode from structured data.

    .PARAMETER SessionId
        The source session identifier.

    .PARAMETER Task
        High-level task description.

    .PARAMETER Outcome
        Episode outcome: success, partial, failure.

    .PARAMETER Decisions
        Array of decision objects.

    .PARAMETER Events
        Array of event objects.

    .PARAMETER Lessons
        Array of lesson strings.

    .PARAMETER Metrics
        Metrics hashtable.

    .EXAMPLE
        New-Episode -SessionId "2026-01-01-session-126" -Task "Implement feature" -Outcome "success"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SessionId,

        [Parameter(Mandatory)]
        [string]$Task,

        [Parameter(Mandatory)]
        [ValidateSet("success", "partial", "failure")]
        [string]$Outcome,

        [array]$Decisions = @(),

        [array]$Events = @(),

        [array]$Lessons = @(),

        [hashtable]$Metrics = @{}
    )

    $episode = @{
        id        = "episode-$SessionId"
        session   = $SessionId
        timestamp = (Get-Date).ToString("o")
        outcome   = $Outcome
        task      = $Task
        decisions = $Decisions
        events    = $Events
        metrics   = $Metrics
        lessons   = $Lessons
    }

    # Ensure directory exists
    if (-not (Test-Path $script:EpisodesPath)) {
        New-Item -Path $script:EpisodesPath -ItemType Directory -Force | Out-Null
    }

    $episodeFile = Join-Path $script:EpisodesPath "episode-$SessionId.json"
    $json = $episode | ConvertTo-Json -Depth 10
    Set-Content -Path $episodeFile -Value $json -Encoding UTF8

    return $episode
}

function Get-DecisionSequence {
    <#
    .SYNOPSIS
        Retrieves the decision sequence from an episode.

    .PARAMETER EpisodeId
        The episode identifier.

    .EXAMPLE
        Get-DecisionSequence -EpisodeId "episode-2026-01-01-126"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$EpisodeId
    )

    $sessionId = $EpisodeId -replace '^episode-', ''
    $episode = Get-Episode -SessionId $sessionId

    if (-not $episode) {
        return @()
    }

    return $episode.decisions | Sort-Object -Property timestamp
}

#endregion

#region Causal Graph Functions

function Add-CausalNode {
    <#
    .SYNOPSIS
        Adds a node to the causal graph.

    .PARAMETER Type
        Node type: decision, event, outcome, pattern, error.

    .PARAMETER Label
        Human-readable label.

    .PARAMETER EpisodeId
        Source episode ID.

    .EXAMPLE
        Add-CausalNode -Type "decision" -Label "Choose Serena-first routing" -EpisodeId "episode-2026-01-01-126"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateSet("decision", "event", "outcome", "pattern", "error")]
        [string]$Type,

        [Parameter(Mandatory)]
        [string]$Label,

        [string]$EpisodeId
    )

    $graph = Get-CausalGraph

    # Check if node already exists (by label)
    $existing = $graph.nodes | Where-Object { $_.label -eq $Label }

    if ($existing) {
        # Update existing node
        $existing.frequency++
        if ($EpisodeId -and $existing.episodes -notcontains $EpisodeId) {
            $existing.episodes += $EpisodeId
        }
        Save-CausalGraph -Graph $graph
        return $existing
    }

    # Create new node
    $node = @{
        id           = Get-NextNodeId -Graph $graph
        type         = $Type
        label        = $Label
        episodes     = if ($EpisodeId) { @($EpisodeId) } else { @() }
        frequency    = 1
        success_rate = 1.0
    }

    $graph.nodes += $node
    Save-CausalGraph -Graph $graph

    return $node
}

function Add-CausalEdge {
    <#
    .SYNOPSIS
        Adds an edge to the causal graph.

    .PARAMETER SourceId
        Source node ID.

    .PARAMETER TargetId
        Target node ID.

    .PARAMETER Type
        Edge type: causes, enables, prevents, correlates.

    .PARAMETER Weight
        Confidence weight (0-1).

    .EXAMPLE
        Add-CausalEdge -SourceId "n001" -TargetId "n002" -Type "causes" -Weight 0.9
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SourceId,

        [Parameter(Mandatory)]
        [string]$TargetId,

        [Parameter(Mandatory)]
        [ValidateSet("causes", "enables", "prevents", "correlates")]
        [string]$Type,

        [ValidateRange(0, 1)]
        [double]$Weight = 0.5
    )

    $graph = Get-CausalGraph

    # Check if edge already exists
    $existing = $graph.edges | Where-Object {
        $_.source -eq $SourceId -and $_.target -eq $TargetId -and $_.type -eq $Type
    }

    if ($existing) {
        # Update existing edge
        $existing.evidence_count++
        # Adjust weight based on evidence
        $existing.weight = ($existing.weight * ($existing.evidence_count - 1) + $Weight) / $existing.evidence_count
        Save-CausalGraph -Graph $graph
        return $existing
    }

    # Create new edge
    $edge = @{
        source         = $SourceId
        target         = $TargetId
        type           = $Type
        weight         = $Weight
        evidence_count = 1
    }

    $graph.edges += $edge
    Save-CausalGraph -Graph $graph

    return $edge
}

function Get-CausalPath {
    <#
    .SYNOPSIS
        Finds causal path between two nodes.

    .PARAMETER FromLabel
        Source node label.

    .PARAMETER ToLabel
        Target node label.

    .PARAMETER MaxDepth
        Maximum path depth to search.

    .EXAMPLE
        Get-CausalPath -FromLabel "Choose routing" -ToLabel "Performance target met"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FromLabel,

        [Parameter(Mandatory)]
        [string]$ToLabel,

        [ValidateRange(1, 10)]
        [int]$MaxDepth = 5
    )

    $graph = Get-CausalGraph

    $fromNode = $graph.nodes | Where-Object { $_.label -like "*$FromLabel*" } | Select-Object -First 1
    $toNode = $graph.nodes | Where-Object { $_.label -like "*$ToLabel*" } | Select-Object -First 1

    if (-not $fromNode -or -not $toNode) {
        return @{
            found = $false
            path  = @()
            error = "Node not found"
        }
    }

    # BFS to find path
    $queue = [System.Collections.ArrayList]@(@{ node = $fromNode.id; path = @($fromNode.id) })
    $visited = @{ $fromNode.id = $true }

    while ($queue.Count -gt 0) {
        $current = $queue[0]
        $queue.RemoveAt(0)

        if ($current.node -eq $toNode.id) {
            # Found path - resolve node labels
            $pathNodes = $current.path | ForEach-Object {
                $nodeId = $_
                $graph.nodes | Where-Object { $_.id -eq $nodeId }
            }
            return @{
                found = $true
                path  = $pathNodes
                depth = $current.path.Count - 1
            }
        }

        if ($current.path.Count -ge $MaxDepth) {
            continue
        }

        # Find outgoing edges
        $outEdges = $graph.edges | Where-Object { $_.source -eq $current.node }

        foreach ($edge in $outEdges) {
            if (-not $visited[$edge.target]) {
                $visited[$edge.target] = $true
                [void]$queue.Add(@{
                    node = $edge.target
                    path = $current.path + @($edge.target)
                })
            }
        }
    }

    return @{
        found = $false
        path  = @()
        error = "No path found within depth $MaxDepth"
    }
}

#endregion

#region Pattern Functions

function Add-Pattern {
    <#
    .SYNOPSIS
        Adds a pattern to the causal graph.

    .PARAMETER Name
        Pattern name.

    .PARAMETER Description
        Pattern description.

    .PARAMETER Trigger
        Condition that triggers this pattern.

    .PARAMETER Action
        Recommended action.

    .PARAMETER SuccessRate
        Success rate (0-1).

    .EXAMPLE
        Add-Pattern -Name "Lint bypass" -Trigger "Unrelated lint errors" -Action "Use --no-verify with justification"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [string]$Description,

        [Parameter(Mandatory)]
        [string]$Trigger,

        [Parameter(Mandatory)]
        [string]$Action,

        [ValidateRange(0, 1)]
        [double]$SuccessRate = 1.0
    )

    $graph = Get-CausalGraph

    # Check if pattern already exists
    $existing = $graph.patterns | Where-Object { $_.name -eq $Name }

    if ($existing) {
        $existing.occurrences++
        $existing.last_used = (Get-Date).ToString("o")
        # Update success rate with running average
        $existing.success_rate = ($existing.success_rate * ($existing.occurrences - 1) + $SuccessRate) / $existing.occurrences
        Save-CausalGraph -Graph $graph
        return $existing
    }

    # Create new pattern
    $pattern = @{
        id           = Get-NextPatternId -Graph $graph
        name         = $Name
        description  = $Description
        trigger      = $Trigger
        action       = $Action
        success_rate = $SuccessRate
        occurrences  = 1
        last_used    = (Get-Date).ToString("o")
    }

    $graph.patterns += $pattern
    Save-CausalGraph -Graph $graph

    return $pattern
}

function Get-Patterns {
    <#
    .SYNOPSIS
        Retrieves patterns matching criteria.

    .PARAMETER MinSuccessRate
        Minimum success rate filter.

    .PARAMETER MinOccurrences
        Minimum occurrences filter.

    .EXAMPLE
        Get-Patterns -MinSuccessRate 0.7 -MinOccurrences 3
    #>
    [CmdletBinding()]
    param(
        [ValidateRange(0, 1)]
        [double]$MinSuccessRate = 0,

        [ValidateRange(1, 1000)]
        [int]$MinOccurrences = 1
    )

    $graph = Get-CausalGraph

    return $graph.patterns | Where-Object {
        $_.success_rate -ge $MinSuccessRate -and $_.occurrences -ge $MinOccurrences
    } | Sort-Object -Property success_rate -Descending
}

function Get-AntiPatterns {
    <#
    .SYNOPSIS
        Retrieves anti-patterns (low success rate patterns).

    .PARAMETER MaxSuccessRate
        Maximum success rate to qualify as anti-pattern.

    .EXAMPLE
        Get-AntiPatterns -MaxSuccessRate 0.3
    #>
    [CmdletBinding()]
    param(
        [ValidateRange(0, 1)]
        [double]$MaxSuccessRate = 0.3
    )

    $graph = Get-CausalGraph

    return $graph.patterns | Where-Object {
        $_.success_rate -le $MaxSuccessRate -and $_.occurrences -ge 2
    } | Sort-Object -Property success_rate
}

#endregion

#region Status Functions

function Get-ReflexionMemoryStatus {
    <#
    .SYNOPSIS
        Gets the status of the reflexion memory system.

    .EXAMPLE
        Get-ReflexionMemoryStatus
    #>
    [CmdletBinding()]
    param()

    $graph = Get-CausalGraph

    $episodeCount = 0
    if (Test-Path $script:EpisodesPath) {
        $episodeCount = (Get-ChildItem -Path $script:EpisodesPath -Filter "episode-*.json" -ErrorAction SilentlyContinue).Count
    }

    return [PSCustomObject]@{
        Episodes      = @{
            Path  = $script:EpisodesPath
            Count = $episodeCount
        }
        CausalGraph   = @{
            Path     = $script:CausalGraphFile
            Version  = $graph.version
            Updated  = $graph.updated
            Nodes    = $graph.nodes.Count
            Edges    = $graph.edges.Count
            Patterns = $graph.patterns.Count
        }
        Configuration = @{
            EpisodesPath  = $script:EpisodesPath
            CausalityPath = $script:CausalityPath
        }
    }
}

#endregion

#region Export

Export-ModuleMember -Function @(
    # Episode functions
    'Get-Episode',
    'Get-Episodes',
    'New-Episode',
    'Get-DecisionSequence',
    # Causal graph functions
    'Add-CausalNode',
    'Add-CausalEdge',
    'Get-CausalPath',
    # Pattern functions
    'Add-Pattern',
    'Get-Patterns',
    'Get-AntiPatterns',
    # Status
    'Get-ReflexionMemoryStatus'
)

#endregion
