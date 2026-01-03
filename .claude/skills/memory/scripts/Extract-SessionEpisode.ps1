<#
.SYNOPSIS
    Extracts episode data from session logs.

.DESCRIPTION
    Parses session log markdown files and extracts structured episode data
    for the reflexion memory system per ADR-038.

    Extraction targets:
    - Session metadata (date, objectives, status)
    - Decisions made during the session
    - Events (commits, errors, milestones)
    - Metrics (duration, file counts)
    - Lessons learned

.PARAMETER SessionLogPath
    Path to the session log file to extract from.

.PARAMETER OutputPath
    Output directory for episode JSON. Defaults to .agents/memory/episodes/

.PARAMETER Force
    Overwrite existing episode file if it exists.

.EXAMPLE
    ./Extract-SessionEpisode.ps1 -SessionLogPath ".agents/sessions/2026-01-01-session-126.md"

.NOTES
    Task: M-005 (Phase 2A Memory System)
    ADR: ADR-038 Reflexion Memory Schema
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path $_ -PathType Leaf })]
    [string]$SessionLogPath,

    [string]$OutputPath = (Join-Path $PSScriptRoot ".." ".." ".." ".." ".agents" "memory" "episodes"),

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Helper Functions

function Get-SessionIdFromPath {
    <#
    .SYNOPSIS
        Extracts session ID from log file path.
    #>
    param([string]$Path)

    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($Path)
    # Pattern: YYYY-MM-DD-session-NNN or session-NNN-description
    if ($fileName -match '(\d{4}-\d{2}-\d{2}-session-\d+)') {
        return $Matches[1]
    }
    if ($fileName -match '(session-\d+)') {
        return $Matches[1]
    }
    return $fileName
}

function ConvertFrom-SessionMetadata {
    <#
    .SYNOPSIS
        Extracts metadata from session log header.

    .OUTPUTS
        Hashtable with: title, date, status, objectives, deliverables
    #>
    param([string[]]$Lines)

    $metadata = @{
        title       = ""
        date        = ""
        status      = ""
        objectives  = @()
        deliverables = @()
    }

    $inSection = ""

    foreach ($line in $Lines) {
        # Title (first H1)
        if ($line -match '^#\s+(.+)$' -and -not $metadata.title) {
            $metadata.title = $Matches[1]
            continue
        }

        # Date field
        if ($line -match '^\*\*Date\*\*:\s*(.+)$') {
            $metadata.date = $Matches[1].Trim()
            continue
        }

        # Status field
        if ($line -match '^\*\*Status\*\*:\s*(.+)$') {
            $metadata.status = $Matches[1].Trim()
            continue
        }

        # Objectives section
        if ($line -match '^##\s*Objectives?') {
            $inSection = "objectives"
            continue
        }

        # Deliverables section
        if ($line -match '^##\s*Deliverables?') {
            $inSection = "deliverables"
            continue
        }

        # New section ends current
        if ($line -match '^##\s') {
            $inSection = ""
            continue
        }

        # Collect list items
        if ($line -match '^\s*[-*]\s+(.+)$') {
            $item = $Matches[1].Trim()
            if ($inSection -eq "objectives") {
                $metadata.objectives += $item
            }
            elseif ($inSection -eq "deliverables") {
                $metadata.deliverables += $item
            }
        }
    }

    return $metadata
}

function ConvertFrom-Decisions {
    <#
    .SYNOPSIS
        Extracts decisions from session log.

    .OUTPUTS
        Array of hashtable with: id, timestamp, type, context, chosen, rationale, outcome, effects
    #>
    param([string[]]$Lines)

    $decisions = @()
    $decisionIndex = 0
    $inDecisionSection = $false

    # Use for loop for direct index access needed for context lookups
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        $line = $Lines[$i]

        # Look for decision markers
        if ($line -match '^##\s*Decisions?') {
            $inDecisionSection = $true
            continue
        }

        if ($inDecisionSection -and $line -match '^##\s') {
            $inDecisionSection = $false
        }

        # Decision patterns in various formats
        if ($line -match '^\*\*Decision\*\*:\s*(.+)$' -or
            $line -match '^Decision:\s*(.+)$' -or
            ($inDecisionSection -and $line -match '^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)$')) {

            $decisionIndex++
            $decisionText = if ($Matches[2]) { "$($Matches[1]): $($Matches[2])" } else { $Matches[1] }

            $decision = @{
                id        = "d{0:D3}" -f $decisionIndex
                timestamp = (Get-Date).ToString("o")
                type      = Get-DecisionType -Text $decisionText
                context   = ""
                chosen    = $decisionText
                rationale = ""
                outcome   = "success"  # Default, can be updated
                effects   = @()
            }

            # Look for context/rationale in nearby lines
            if ($i -gt 0 -and $Lines[$i-1] -match '^\s*[-*]\s+(.+)$') {
                $decision.context = $Matches[1]
            }

            $decisions += $decision
        }

        # Also capture decisions from work log entries
        if ($line -match 'chose|decided|selected|opted for' -and $line -notmatch '^#') {
            $decisionIndex++
            $decisions += @{
                id        = "d{0:D3}" -f $decisionIndex
                timestamp = (Get-Date).ToString("o")
                type      = "implementation"
                context   = ""
                chosen    = $line.Trim()
                rationale = ""
                outcome   = "success"
                effects   = @()
            }
        }
    }

    return $decisions
}

