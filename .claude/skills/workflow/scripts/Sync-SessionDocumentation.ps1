<#
.SYNOPSIS
    Synchronizes session documentation by scanning git history and generating structured reports.

.DESCRIPTION
    Sync-SessionDocumentation.ps1 collects session activity from git history,
    identifies agents invoked, files changed, and decisions made, then generates
    a structured Markdown session sync report with a Mermaid workflow diagram.

    This script supports the /9-sync command for auto-documentation integration.

.PARAMETER SessionNumber
    Optional session number. Auto-detected from existing session logs if omitted.

.PARAMETER LookbackHours
    How many hours of git history to scan. Default: 8.

.PARAMETER OutputPath
    Path to write the sync report. Default: .agents/sessions/ with auto-generated name.

.PARAMETER DryRun
    Preview the report without writing to disk.

.PARAMETER Verbose
    Include extended commit details and full file diffs.

.EXAMPLE
    pwsh .claude/skills/workflow/scripts/Sync-SessionDocumentation.ps1
    pwsh .claude/skills/workflow/scripts/Sync-SessionDocumentation.ps1 -DryRun
    pwsh .claude/skills/workflow/scripts/Sync-SessionDocumentation.ps1 -LookbackHours 24

.NOTES
    Follows ADR-005 (PowerShell-only scripting) and ADR-007 (memory-first architecture).
#>

[CmdletBinding()]
param(
    [Parameter()]
    [int]$SessionNumber = 0,

    [Parameter()]
    [int]$LookbackHours = 8,

    [Parameter()]
    [string]$OutputPath = '',

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$VerboseOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Helper: Get repo root
# ---------------------------------------------------------------------------
function Get-RepoRoot {
    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root) {
        Write-Error "Not inside a git repository."
        exit 1
    }
    return $root
}

# ---------------------------------------------------------------------------
# Helper: Get recent commits within lookback window
# ---------------------------------------------------------------------------
function Get-RecentCommits {
    param([int]$Hours)

    $since = (Get-Date).AddHours(-$Hours).ToString('yyyy-MM-ddTHH:mm:ss')
    $logOutput = git log --oneline --since="$since" --format='%H|%s|%an|%ai' 2>$null

    if (-not $logOutput) {
        # Fallback: last 20 commits
        $logOutput = git log --oneline -20 --format='%H|%s|%an|%ai' 2>$null
    }

    $commits = @()
    foreach ($line in $logOutput) {
        $parts = $line -split '\|', 4
        if ($parts.Count -ge 2) {
            $commits += [PSCustomObject]@{
                Hash    = $parts[0].Substring(0, [Math]::Min(8, $parts[0].Length))
                Message = $parts[1]
                Author  = if ($parts.Count -ge 3) { $parts[2] } else { 'unknown' }
                Date    = if ($parts.Count -ge 4) { $parts[3] } else { '' }
            }
        }
    }
    return $commits
}

# ---------------------------------------------------------------------------
# Helper: Extract agents from commit messages
# ---------------------------------------------------------------------------
function Get-AgentsFromCommits {
    param([array]$Commits)

    $knownAgents = @(
        'orchestrator', 'planner', 'implementer', 'qa', 'security',
        'architect', 'critic', 'devops', 'analyst', 'explainer',
        'task-generator', 'retrospective', 'memory', 'skillbook',
        'context-retrieval', 'high-level-advisor', 'independent-thinker',
        'roadmap', 'merge-resolver'
    )

    $found = [System.Collections.Generic.List[string]]::new()

    foreach ($commit in $Commits) {
        $msg = $commit.Message.ToLower()
        foreach ($agent in $knownAgents) {
            if ($msg -match [regex]::Escape($agent) -and -not $found.Contains($agent)) {
                $found.Add($agent)
            }
        }
    }

    # Infer from conventional commit prefixes
    foreach ($commit in $Commits) {
        $msg = $commit.Message.ToLower()
        if ($msg -match '^feat' -and -not $found.Contains('implementer')) { $found.Add('implementer') }
        if ($msg -match '^fix' -and -not $found.Contains('implementer')) { $found.Add('implementer') }
        if ($msg -match '^test' -and -not $found.Contains('qa')) { $found.Add('qa') }
        if ($msg -match '^docs' -and -not $found.Contains('explainer')) { $found.Add('explainer') }
        if ($msg -match '^ci' -and -not $found.Contains('devops')) { $found.Add('devops') }
        if ($msg -match 'security|cwe|owasp' -and -not $found.Contains('security')) { $found.Add('security') }
    }

    return $found
}

