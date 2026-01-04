#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Export ALL claude-mem data directly from SQLite database (bypasses broken search)

.DESCRIPTION
    The claude-mem export script uses full-text search which only returns ~2% of data
    (71 out of 3500+ observations). This script exports EVERYTHING directly from SQLite.

    **RECOMMENDED for full backups** - The FTS query approach is fundamentally broken.

    DUPLICATE DETECTION FIX:
    - Adds sdk_session_id field via JOIN with sdk_sessions table
    - Replaces NULL/empty titles with "(untitled)" placeholder
    - Without these fixes, import creates massive duplicates (1000s of duplicate rows)

    REQUIREMENTS:
    - sqlite3 command-line tool must be installed
    - Windows: Download from https://www.sqlite.org/download.html or use Chocolatey/Scoop
    - Linux: sudo apt-get install sqlite3 (Ubuntu/Debian)
    - macOS: brew install sqlite3

.PARAMETER Project
    Optional project filter. If omitted, exports ALL projects.

.PARAMETER OutputFile
    Output JSON file path. Default: .claude-mem/memories/direct-backup-YYYY-MM-DD-HHMM.json

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemDirect.ps1
    # Exports ALL observations from all projects

.EXAMPLE
    pwsh .claude-mem/scripts/Export-ClaudeMemDirect.ps1 -Project "ai-agents"
    # Exports only ai-agents project observations

.NOTES
    WARNING: Do NOT use Export-ClaudeMemFullBackup.ps1 - it only exports 2% of data!
    The FTS query approach (query=".") only matches observations containing periods.

    This script is the ONLY reliable way to export complete institutional knowledge.

    Exported files are compatible with claude-mem import:
    pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[a-zA-Z0-9_-]+$')]
    [string]$Project,

    [Parameter(Mandatory = $false)]
    [string]$OutputFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Check if sqlite3 is available
$Sqlite3Available = $null -ne (Get-Command sqlite3 -ErrorAction SilentlyContinue)

if (-not $Sqlite3Available) {
    $IsWindows = $PSVersionTable.PSVersion.Major -ge 6 -and $IsWindows
    $IsLegacyWindows = $PSVersionTable.PSVersion.Major -lt 6

    Write-Error "sqlite3 command not found. Please install SQLite:"
    Write-Host ""

    if ($IsWindows -or $IsLegacyWindows) {
        Write-Host "Windows Installation:" -ForegroundColor Yellow
        Write-Host "  1. Download SQLite tools from: https://www.sqlite.org/download.html" -ForegroundColor Cyan
        Write-Host "  2. Extract sqlite3.exe to a directory in your PATH" -ForegroundColor Cyan
        Write-Host "  3. Or install via Chocolatey: choco install sqlite" -ForegroundColor Cyan
        Write-Host "  4. Or install via Scoop: scoop install sqlite" -ForegroundColor Cyan
    } else {
        Write-Host "Linux/macOS Installation:" -ForegroundColor Yellow
        Write-Host "  Ubuntu/Debian: sudo apt-get install sqlite3" -ForegroundColor Cyan
        Write-Host "  macOS: brew install sqlite3" -ForegroundColor Cyan
        Write-Host "  Fedora/RHEL: sudo dnf install sqlite" -ForegroundColor Cyan
    }

    Write-Host ""
    exit 1
}

$DbPath = Join-Path $env:HOME '.claude-mem' 'claude-mem.db'

if (-not (Test-Path $DbPath)) {
    Write-Error "Claude-Mem database not found at: $DbPath"
    exit 1
}

# Generate default filename
$MemoriesDir = Join-Path $PSScriptRoot '..' 'memories'
$Timestamp = Get-Date -Format 'yyyy-MM-dd-HHmm'
$DefaultFile = "direct-backup-$Timestamp"
if ($Project) { $DefaultFile += "-$Project" }
$DefaultFile += ".json"

$OutputPath = if ($OutputFile) { $OutputFile } else {
    Join-Path $MemoriesDir $DefaultFile
}

# Ensure memories directory exists
if (-not (Test-Path $MemoriesDir)) {
    New-Item -ItemType Directory -Path $MemoriesDir -Force | Out-Null
}