function Get-DecisionType {
    <#
    .SYNOPSIS
        Categorizes decision type from text.
    #>
    param([string]$Text)

    $textLower = $Text.ToLower()

    if ($textLower -match 'design|architect|schema|structure') {
        return "design"
    }
    if ($textLower -match 'test|pester|coverage|assert') {
        return "test"
    }
    if ($textLower -match 'recover|fix|retry|fallback') {
        return "recovery"
    }
    if ($textLower -match 'route|delegate|agent|handoff') {
        return "routing"
    }
    return "implementation"
}

function ConvertFrom-Events {
    <#
    .SYNOPSIS
        Extracts events from session log.

    .OUTPUTS
        Array of hashtable with: id, timestamp, type, content, caused_by, leads_to
    #>
    param([string[]]$Lines)

    $events = @()
    $eventIndex = 0

    foreach ($line in $Lines) {
        $evt = $null

        # Commit events
        if ($line -match 'commit[ted]?\s+(?:as\s+)?([a-f0-9]{7,40})' -or
            $line -match '([a-f0-9]{7,40})\s+\w+\(.+\):') {
            $eventIndex++
            $evt = @{
                id        = "e{0:D3}" -f $eventIndex
                timestamp = (Get-Date).ToString("o")
                type      = "commit"
                content   = "Commit: $($Matches[1])"
                caused_by = @()
                leads_to  = @()
            }
        }

        # Error events
        if ($line -match 'error|fail|exception' -and $line -notmatch '^#') {
            $eventIndex++
            $evt = @{
                id        = "e{0:D3}" -f $eventIndex
                timestamp = (Get-Date).ToString("o")
                type      = "error"
                content   = $line.Trim()
                caused_by = @()
                leads_to  = @()
            }
        }

        # Milestone events
        if ($line -match '✅|completed?|done|finished|success' -and $line -match '^[-*]') {
            $eventIndex++
            $evt = @{
                id        = "e{0:D3}" -f $eventIndex
                timestamp = (Get-Date).ToString("o")
                type      = "milestone"
                content   = $line.Trim() -replace '^[-*]\s*', ''
                caused_by = @()
                leads_to  = @()
            }
        }

        # Test events
        if ($line -match 'test[s]?\s+(pass|fail|run)' -or $line -match 'Pester') {
            $eventIndex++
            $evt = @{
                id        = "e{0:D3}" -f $eventIndex
                timestamp = (Get-Date).ToString("o")
                type      = "test"
                content   = $line.Trim()
                caused_by = @()
                leads_to  = @()
            }
        }

        if ($evt) {
            $events += $evt
        }
    }

    return $events
}

function ConvertFrom-Lessons {
    <#
    .SYNOPSIS
        Extracts lessons learned from session log.

    .OUTPUTS
        Array of unique lesson strings
    #>
    param([string[]]$Lines)

    $lessons = @()
    $inLessonsSection = $false

    foreach ($line in $Lines) {
        # Lessons section header
        if ($line -match '^##\s*(Lessons?\s*Learned?|Key\s*Learnings?|Takeaways?)') {
            $inLessonsSection = $true
            continue
        }

        # New section ends lessons
        if ($inLessonsSection -and $line -match '^##\s') {
            $inLessonsSection = $false
        }

        # Collect lesson items
        if ($inLessonsSection -and $line -match '^\s*[-*]\s+(.+)$') {
            $lessons += $Matches[1].Trim()
        }

        # Also capture inline lessons
        if ($line -match 'lesson|learned|takeaway|note for future' -and $line -notmatch '^#') {
            $lessons += $line.Trim()
        }
    }

    return $lessons | Select-Object -Unique
}

