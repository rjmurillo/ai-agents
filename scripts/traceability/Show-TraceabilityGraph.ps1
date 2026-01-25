<#
.SYNOPSIS
    Displays the traceability graph in various formats.

.DESCRIPTION
    Visualizes the traceability graph showing relationships between
    requirements, designs, and tasks. Supports multiple output formats
    for different use cases (terminal viewing, documentation, automation).

.PARAMETER SpecsPath
    Path to the specs directory. Default: ".agents/specs"

.PARAMETER Format
    Output format: "text", "mermaid", or "json".
    - text: Tree-like ASCII representation
    - mermaid: Mermaid.js graph definition
    - json: JSON graph with nodes and edges
    Default: "text"

.PARAMETER RootId
    Optional. Start the graph from a specific spec ID.
    Without this, shows the entire graph.

.PARAMETER Depth
    Maximum traversal depth from root. Default: unlimited (0)

.PARAMETER DryRun
    Validate parameters and exit without generating output.
    Useful for testing script accessibility.

.PARAMETER ShowOrphans
    Include orphaned specs in the output (specs with no relationships).

.PARAMETER NoCache
    Bypass cache and force full re-parse of all spec files.

.EXAMPLE
    .\Show-TraceabilityGraph.ps1

    Display the full graph in text format

.EXAMPLE
    .\Show-TraceabilityGraph.ps1 -Format mermaid

    Generate Mermaid.js diagram for documentation

.EXAMPLE
    .\Show-TraceabilityGraph.ps1 -RootId REQ-001 -Depth 2

    Show graph starting from REQ-001, 2 levels deep

.EXAMPLE
    .\Show-TraceabilityGraph.ps1 -Format json | ConvertFrom-Json

    Get graph data for programmatic use

.EXAMPLE
    .\Show-TraceabilityGraph.ps1 -DryRun

    Test that script works without generating output

.NOTES
    Exit codes:
    0 = Success
    1 = Error (invalid path, spec not found, etc.)

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$SpecsPath = ".agents/specs",

    [Parameter()]
    [ValidateSet("text", "mermaid", "json")]
    [string]$Format = "text",

    [Parameter()]
    [string]$RootId,

    [Parameter()]
    [int]$Depth = 0,

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$ShowOrphans,

    [Parameter()]
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

# Import caching module
$cacheModulePath = Join-Path $PSScriptRoot "TraceabilityCache.psm1"
if (Test-Path $cacheModulePath) {
    Import-Module $cacheModulePath -Force
    $CachingEnabled = -not $NoCache
}
else {
    $CachingEnabled = $false
}

#region Validation
function Test-SpecIdFormat {
    param([string]$Id)
    return $Id -match '^(REQ|DESIGN|TASK)-[A-Z0-9]+$'
}

if ($RootId -and -not (Test-SpecIdFormat -Id $RootId)) {
    Write-Error "Invalid RootId format: $RootId. Expected format: TYPE-ID (e.g., REQ-001)"
    exit 1
}
#endregion

#region YAML Parsing
function Get-YamlFrontMatter {
    param([string]$FilePath)

    # Try cache first if caching is enabled
    if ($CachingEnabled) {
        $fileHash = Get-TraceabilityFileHash -FilePath $FilePath
        if ($fileHash) {
            $cached = Get-CachedSpec -FilePath $FilePath -CurrentHash $fileHash
            if ($cached) {
                return $cached
            }
        }
    }

    $content = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
    if (-not $content) { return $null }

    if ($content -match '(?s)^---\r?\n(.+?)\r?\n---') {
        $yaml = $Matches[1]
        $result = @{
            type = ''
            id = ''
            status = ''
            related = @()
            filePath = $FilePath
        }

        if ($yaml -match '(?m)^type:\s*(.+)$') {
            $result.type = $Matches[1].Trim()
        }

        if ($yaml -match '(?m)^id:\s*(.+)$') {
            $result.id = $Matches[1].Trim()
        }

        if ($yaml -match '(?m)^status:\s*(.+)$') {
            $result.status = $Matches[1].Trim()
        }

        if ($yaml -match '(?s)related:\s*\r?\n((?:\s+-\s+.+\r?\n?)+)') {
            $relatedBlock = $Matches[1]
            $result.related = [regex]::Matches($relatedBlock, '-\s+([A-Z]+-[A-Z0-9]+)') |
                ForEach-Object { $_.Groups[1].Value }
        }

        # Cache the result if caching is enabled
        if ($CachingEnabled -and $fileHash) {
            Set-CachedSpec -FilePath $FilePath -FileHash $fileHash -Spec $result
        }

        return $result
    }

    return $null
}
#endregion