# ---------------------------------------------------------------------------
# Helper: Get changed files
# ---------------------------------------------------------------------------
function Get-ChangedFiles {
    param([int]$Hours)

    $since = (Get-Date).AddHours(-$Hours).ToString('yyyy-MM-ddTHH:mm:ss')
    $diffOutput = git diff --stat --since="$since" HEAD 2>$null

    if (-not $diffOutput) {
        $diffOutput = git diff --stat main..HEAD 2>$null
    }

    if (-not $diffOutput) {
        $diffOutput = git diff --stat HEAD~10..HEAD 2>$null
    }

    return $diffOutput
}

# ---------------------------------------------------------------------------
# Helper: Extract decisions from commits and changed files
# ---------------------------------------------------------------------------
function Get-Decisions {
    param([array]$Commits)

    $decisions = @()

    foreach ($commit in $Commits) {
        $msg = $commit.Message
        # ADR references
        if ($msg -match 'ADR-\d+') {
            $decisions += "ADR reference: $msg"
        }
        # Design decisions in commit messages
        if ($msg -match '(?i)(decision|chose|selected|adopted|switched to|migrated)') {
            $decisions += "Design: $msg"
        }
    }

    return $decisions
}

# ---------------------------------------------------------------------------
# Helper: Get artifacts created (new files in recent commits)
# ---------------------------------------------------------------------------
function Get-Artifacts {
    param([int]$Hours)

    $since = (Get-Date).AddHours(-$Hours).ToString('yyyy-MM-ddTHH:mm:ss')
    $added = git log --since="$since" --diff-filter=A --name-only --format='' 2>$null
    $modified = git log --since="$since" --diff-filter=M --name-only --format='' 2>$null

    if (-not $added -and -not $modified) {
        $added = git log -10 --diff-filter=A --name-only --format='' 2>$null
        $modified = git log -10 --diff-filter=M --name-only --format='' 2>$null
    }

    $artifacts = @()

    if ($added) {
        foreach ($file in ($added | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique)) {
            $artifacts += [PSCustomObject]@{ File = $file; Status = 'new' }
        }
    }

    if ($modified) {
        foreach ($file in ($modified | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique)) {
            # Skip if already in added
            if (-not ($artifacts | Where-Object { $_.File -eq $file })) {
                $artifacts += [PSCustomObject]@{ File = $file; Status = 'modified' }
            }
        }
    }

    return $artifacts
}