function ConvertFrom-Metrics {
    <#
    .SYNOPSIS
        Extracts metrics from session log.

    .OUTPUTS
        Hashtable with: duration_minutes, tool_calls, errors, recoveries, commits, files_changed
    #>
    param([string[]]$Lines)

    $metrics = @{
        duration_minutes = 0
        tool_calls       = 0
        errors           = 0
        recoveries       = 0
        commits          = 0
        files_changed    = 0
    }

    foreach ($line in $Lines) {
        # Duration
        if ($line -match '(\d+)\s*minutes?' -or $line -match 'duration:\s*(\d+)') {
            $metrics.duration_minutes = [int]$Matches[1]
        }

        # Count commits
        if ($line -match '[a-f0-9]{7,40}') {
            $metrics.commits++
        }

        # Count errors
        if ($line -match 'error|fail|exception' -and $line -notmatch '^#') {
            $metrics.errors++
        }

        # Count files
        if ($line -match '(\d+)\s+files?\s+(changed|modified|created)') {
            $metrics.files_changed += [int]$Matches[1]
        }
    }

    return $metrics
}

function Get-SessionOutcome {
    <#
    .SYNOPSIS
        Determines overall session outcome.
    #>
    param(
        [hashtable]$Metadata,
        [array]$Events
    )

    # Null-safe status handling
    $status = if ($Metadata.status) { $Metadata.status.ToLower() } else { "" }

    if ($status -match 'complete|done|success') {
        return "success"
    }
    if ($status -match 'partial|in.?progress|blocked') {
        return "partial"
    }
    if ($status -match 'fail|abort|error') {
        return "failure"
    }

    # Infer from events
    $errorCount = ($Events | Where-Object { $_.type -eq "error" }).Count
    $milestoneCount = ($Events | Where-Object { $_.type -eq "milestone" }).Count

    if ($errorCount -gt $milestoneCount) {
        return "failure"
    }
    if ($milestoneCount -gt 0) {
        return "success"
    }

    return "partial"
}

#endregion

#region Main Execution

Write-Host "Extracting episode from: $SessionLogPath" -ForegroundColor Cyan

# Read session log
try {
    $content = Get-Content -Path $SessionLogPath -Encoding UTF8 -ErrorAction Stop
}
catch {
    Write-Error "Failed to read session log '$SessionLogPath': $($_.Exception.Message)"
    exit 1
}
$sessionId = Get-SessionIdFromPath -Path $SessionLogPath

# Parse components
Write-Host "  Parsing metadata..." -ForegroundColor Gray
$metadata = ConvertFrom-SessionMetadata -Lines $content

Write-Host "  Parsing decisions..." -ForegroundColor Gray
$decisions = ConvertFrom-Decisions -Lines $content

Write-Host "  Parsing events..." -ForegroundColor Gray
$events = ConvertFrom-Events -Lines $content

Write-Host "  Parsing lessons..." -ForegroundColor Gray
$lessons = ConvertFrom-Lessons -Lines $content

Write-Host "  Parsing metrics..." -ForegroundColor Gray
$metrics = ConvertFrom-Metrics -Lines $content

# Determine outcome
$outcome = Get-SessionOutcome -Metadata $metadata -Events $events

# Build episode
$episode = @{
    id        = "episode-$sessionId"
    session   = $sessionId
    timestamp = if ($metadata.date) {
        try { [datetime]::Parse($metadata.date).ToString("o") }
        catch {
            Write-Warning "Could not parse date '$($metadata.date)', using current time"
            (Get-Date).ToString("o")
        }
    } else { (Get-Date).ToString("o") }
    outcome   = $outcome
    task      = if ($metadata.objectives.Count -gt 0) { $metadata.objectives[0] } else { $metadata.title }
    decisions = $decisions
    events    = $events
    metrics   = $metrics
    lessons   = $lessons
}

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -Path $OutputPath -ItemType Directory -Force | Out-Null
}

# Write episode file
$episodeFile = Join-Path $OutputPath "episode-$sessionId.json"

if ((Test-Path $episodeFile) -and -not $Force) {
    Write-Warning "Episode file already exists: $episodeFile"
    Write-Warning "Use -Force to overwrite."
    exit 1
}

try {
    $json = $episode | ConvertTo-Json -Depth 10 -ErrorAction Stop
    Set-Content -Path $episodeFile -Value $json -Encoding UTF8 -ErrorAction Stop
}
catch {
    Write-Error "Failed to write episode file '$episodeFile': $($_.Exception.Message)"
    exit 1
}

# Summary
Write-Host "`nEpisode extracted:" -ForegroundColor Green
Write-Host "  ID:        $($episode.id)" -ForegroundColor Gray
Write-Host "  Session:   $sessionId" -ForegroundColor Gray
Write-Host "  Outcome:   $outcome" -ForegroundColor Gray
Write-Host "  Decisions: $(@($decisions).Count)" -ForegroundColor Gray
Write-Host "  Events:    $(@($events).Count)" -ForegroundColor Gray
Write-Host "  Lessons:   $(@($lessons).Count)" -ForegroundColor Gray
Write-Host "  Output:    $episodeFile" -ForegroundColor Gray

# Return episode for pipeline usage
$episode

#endregion