# Ensure output file is in memories directory (prevent path traversal - CWE-22)
# WHY: Normalize paths before comparison to prevent directory traversal attacks
# SECURITY: GetFullPath() resolves ".." and ensures paths are absolute
#
# ATTACK SCENARIO: Without this check, an attacker could specify:
#   -OutputFile "../../etc/passwd" or "../../../sensitive-data.json"
# This would write export data outside the intended directory, potentially:
#   - Overwriting system files
#   - Exposing sensitive data to unintended locations
#   - Bypassing access controls
#
# VALID: .claude-mem/memories/export.json
# INVALID: .claude-mem/../export.json (resolves outside memories dir)
$NormalizedOutput = [System.IO.Path]::GetFullPath($OutputPath)
$NormalizedDir = [System.IO.Path]::GetFullPath($MemoriesDir)
# Add trailing separator to prevent "memories-evil" directory bypass
$NormalizedDirWithSep = $NormalizedDir.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $NormalizedOutput.StartsWith($NormalizedDirWithSep, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error "Path traversal attempt detected. Output file must be inside '$MemoriesDir' directory."
    Write-Error ""
    Write-Error "Attempted path: $OutputFile"
    Write-Error "Normalized path: $NormalizedOutput"
    Write-Error "Required parent: $NormalizedDir"
    Write-Error ""
    Write-Error "Valid example: .claude-mem/memories/export.json"
    Write-Error "Invalid example: ../export.json (escapes memories directory)"
    exit 1
}

Write-Host "🔍 Exporting from SQLite database..." -ForegroundColor Cyan
if ($Project) {
    Write-Host "   Scope: Project '$Project'" -ForegroundColor Gray
} else {
    Write-Host "   Scope: ALL projects" -ForegroundColor Gray
}
Write-Host "   Database: $DbPath" -ForegroundColor Gray
Write-Host "   Output: $OutputPath" -ForegroundColor Gray
Write-Host ""

# Build project filter for different tables
# SECURITY: Escape single quotes to prevent SQL injection (CWE-89)
# Defense-in-depth: ValidatePattern provides first layer, escaping provides second layer
$SafeProject = if ($Project) { $Project -replace "'", "''" } else { "" }
$ObsFilter = if ($Project) { "WHERE o.project = '$SafeProject'" } else { "" }
$SummaryFilter = if ($Project) { "WHERE ss.project = '$SafeProject'" } else { "" }
$SessionFilter = if ($Project) { "WHERE project = '$SafeProject'" } else { "" }
$PromptFilter = if ($Project) { "WHERE content_session_id IN (SELECT content_session_id FROM sdk_sessions WHERE project = '$SafeProject')" } else { "" }

# Get counts (simple queries without aliases)
$CountFilter = if ($Project) { "WHERE project = '$SafeProject'" } else { "" }
$ObsCount = sqlite3 $DbPath "SELECT COUNT(*) FROM observations $CountFilter;"
$SummaryCount = sqlite3 $DbPath "SELECT COUNT(*) FROM session_summaries $CountFilter;"
$PromptCount = sqlite3 $DbPath "SELECT COUNT(*) FROM user_prompts $PromptFilter;"
$SessionCount = sqlite3 $DbPath "SELECT COUNT(*) FROM sdk_sessions $SessionFilter;"

Write-Host "📊 Database contains:" -ForegroundColor Cyan
Write-Host "   Observations: $ObsCount"
Write-Host "   Session summaries: $SummaryCount"
Write-Host "   User prompts: $PromptCount"
Write-Host "   SDK sessions: $SessionCount"
Write-Host ""

# Export to temp files then parse
$TempDir = [System.IO.Path]::GetTempPath()

# Export observations with sdk_session_id for duplicate detection
Write-Host "📦 Exporting observations..." -ForegroundColor Cyan
$ObsTemp = Join-Path $TempDir "obs-$((Get-Date).Ticks).json"
$ObsQuery = @"
SELECT
    o.*,
    s.content_session_id as sdk_session_id
FROM observations o
LEFT JOIN sdk_sessions s ON o.memory_session_id = s.memory_session_id
$ObsFilter
ORDER BY o.created_at_epoch DESC
"@
sqlite3 $DbPath -json $ObsQuery | Out-File $ObsTemp
$Observations = Get-Content $ObsTemp -Raw | ConvertFrom-Json
Remove-Item $ObsTemp -Force