# ---------------------------------------------------------------------------
# Helper: Generate Mermaid sequence diagram
# ---------------------------------------------------------------------------
function New-WorkflowDiagram {
    param([array]$Agents)

    $lines = @()
    $lines += '```mermaid'
    $lines += 'sequenceDiagram'
    $lines += '    participant U as User'

    # Add agent participants
    $agentAbbrev = @{
        'orchestrator'       = 'O'
        'planner'            = 'P'
        'implementer'        = 'I'
        'qa'                 = 'Q'
        'security'           = 'S'
        'architect'          = 'A'
        'critic'             = 'C'
        'devops'             = 'D'
        'analyst'            = 'An'
        'explainer'          = 'E'
        'retrospective'      = 'R'
        'memory'             = 'M'
        'merge-resolver'     = 'MR'
        'high-level-advisor' = 'HLA'
        'independent-thinker'= 'IT'
        'roadmap'            = 'RM'
    }

    foreach ($agent in $Agents) {
        $abbr = if ($agentAbbrev.ContainsKey($agent)) { $agentAbbrev[$agent] } else { $agent.Substring(0, [Math]::Min(3, $agent.Length)).ToUpper() }
        $lines += "    participant $abbr as $agent"
    }

    # Generate interaction flow
    if ($Agents.Count -gt 0) {
        $firstAbbr = if ($agentAbbrev.ContainsKey($Agents[0])) { $agentAbbrev[$Agents[0]] } else { $Agents[0].Substring(0, 3).ToUpper() }
        $lines += "    U->>$($firstAbbr): Initiate workflow"

        for ($i = 0; $i -lt $Agents.Count - 1; $i++) {
            $curr = $Agents[$i]
            $next = $Agents[$i + 1]
            $currAbbr = if ($agentAbbrev.ContainsKey($curr)) { $agentAbbrev[$curr] } else { $curr.Substring(0, 3).ToUpper() }
            $nextAbbr = if ($agentAbbrev.ContainsKey($next)) { $agentAbbrev[$next] } else { $next.Substring(0, 3).ToUpper() }
            $lines += "    $($currAbbr)->>$($nextAbbr): Handoff"
        }

        $lastAgent = $Agents[$Agents.Count - 1]
        $lastAbbr = if ($agentAbbrev.ContainsKey($lastAgent)) { $agentAbbrev[$lastAgent] } else { $lastAgent.Substring(0, 3).ToUpper() }
        $lines += "    $($lastAbbr)->>U: Results"
    }

    $lines += '```'
    return $lines -join "`n"
}

# ---------------------------------------------------------------------------
# Helper: Detect current session log
# ---------------------------------------------------------------------------
function Get-CurrentSessionLog {
    param([string]$RepoRoot)

    $sessionsDir = Join-Path $RepoRoot '.agents' 'sessions'
    if (-not (Test-Path $sessionsDir)) { return $null }

    $today = Get-Date -Format 'yyyy-MM-dd'
    $todayLogs = Get-ChildItem -Path $sessionsDir -Filter "${today}*.json" -File 2>$null |
        Sort-Object Name -Descending |
        Select-Object -First 1

    return $todayLogs
}

# ---------------------------------------------------------------------------
# Helper: Suggest retrospective learnings
# ---------------------------------------------------------------------------
function Get-RetrospectiveSuggestions {
    param(
        [array]$Commits,
        [array]$Agents,
        [array]$Artifacts
    )

    $suggestions = @()

    # Pattern: many commits = possibly too granular
    if ($Commits.Count -gt 15) {
        $suggestions += "Consider squashing related commits — $($Commits.Count) commits may indicate overly granular work"
    }

    # Pattern: no QA involvement
    if ($Agents -and -not ($Agents -contains 'qa')) {
        $suggestions += 'No QA agent was invoked during this session — consider running /3-qa before completion'
    }

    # Pattern: no security for script changes
    $scriptChanges = $Artifacts | Where-Object { $_.File -match '\.(ps1|py|sh|bash)$' }
    if ($scriptChanges -and -not ($Agents -contains 'security')) {
        $suggestions += 'Script files were modified without security review — consider running /4-security'
    }

    # Pattern: new ADR without critic review
    $adrChanges = $Artifacts | Where-Object { $_.File -match 'ADR-\d+' -and $_.Status -eq 'new' }
    if ($adrChanges -and -not ($Agents -contains 'critic')) {
        $suggestions += 'New ADR created without critic review — consider architect/critic consensus'
    }

    if ($suggestions.Count -eq 0) {
        $suggestions += 'Session followed standard patterns — no specific improvements identified'
    }

    return $suggestions
}

# ===========================================================================
# Main
# ===========================================================================
$repoRoot = Get-RepoRoot
$currentBranch = git branch --show-current 2>$null

Write-Host "🔄 /9-sync: Generating session documentation..." -ForegroundColor Cyan
Write-Host "  Branch: $currentBranch" -ForegroundColor Gray
Write-Host "  Lookback: $LookbackHours hours" -ForegroundColor Gray

# Gather data
$commits = Get-RecentCommits -Hours $LookbackHours
$agents = Get-AgentsFromCommits -Commits $commits
$changedFiles = Get-ChangedFiles -Hours $LookbackHours
$decisions = Get-Decisions -Commits $commits
$artifacts = Get-Artifacts -Hours $LookbackHours
$diagram = New-WorkflowDiagram -Agents $agents
$learnings = Get-RetrospectiveSuggestions -Commits $commits -Agents $agents -Artifacts $artifacts
$currentLog = Get-CurrentSessionLog -RepoRoot $repoRoot