#region Spec Loading
function Get-AllSpecs {
    param([string]$BasePath)

    $specs = @{
        requirements = @{}
        designs = @{}
        tasks = @{}
        all = @{}
    }

    # Load requirements
    $reqPath = Join-Path $BasePath "requirements"
    if (Test-Path $reqPath) {
        Get-ChildItem -Path $reqPath -Filter "REQ-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.requirements[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    # Load designs
    $designPath = Join-Path $BasePath "design"
    if (Test-Path $designPath) {
        Get-ChildItem -Path $designPath -Filter "DESIGN-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.designs[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    # Load tasks
    $taskPath = Join-Path $BasePath "tasks"
    if (Test-Path $taskPath) {
        Get-ChildItem -Path $taskPath -Filter "TASK-*.md" | ForEach-Object {
            $spec = Get-YamlFrontMatter -FilePath $_.FullName
            if ($spec -and $spec.id) {
                $specs.tasks[$spec.id] = $spec
                $specs.all[$spec.id] = $spec
            }
        }
    }

    return $specs
}
#endregion

#region Graph Building
function Build-Graph {
    param([hashtable]$Specs)

    $graph = @{
        nodes = @{}
        edges = @()
        forwardRefs = @{}   # parent -> [children]
        backwardRefs = @{}  # child -> [parents]
    }

    # Add all nodes
    foreach ($id in $Specs.all.Keys) {
        $spec = $Specs.all[$id]
        $graph.nodes[$id] = @{
            id = $id
            type = $spec.type
            status = $spec.status
        }
        $graph.forwardRefs[$id] = @()
        $graph.backwardRefs[$id] = @()
    }

    # Build edges from related references
    foreach ($id in $Specs.all.Keys) {
        $spec = $Specs.all[$id]
        foreach ($relatedId in $spec.related) {
            if ($Specs.all.ContainsKey($relatedId)) {
                # Edge: current spec relates to related spec
                $graph.edges += @{
                    from = $id
                    to = $relatedId
                }
                $graph.forwardRefs[$relatedId] += $id
                $graph.backwardRefs[$id] += $relatedId
            }
        }
    }

    return $graph
}

function Get-Descendants {
    param(
        [hashtable]$Graph,
        [string]$RootId,
        [int]$MaxDepth,
        [int]$CurrentDepth = 0,
        [hashtable]$Visited = @{}
    )

    if ($Visited.ContainsKey($RootId)) {
        return @()
    }
    $Visited[$RootId] = $true

    $result = @($RootId)

    if ($MaxDepth -eq 0 -or $CurrentDepth -lt $MaxDepth) {
        foreach ($childId in $Graph.forwardRefs[$RootId]) {
            $result += Get-Descendants -Graph $Graph -RootId $childId -MaxDepth $MaxDepth -CurrentDepth ($CurrentDepth + 1) -Visited $Visited
        }
    }

    return $result
}

function Get-Ancestors {
    param(
        [hashtable]$Graph,
        [string]$RootId,
        [int]$MaxDepth,
        [int]$CurrentDepth = 0,
        [hashtable]$Visited = @{}
    )

    if ($Visited.ContainsKey($RootId)) {
        return @()
    }
    $Visited[$RootId] = $true

    $result = @($RootId)

    if ($MaxDepth -eq 0 -or $CurrentDepth -lt $MaxDepth) {
        foreach ($parentId in $Graph.backwardRefs[$RootId]) {
            $result += Get-Ancestors -Graph $Graph -RootId $parentId -MaxDepth $MaxDepth -CurrentDepth ($CurrentDepth + 1) -Visited $Visited
        }
    }

    return $result
}
#endregion

#region Output Formatting
function Format-TextGraph {
    param(
        [hashtable]$Graph,
        [hashtable]$Specs,
        [string]$RootId,
        [int]$MaxDepth,
        [switch]$ShowOrphans
    )

    $sb = [System.Text.StringBuilder]::new()

    function Write-Node {
        param(
            [string]$Id,
            [int]$Level,
            [hashtable]$Visited
        )

        if ($Visited.ContainsKey($Id)) {
            return
        }
        $Visited[$Id] = $true

        $indent = "  " * $Level
        $node = $Graph.nodes[$Id]
        $statusMarker = switch ($node.status) {
            'complete' { '[x]' }
            'done' { '[x]' }
            'implemented' { '[x]' }
            'approved' { '[~]' }
            'draft' { '[ ]' }
            default { '[ ]' }
        }

        [void]$sb.AppendLine("$indent$statusMarker $Id ($($node.type))")

        if ($MaxDepth -eq 0 -or $Level -lt $MaxDepth) {
            foreach ($childId in ($Graph.forwardRefs[$Id] | Sort-Object)) {
                Write-Node -Id $childId -Level ($Level + 1) -Visited $Visited
            }
        }
    }

    [void]$sb.AppendLine("Traceability Graph")
    [void]$sb.AppendLine("==================")
    [void]$sb.AppendLine("")

    $visited = @{}

    if ($RootId) {
        if (-not $Graph.nodes.ContainsKey($RootId)) {
            return "Error: Spec '$RootId' not found"
        }
        Write-Node -Id $RootId -Level 0 -Visited $visited
    }
    else {
        # Start from requirements (roots of the tree)
        [void]$sb.AppendLine("Requirements:")
        foreach ($reqId in ($Specs.requirements.Keys | Sort-Object)) {
            Write-Node -Id $reqId -Level 1 -Visited $visited
        }

        # Show orphaned designs (not referenced by any task)
        if ($ShowOrphans) {
            $orphanedDesigns = @()
            foreach ($designId in $Specs.designs.Keys) {
                if ($Graph.forwardRefs[$designId].Count -eq 0 -and -not $visited.ContainsKey($designId)) {
                    $orphanedDesigns += $designId
                }
            }
            if ($orphanedDesigns.Count -gt 0) {
                [void]$sb.AppendLine("")
                [void]$sb.AppendLine("Orphaned Designs:")
                foreach ($designId in ($orphanedDesigns | Sort-Object)) {
                    Write-Node -Id $designId -Level 1 -Visited $visited
                }
            }

            # Show orphaned tasks (not referencing any design)
            $orphanedTasks = @()
            foreach ($taskId in $Specs.tasks.Keys) {
                if ($Graph.backwardRefs[$taskId].Count -eq 0 -and -not $visited.ContainsKey($taskId)) {
                    $orphanedTasks += $taskId
                }
            }
            if ($orphanedTasks.Count -gt 0) {
                [void]$sb.AppendLine("")
                [void]$sb.AppendLine("Orphaned Tasks:")
                foreach ($taskId in ($orphanedTasks | Sort-Object)) {
                    Write-Node -Id $taskId -Level 1 -Visited $visited
                }
            }
        }
    }

    return $sb.ToString().TrimEnd()
}

function Format-MermaidGraph {
    param(
        [hashtable]$Graph,
        [hashtable]$Specs,
        [string]$RootId,
        [int]$MaxDepth
    )

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine('```mermaid')
    [void]$sb.AppendLine('graph TD')

    # Determine which nodes to include
    $nodesToInclude = @{}
    if ($RootId) {
        if (-not $Graph.nodes.ContainsKey($RootId)) {
            return "Error: Spec '$RootId' not found"
        }
        # Include root and all descendants
        $descendants = Get-Descendants -Graph $Graph -RootId $RootId -MaxDepth $MaxDepth
        # Also include ancestors
        $ancestors = Get-Ancestors -Graph $Graph -RootId $RootId -MaxDepth $MaxDepth
        foreach ($id in $descendants) { $nodesToInclude[$id] = $true }
        foreach ($id in $ancestors) { $nodesToInclude[$id] = $true }
    }
    else {
        foreach ($id in $Graph.nodes.Keys) {
            $nodesToInclude[$id] = $true
        }
    }

    # Add node definitions with styling
    foreach ($id in ($nodesToInclude.Keys | Sort-Object)) {
        $node = $Graph.nodes[$id]
        $shape = switch ($node.type) {
            'requirement' { "[$id]" }
            'design' { "([$id])" }
            'task' { "{$id}" }
            default { "[$id]" }
        }
        [void]$sb.AppendLine("    $($id -replace '-', '_')$shape")
    }

    [void]$sb.AppendLine("")

    # Add edges
    foreach ($edge in $Graph.edges) {
        $fromId = $edge.from -replace '-', '_'
        $toId = $edge.to -replace '-', '_'
        if ($nodesToInclude.ContainsKey($edge.from) -and $nodesToInclude.ContainsKey($edge.to)) {
            [void]$sb.AppendLine("    $fromId --> $toId")
        }
    }

    [void]$sb.AppendLine("")

    # Add styling classes
    [void]$sb.AppendLine("    classDef req fill:#e3f2fd,stroke:#1976d2,color:#000")
    [void]$sb.AppendLine("    classDef design fill:#fff3e0,stroke:#f57c00,color:#000")
    [void]$sb.AppendLine("    classDef task fill:#e8f5e9,stroke:#388e3c,color:#000")
    [void]$sb.AppendLine("    classDef complete fill:#c8e6c9,stroke:#2e7d32,color:#000")

    # Apply classes
    $reqNodes = @()
    $designNodes = @()
    $taskNodes = @()
    $completeNodes = @()

    foreach ($id in $nodesToInclude.Keys) {
        $node = $Graph.nodes[$id]
        $safeId = $id -replace '-', '_'
        if ($node.status -in @('complete', 'done', 'implemented')) {
            $completeNodes += $safeId
        }
        elseif ($node.type -eq 'requirement') {
            $reqNodes += $safeId
        }
        elseif ($node.type -eq 'design') {
            $designNodes += $safeId
        }
        elseif ($node.type -eq 'task') {
            $taskNodes += $safeId
        }
    }

    if ($reqNodes.Count -gt 0) {
        [void]$sb.AppendLine("    class $($reqNodes -join ',') req")
    }
    if ($designNodes.Count -gt 0) {
        [void]$sb.AppendLine("    class $($designNodes -join ',') design")
    }
    if ($taskNodes.Count -gt 0) {
        [void]$sb.AppendLine("    class $($taskNodes -join ',') task")
    }
    if ($completeNodes.Count -gt 0) {
        [void]$sb.AppendLine("    class $($completeNodes -join ',') complete")
    }

    [void]$sb.AppendLine('```')

    return $sb.ToString().TrimEnd()
}

function Format-JsonGraph {
    param(
        [hashtable]$Graph,
        [string]$RootId,
        [int]$MaxDepth
    )

    # Determine which nodes to include
    $nodesToInclude = @{}
    if ($RootId) {
        if (-not $Graph.nodes.ContainsKey($RootId)) {
            return '{"error": "Spec not found"}'
        }
        $descendants = Get-Descendants -Graph $Graph -RootId $RootId -MaxDepth $MaxDepth
        $ancestors = Get-Ancestors -Graph $Graph -RootId $RootId -MaxDepth $MaxDepth
        foreach ($id in $descendants) { $nodesToInclude[$id] = $true }
        foreach ($id in $ancestors) { $nodesToInclude[$id] = $true }
    }
    else {
        foreach ($id in $Graph.nodes.Keys) {
            $nodesToInclude[$id] = $true
        }
    }

    $nodes = @()
    foreach ($id in ($nodesToInclude.Keys | Sort-Object)) {
        $node = $Graph.nodes[$id]
        $nodes += @{
            id = $node.id
            type = $node.type
            status = $node.status
        }
    }

    $edges = @()
    foreach ($edge in $Graph.edges) {
        if ($nodesToInclude.ContainsKey($edge.from) -and $nodesToInclude.ContainsKey($edge.to)) {
            $edges += @{
                from = $edge.from
                to = $edge.to
            }
        }
    }

    $result = @{
        nodes = $nodes
        edges = $edges
        stats = @{
            nodeCount = $nodes.Count
            edgeCount = $edges.Count
        }
    }

    return $result | ConvertTo-Json -Depth 5
}
#endregion

#region Main
# Resolve specs path
$resolvedPath = Resolve-Path -Path $SpecsPath -ErrorAction SilentlyContinue
if (-not $resolvedPath) {
    Write-Error "Specs path not found: $SpecsPath"
    exit 1
}

# Path traversal protection
$repoRoot = try { git rev-parse --show-toplevel 2>$null } catch { $null }
if ($repoRoot) {
    $normalizedPath = [System.IO.Path]::GetFullPath($resolvedPath.Path)
    $allowedBase = [System.IO.Path]::GetFullPath($repoRoot)
    $isRelativePath = -not [System.IO.Path]::IsPathRooted($SpecsPath)

    if ($isRelativePath -and -not $normalizedPath.StartsWith($allowedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Error "Path traversal attempt detected: '$SpecsPath' is outside the repository root."
        exit 1
    }
}

# Dry run mode
if ($DryRun) {
    Write-Host "Dry-run test successful"
    exit 0
}

# Load all specs
$specs = Get-AllSpecs -BasePath $resolvedPath.Path

# Check if RootId exists
if ($RootId -and -not $specs.all.ContainsKey($RootId)) {
    Write-Error "Spec not found: $RootId"
    exit 1
}

# Build graph
$graph = Build-Graph -Specs $specs

# Format and output
$output = switch ($Format) {
    "text" {
        Format-TextGraph -Graph $graph -Specs $specs -RootId $RootId -MaxDepth $Depth -ShowOrphans:$ShowOrphans
    }
    "mermaid" {
        Format-MermaidGraph -Graph $graph -Specs $specs -RootId $RootId -MaxDepth $Depth
    }
    "json" {
        Format-JsonGraph -Graph $graph -RootId $RootId -MaxDepth $Depth
    }
}

Write-Output $output
exit 0
#endregion