# Fix NULL titles to enable duplicate detection (plugin bug workaround)
# Duplicate detection uses (sdk_session_id + title + created_at_epoch)
# but fails when title is NULL because NULL != NULL in SQL
$NullTitleCount = 0
foreach ($obs in $Observations) {
    if ([string]::IsNullOrWhiteSpace($obs.title)) {
        $obs.title = "(untitled)"
        $NullTitleCount++
    }
}
if ($NullTitleCount -gt 0) {
    Write-Host "   Fixed $NullTitleCount NULL titles for duplicate detection" -ForegroundColor Yellow
}

# Export session summaries with sdk_session_id for duplicate detection
Write-Host "📦 Exporting session summaries..." -ForegroundColor Cyan
$SummTemp = Join-Path $TempDir "summ-$((Get-Date).Ticks).json"
$SummQuery = @"
SELECT
    ss.*,
    s.content_session_id as sdk_session_id
FROM session_summaries ss
LEFT JOIN sdk_sessions s ON ss.memory_session_id = s.memory_session_id
$SummaryFilter
ORDER BY ss.created_at_epoch DESC
"@
sqlite3 $DbPath -json $SummQuery | Out-File $SummTemp
$Summaries = Get-Content $SummTemp -Raw | ConvertFrom-Json
Remove-Item $SummTemp -Force

# Export user prompts
Write-Host "📦 Exporting user prompts..." -ForegroundColor Cyan
$PromptTemp = Join-Path $TempDir "prompt-$((Get-Date).Ticks).json"
sqlite3 $DbPath -json "SELECT * FROM user_prompts $PromptFilter ORDER BY prompt_number DESC;" | Out-File $PromptTemp
$Prompts = Get-Content $PromptTemp -Raw | ConvertFrom-Json
Remove-Item $PromptTemp -Force

# Export SDK sessions
Write-Host "📦 Exporting SDK sessions..." -ForegroundColor Cyan
$SessTemp = Join-Path $TempDir "sess-$((Get-Date).Ticks).json"
sqlite3 $DbPath -json "SELECT * FROM sdk_sessions $SessionFilter ORDER BY started_at_epoch DESC;" | Out-File $SessTemp
$Sessions = Get-Content $SessTemp -Raw | ConvertFrom-Json
Remove-Item $SessTemp -Force

# Build export JSON
$QueryDescription = if ($Project) { "direct-sqlite (project: $Project)" } else { "direct-sqlite (all projects)" }
$ExportData = @{
    exportedAt = (Get-Date -Format 'o')
    exportedAtEpoch = [int](Get-Date -UFormat %s)
    query = $QueryDescription
    method = "direct-sqlite"
    project = $Project
    totalObservations = [int]$ObsCount
    totalSessions = [int]$SessionCount
    totalSummaries = [int]$SummaryCount
    totalPrompts = [int]$PromptCount
    observations = $Observations
    sessions = $Sessions
    summaries = $Summaries
    prompts = $Prompts
}

$ExportData | ConvertTo-Json -Depth 10 -Compress:$false | Out-File -FilePath $OutputPath -Encoding UTF8

$FileSize = (Get-Item $OutputPath).Length

Write-Host ""
Write-Host "✅ Direct export created: $OutputPath" -ForegroundColor Green
Write-Host "   File size: $([math]::Round($FileSize / 1KB, 2)) KB" -ForegroundColor Gray
Write-Host ""
Write-Host "📊 Exported:" -ForegroundColor Cyan
Write-Host "   Observations: $ObsCount"
Write-Host "   Session summaries: $SummaryCount"
Write-Host "   User prompts: $PromptCount"
Write-Host "   SDK sessions: $SessionCount"
Write-Host ""

# Security review
Write-Host "🔒 Running security review..." -ForegroundColor Cyan
$SecurityScript = Join-Path $PSScriptRoot '..' '..' 'scripts' 'Review-MemoryExportSecurity.ps1'

& $SecurityScript -ExportFile $OutputPath

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Error "Security review FAILED. Violations must be fixed before commit."
    exit 1
}

Write-Host "✅ Security review PASSED" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  Import on fresh instance: pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1"