# Build report
$date = Get-Date -Format 'yyyy-MM-dd'
$sessionLabel = if ($SessionNumber -gt 0) { "Session $SessionNumber" } else { "Session" }

$report = @"
## Session Sync Report — $date $sessionLabel

**Branch**: ``$currentBranch``
**Commits**: $($commits.Count) in last $LookbackHours hours
**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

### Workflow Diagram

$diagram

### Agents Invoked

"@

if ($agents.Count -gt 0) {
    $i = 1
    foreach ($agent in $agents) {
        $report += "$i. $agent`n"
        $i++
    }
} else {
    $report += "_No agents detected from commit history._`n"
}

$report += @"

### Recent Commits

| Hash | Message |
|------|---------|
"@

foreach ($commit in ($commits | Select-Object -First 20)) {
    $escapedMsg = $commit.Message -replace '\|', '\|'
    $report += "| ``$($commit.Hash)`` | $escapedMsg |`n"
}

$report += @"

### Decisions Made

"@

if ($decisions.Count -gt 0) {
    foreach ($d in $decisions) {
        $report += "- $d`n"
    }
} else {
    $report += "_No explicit decisions detected from commit messages._`n"
}

$report += @"

### Artifacts Created/Modified

| File | Status |
|------|--------|
"@

foreach ($a in ($artifacts | Select-Object -First 30)) {
    $report += "| ``$($a.File)`` | $($a.Status) |`n"
}

if ($artifacts.Count -eq 0) {
    $report += "| _(none detected)_ | — |`n"
}

$report += @"

### Retrospective Learnings

"@

foreach ($l in $learnings) {
    $report += "- $l`n"
}

$report += @"

---
_Generated by /9-sync (Sync-SessionDocumentation.ps1)_
"@

# Output
if ($DryRun) {
    Write-Host "`n📋 DRY RUN — Report preview:`n" -ForegroundColor Yellow
    Write-Host $report
    Write-Host "`n✅ Dry run complete. No files written." -ForegroundColor Green
} else {
    # Determine output path
    if (-not $OutputPath) {
        $sessionsDir = Join-Path $repoRoot '.agents' 'sessions'
        if (-not (Test-Path $sessionsDir)) {
            New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        }
        $sessionSlug = if ($SessionNumber -gt 0) { "session-$SessionNumber" } else { 'session' }
        $OutputPath = Join-Path $sessionsDir "$date-$sessionSlug-sync.md"
    }

    # Security: Validate OutputPath to prevent path traversal (CWE-22)
    $allowedDir = [System.IO.Path]::GetFullPath($repoRoot)
    $resolvedPath = [System.IO.Path]::GetFullPath($OutputPath)
    if (-not $resolvedPath.StartsWith($allowedDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path traversal attempt detected. Output path '$OutputPath' is outside the repository root."
    }

    $report | Out-File -FilePath $OutputPath -Encoding utf8 -Force
    Write-Host "`n✅ Session sync report written to: $OutputPath" -ForegroundColor Green
    Write-Host "  Commits: $($commits.Count)" -ForegroundColor Gray
    Write-Host "  Agents detected: $($agents.Count)" -ForegroundColor Gray
    Write-Host "  Artifacts: $($artifacts.Count)" -ForegroundColor Gray
    Write-Host "  Learnings: $($learnings.Count)" -ForegroundColor Gray
}

# Output structured JSON for programmatic consumption
$jsonOutput = @{
    date        = $date
    branch      = $currentBranch
    commits     = $commits.Count
    agents      = @($agents)
    artifacts   = $artifacts.Count
    decisions   = $decisions.Count
    learnings   = @($learnings)
    outputPath  = if (-not $DryRun) { $OutputPath } else { $null }
} | ConvertTo-Json -Depth 3

Write-Host "`n📊 Structured Output:" -ForegroundColor Cyan
Write-Host $jsonOutput
