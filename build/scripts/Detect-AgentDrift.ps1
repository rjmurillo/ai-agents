<#
.SYNOPSIS
    Detects semantic drift between Claude agents and VS Code/Copilot agents.

.DESCRIPTION
    Compares Claude agents (src/claude/*.md) with corresponding VS Code agents
    (src/vs-code-agents/*.agent.md) to detect significant content differences.

    Claude agents have unique content and are NOT generated from templates.
    This script detects when Claude agents diverge significantly from the
    shared content that VS Code/Copilot agents are generated from.

    The script ignores known platform-specific differences:
    - YAML frontmatter format differences
    - Tool invocation syntax (mcp__cloudmcp-manager__* vs cloudmcp-manager/*)
    - Claude Code Tools section (Claude-specific)
    - Platform-specific tool references

    The script focuses on detecting drift in:
    - Core Identity / Core Mission sections
    - Key Responsibilities
    - Review criteria / checklists
    - Templates and output formats

.PARAMETER ClaudePath
    Path to Claude agents directory. Defaults to src/claude.

.PARAMETER VSCodePath
    Path to VS Code agents directory. Defaults to src/vs-code-agents.

.PARAMETER SimilarityThreshold
    Minimum similarity percentage (0-100) to consider content aligned.
    Below this threshold, drift is reported. Defaults to 80.

.PARAMETER OutputFormat
    Output format: Text (default), JSON, or Markdown.

.EXAMPLE
    .\Detect-AgentDrift.ps1
    # Run drift detection with defaults

.EXAMPLE
    .\Detect-AgentDrift.ps1 -SimilarityThreshold 90
    # Require 90% similarity to pass

.EXAMPLE
    .\Detect-AgentDrift.ps1 -OutputFormat JSON
    # Output results as JSON

.NOTES
    Exit codes:
    0 - No significant drift detected
    1 - Drift detected (similarity below threshold)
    2 - Error during execution
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$ClaudePath,

    [Parameter()]
    [string]$VSCodePath,

    [Parameter()]
    [ValidateRange(0, 100)]
    [int]$SimilarityThreshold = 80,

    [Parameter()]
    [ValidateSet("Text", "JSON", "Markdown")]
    [string]$OutputFormat = "Text"
)

$ErrorActionPreference = "Stop"

#region Path Resolution

# Script is in build/scripts/, so go up two levels to repo root
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ClaudePath) {
    $ClaudePath = Join-Path $RepoRoot "src" "claude"
}
if (-not $VSCodePath) {
    $VSCodePath = Join-Path $RepoRoot "src" "vs-code-agents"
}

# Validate paths exist
if (-not (Test-Path $ClaudePath)) {
    Write-Error "Claude agents path not found: $ClaudePath"
    exit 2
}
if (-not (Test-Path $VSCodePath)) {
    Write-Error "VS Code agents path not found: $VSCodePath"
    exit 2
}

#endregion

#region Helper Functions

function Remove-YamlFrontmatter {
    <#
    .SYNOPSIS
        Removes YAML frontmatter from markdown content.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Content
    )

    if ($Content -match '^---\r?\n[\s\S]*?\r?\n---\r?\n([\s\S]*)$') {
        return $Matches[1]
    }
    return $Content
}

function Get-MarkdownSections {
    <#
    .SYNOPSIS
        Extracts sections from markdown content based on ## headers.
    .OUTPUTS
        Hashtable with section name as key and content as value.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Content
    )

    $sections = @{}
    $currentSection = "preamble"
    $currentContent = [System.Collections.ArrayList]::new()

    $lines = $Content -split '\r?\n'

    foreach ($line in $lines) {
        if ($line -match '^##\s+(.+)$') {
            # Save previous section
            if ($currentContent.Count -gt 0) {
                $sections[$currentSection] = ($currentContent -join "`n").Trim()
            }
            # Start new section
            $currentSection = $Matches[1].Trim()
            $currentContent = [System.Collections.ArrayList]::new()
        }
        else {
            [void]$currentContent.Add($line)
        }
    }

    # Save final section
    if ($currentContent.Count -gt 0) {
        $sections[$currentSection] = ($currentContent -join "`n").Trim()
    }

    return $sections
}

function Normalize-ContentForComparison {
    <#
    .SYNOPSIS
        Normalizes content by removing platform-specific syntax.
    .DESCRIPTION
        Removes known platform differences to enable semantic comparison:
        - Memory protocol syntax variations
        - Tool invocation syntax differences
        - Whitespace normalization
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Content
    )

    $result = $Content

    # Normalize memory protocol syntax
    # Claude: mcp__cloudmcp-manager__memory-search_nodes
    # VS Code: cloudmcp-manager/memory-search_nodes
    $result = $result -replace 'mcp__cloudmcp-manager__', 'cloudmcp-manager/'
    $result = $result -replace 'mcp__cognitionai-deepwiki__', 'cognitionai/deepwiki/'
    $result = $result -replace 'mcp__context7__', 'context7/'
    $result = $result -replace 'mcp__deepwiki__', 'deepwiki/'

    # Normalize handoff syntax
    # Claude: Task(...) syntax is not used, but /agent or similar might appear
    # VS Code: #runSubagent with subagentType=X
    $result = $result -replace '`#runSubagent with subagentType=(\w+)`', '`invoke $1`'
    $result = $result -replace '`/agent\s+(\w+)`', '`invoke $1`'

    # Remove code block language identifiers for comparison (normalize to generic)
    $result = $result -replace '```(bash|powershell|text|markdown|python)', '```'

    # Normalize whitespace
    $result = $result -replace '\r\n', "`n"
    $result = $result -replace '[ \t]+$', '' -split "`n" | ForEach-Object { $_.TrimEnd() }
    $result = ($result -join "`n").Trim()

    # Collapse multiple blank lines to single
    $result = $result -replace '\n{3,}', "`n`n"

    return $result
}

function Get-SectionSimilarity {
    <#
    .SYNOPSIS
        Calculates similarity percentage between two text sections.
    .DESCRIPTION
        Uses Jaccard similarity on word tokens for comparison.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Text1,

        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Text2
    )

    if ([string]::IsNullOrWhiteSpace($Text1) -and [string]::IsNullOrWhiteSpace($Text2)) {
        return 100.0
    }
    if ([string]::IsNullOrWhiteSpace($Text1) -or [string]::IsNullOrWhiteSpace($Text2)) {
        return 0.0
    }

    # Tokenize into words
    $words1 = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    $words2 = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )

    # Extract words (alphanumeric sequences)
    foreach ($word in ($Text1 -split '\W+' | Where-Object { $_.Length -gt 2 })) {
        [void]$words1.Add($word)
    }
    foreach ($word in ($Text2 -split '\W+' | Where-Object { $_.Length -gt 2 })) {
        [void]$words2.Add($word)
    }

    if ($words1.Count -eq 0 -and $words2.Count -eq 0) {
        return 100.0
    }

    # Calculate Jaccard similarity: |intersection| / |union|
    # Must use same comparer for intersection/union operations
    $intersection = [System.Collections.Generic.HashSet[string]]::new($words1, [StringComparer]::OrdinalIgnoreCase)
    $intersection.IntersectWith($words2)

    $union = [System.Collections.Generic.HashSet[string]]::new($words1, [StringComparer]::OrdinalIgnoreCase)
    $union.UnionWith($words2)

    if ($union.Count -eq 0) {
        return 100.0
    }

    return [Math]::Round(($intersection.Count / $union.Count) * 100, 1)
}

function Compare-AgentContent {
    <#
    .SYNOPSIS
        Compares two agent files and returns drift analysis.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ClaudeContent,

        [Parameter(Mandatory)]
        [string]$VSCodeContent,

        [Parameter(Mandatory)]
        [string]$AgentName,

        [Parameter()]
        [int]$Threshold = 80
    )

    # Remove frontmatter
    $claudeBody = Remove-YamlFrontmatter -Content $ClaudeContent
    $vscodeBody = Remove-YamlFrontmatter -Content $VSCodeContent

    # Get sections
    $claudeSections = Get-MarkdownSections -Content $claudeBody
    $vscodeSections = Get-MarkdownSections -Content $vscodeBody

    # Sections to compare (semantic content)
    $sectionsToCompare = @(
        "Core Identity"
        "Core Mission"
        "Key Responsibilities"
        "Constraints"
        "Handoff Options"
        "Execution Mindset"
        "Memory Protocol"
        "Memory Protocol (cloudmcp-manager)"
        "Impact Analysis Mode"
        "Analysis Types"
        "ADR Template"
        "ADR Format"
        "Review Phases"
        "Architecture Review Process"
        "Handoff Protocol"
        "Analysis Document Format"
    )

    # Sections to skip (platform-specific)
    $sectionsToSkip = @(
        "Claude Code Tools"
        "Research Tools"
        "Tools for Ideation Research"
    )

    $sectionResults = @()
    $totalSimilarity = 0.0
    $comparedCount = 0

    foreach ($section in $sectionsToCompare) {
        $claudeSection = $claudeSections[$section]
        $vscodeSection = $vscodeSections[$section]

        # Skip if neither has this section
        if (-not $claudeSection -and -not $vscodeSection) {
            continue
        }

        # Normalize for comparison
        $claudeNormalized = if ($claudeSection) {
            Normalize-ContentForComparison -Content $claudeSection
        } else { "" }
        $vscodeNormalized = if ($vscodeSection) {
            Normalize-ContentForComparison -Content $vscodeSection
        } else { "" }

        $similarity = Get-SectionSimilarity -Text1 $claudeNormalized -Text2 $vscodeNormalized

        $sectionResults += [PSCustomObject]@{
            Section       = $section
            Similarity    = $similarity
            ClaudeHas     = [bool]$claudeSection
            VSCodeHas     = [bool]$vscodeSection
            Status        = if ($similarity -ge $Threshold) { "OK" } else { "DRIFT" }
        }

        $totalSimilarity += $similarity
        $comparedCount++
    }

    # Calculate overall similarity
    $overallSimilarity = if ($comparedCount -gt 0) {
        [Math]::Round($totalSimilarity / $comparedCount, 1)
    } else {
        100.0
    }

    return [PSCustomObject]@{
        AgentName         = $AgentName
        OverallSimilarity = $overallSimilarity
        Status            = if ($overallSimilarity -ge $Threshold) { "OK" } else { "DRIFT DETECTED" }
        Sections          = $sectionResults
        DriftingSections  = @($sectionResults | Where-Object { $_.Status -eq "DRIFT" } | ForEach-Object { $_.Section })
    }
}

#endregion

#region Main Logic

$startTime = Get-Date

# Output header
if ($OutputFormat -eq "Text") {
    Write-Host ""
    Write-Host "=== Agent Drift Detection ===" -ForegroundColor Cyan
    Write-Host "Comparing: Claude vs VS Code/Copilot"
    Write-Host "Similarity Threshold: $SimilarityThreshold%"
    Write-Host ""
}

# Find all Claude agents
$claudeAgents = Get-ChildItem -Path $ClaudePath -Filter "*.md" -ErrorAction SilentlyContinue
$results = @()

foreach ($claudeFile in $claudeAgents) {
    $agentName = $claudeFile.BaseName

    # Find corresponding VS Code agent
    $vscodeFile = Join-Path $VSCodePath "$agentName.agent.md"

    if (-not (Test-Path $vscodeFile)) {
        Write-Verbose "No VS Code counterpart for: $agentName"
        $results += [PSCustomObject]@{
            AgentName         = $agentName
            OverallSimilarity = $null
            Status            = "NO COUNTERPART"
            Sections          = @()
            DriftingSections  = @()
        }
        continue
    }

    # Read content
    $claudeContent = Get-Content -Path $claudeFile.FullName -Raw -Encoding UTF8
    $vscodeContent = Get-Content -Path $vscodeFile -Raw -Encoding UTF8

    # Compare
    $comparison = Compare-AgentContent `
        -ClaudeContent $claudeContent `
        -VSCodeContent $vscodeContent `
        -AgentName $agentName `
        -Threshold $SimilarityThreshold

    $results += $comparison
}

# Calculate summary
$driftCount = @($results | Where-Object { $_.Status -eq "DRIFT DETECTED" }).Count
$noCounterpartCount = @($results | Where-Object { $_.Status -eq "NO COUNTERPART" }).Count
$okCount = @($results | Where-Object { $_.Status -eq "OK" }).Count

$duration = (Get-Date) - $startTime

#endregion

#region Output

switch ($OutputFormat) {
    "Text" {
        foreach ($result in $results | Sort-Object AgentName) {
            $color = switch ($result.Status) {
                "OK" { "Green" }
                "DRIFT DETECTED" { "Red" }
                "NO COUNTERPART" { "Yellow" }
                default { "White" }
            }

            if ($null -ne $result.OverallSimilarity) {
                Write-Host "$($result.AgentName): $($result.Status) ($($result.OverallSimilarity)% similar)" -ForegroundColor $color
            }
            else {
                Write-Host "$($result.AgentName): $($result.Status)" -ForegroundColor $color
            }

            if ($result.DriftingSections.Count -gt 0) {
                foreach ($section in $result.DriftingSections) {
                    Write-Host "  - Section `"$section`" differs" -ForegroundColor Red
                }
            }
        }

        Write-Host ""
        Write-Host "=== Summary ===" -ForegroundColor Cyan
        Write-Host "Duration: $($duration.TotalSeconds.ToString('F2'))s"
        Write-Host "Agents compared: $($results.Count)"
        Write-Host "OK: $okCount" -ForegroundColor Green
        Write-Host "Drift detected: $driftCount" -ForegroundColor $(if ($driftCount -gt 0) { "Red" } else { "Green" })
        Write-Host "No counterpart: $noCounterpartCount" -ForegroundColor $(if ($noCounterpartCount -gt 0) { "Yellow" } else { "Green" })
        Write-Host ""

        if ($driftCount -gt 0) {
            Write-Host "RESULT: $driftCount agent(s) with drift detected" -ForegroundColor Red
        }
        else {
            Write-Host "RESULT: No significant drift detected" -ForegroundColor Green
        }
    }

    "JSON" {
        $output = [PSCustomObject]@{
            Timestamp           = (Get-Date).ToString("o")
            Duration            = $duration.TotalSeconds
            Threshold           = $SimilarityThreshold
            Summary             = [PSCustomObject]@{
                TotalAgents     = $results.Count
                OK              = $okCount
                DriftDetected   = $driftCount
                NoCounterpart   = $noCounterpartCount
            }
            Results             = $results
        }
        $output | ConvertTo-Json -Depth 5
    }

    "Markdown" {
        Write-Output "# Agent Drift Detection Report"
        Write-Output ""
        Write-Output "**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        Write-Output "**Threshold**: $SimilarityThreshold%"
        Write-Output "**Duration**: $($duration.TotalSeconds.ToString('F2'))s"
        Write-Output ""
        Write-Output "## Summary"
        Write-Output ""
        Write-Output "| Metric | Count |"
        Write-Output "|--------|-------|"
        Write-Output "| Agents Compared | $($results.Count) |"
        Write-Output "| OK | $okCount |"
        Write-Output "| Drift Detected | $driftCount |"
        Write-Output "| No Counterpart | $noCounterpartCount |"
        Write-Output ""
        Write-Output "## Results"
        Write-Output ""
        Write-Output "| Agent | Status | Similarity | Drifting Sections |"
        Write-Output "|-------|--------|------------|-------------------|"

        foreach ($result in $results | Sort-Object AgentName) {
            $similarity = if ($null -ne $result.OverallSimilarity) { "$($result.OverallSimilarity)%" } else { "N/A" }
            $drifting = if ($result.DriftingSections.Count -gt 0) { $result.DriftingSections -join ", " } else { "-" }
            Write-Output "| $($result.AgentName) | $($result.Status) | $similarity | $drifting |"
        }
    }
}

#endregion

# Exit with appropriate code
if ($driftCount -gt 0) {
    exit 1
}
exit 0
