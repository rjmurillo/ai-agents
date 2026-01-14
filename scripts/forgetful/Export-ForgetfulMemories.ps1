#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Export Forgetful database to JSON format

.DESCRIPTION
    Exports all data from Forgetful SQLite database to JSON file for backup,
    version control, and sharing across team members and installations.

    IMPORTANT: Security review is REQUIRED before committing exports to git.
    Run: pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile [file].json

    See .forgetful/exports/README.md for complete workflow documentation.

.PARAMETER OutputFile
    Path to output JSON file. Defaults to .forgetful/exports/YYYY-MM-DD-session-NNN-topic.json

    Naming convention: YYYY-MM-DD-session-NNN-topic.json

.PARAMETER SessionNumber
    Optional session number for default filename. If not specified, uses current date only.

.PARAMETER Topic
    Optional topic for default filename (e.g., "architecture-decisions", "agent-patterns")

.PARAMETER DatabasePath
    Path to Forgetful SQLite database. Defaults to ~/.local/share/forgetful/forgetful.db

.PARAMETER IncludeTables
    Comma-separated list of tables to export. Defaults to all data tables.
    Options: memories, projects, entities, documents, code_artifacts, memory_links, associations

.EXAMPLE
    pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -SessionNumber 905 -Topic "architecture"

    Exports to: .forgetful/exports/2026-01-13-session-905-architecture.json

.EXAMPLE
    pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -OutputFile .forgetful/exports/backup.json

.EXAMPLE
    pwsh scripts/forgetful/Export-ForgetfulMemories.ps1 -Topic "full-backup" -IncludeTables "memories,projects"

.NOTES
    Uses SQLite3 command-line tool to extract data from Forgetful database.
    Requires sqlite3 to be installed and available in PATH.

    SECURITY: Always review exports before committing:
    - Run scripts/Review-MemoryExportSecurity.ps1
    - Check for API keys, passwords, tokens, secrets
    - Verify no private file paths or PII
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$OutputFile,

    [Parameter(Mandatory = $false)]
    [int]$SessionNumber,

    [Parameter(Mandatory = $false)]
    [string]$Topic,

    [Parameter(Mandatory = $false)]
    [string]$DatabasePath = (Join-Path $env:HOME '.local' 'share' 'forgetful' 'forgetful.db'),

    [Parameter(Mandatory = $false)]
    [string]$IncludeTables = 'all'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Verify sqlite3 is available
if (-not (Get-Command sqlite3 -ErrorAction SilentlyContinue)) {
    Write-Error "sqlite3 is not installed or not in PATH"
    Write-Error ""
    Write-Error "Install sqlite3:"
    Write-Error "  Ubuntu/Debian: sudo apt-get install sqlite3"
    Write-Error "  macOS: brew install sqlite3"
    Write-Error "  Windows: Download from https://www.sqlite.org/download.html"
    exit 1
}

# Verify database exists
if (-not (Test-Path $DatabasePath)) {
    Write-Error "Forgetful database not found at: $DatabasePath"
    Write-Error ""
    Write-Error "Expected location: ~/.local/share/forgetful/forgetful.db"
    Write-Error ""
    Write-Error "Troubleshooting:"
    Write-Error "  1. Verify Forgetful MCP server is installed and configured"
    Write-Error "  2. Check if database was created at alternate location"
    Write-Error "  3. Create at least one memory via Forgetful to initialize database"
    exit 1
}

$ExportsDir = Join-Path $PSScriptRoot '..' '..' '.forgetful' 'exports'

# Ensure exports directory exists
if (-not (Test-Path $ExportsDir)) {
    Write-Host "Creating exports directory: $ExportsDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $ExportsDir -Force | Out-Null
}

# Generate default filename if not specified
if (-not $OutputFile) {
    $Date = Get-Date -Format 'yyyy-MM-dd'

    $FilenameParts = @($Date)

    if ($SessionNumber) {
        $FilenameParts += "session-$SessionNumber"
    }

    if ($Topic) {
        $FilenameParts += $Topic
    }

    $Filename = ($FilenameParts -join '-') + '.json'
    $OutputFile = Join-Path $ExportsDir $Filename
}

# Ensure output file is in exports directory (prevent path traversal - CWE-22)
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
# VALID: .forgetful/exports/export.json
# INVALID: .forgetful/../export.json (resolves outside exports dir)
$NormalizedOutput = [System.IO.Path]::GetFullPath($OutputFile)
$NormalizedDir = [System.IO.Path]::GetFullPath($ExportsDir)
# Add trailing separator to prevent "exports-evil" directory bypass
$NormalizedDirWithSep = $NormalizedDir.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $NormalizedOutput.StartsWith($NormalizedDirWithSep, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error "Path traversal attempt detected. Output file must be inside '$ExportsDir' directory."
    Write-Error ""
    Write-Error "Attempted path: $OutputFile"
    Write-Error "Normalized path: $NormalizedOutput"
    Write-Error "Required parent: $NormalizedDir"
    Write-Error ""
    Write-Error "Valid example: .forgetful/exports/export.json"
    Write-Error "Invalid example: ../export.json (escapes exports directory)"
    exit 1
}

Write-Host "🔍 Exporting Forgetful database..." -ForegroundColor Cyan
Write-Host "   Database: $DatabasePath" -ForegroundColor Gray
Write-Host "   Output: $OutputFile" -ForegroundColor Gray
Write-Host "   Tables: $IncludeTables" -ForegroundColor Gray
Write-Host ""

# Define tables to export based on parameter
$DataTables = @(
    'users',
    'memories',
    'projects',
    'entities',
    'documents',
    'code_artifacts',
    'memory_links',
    'memory_project_association',
    'memory_code_artifact_association',
    'memory_document_association',
    'memory_entity_association',
    'entity_project_association',
    'entity_relationships'
)

if ($IncludeTables -ne 'all') {
    # Filter tables based on comma-separated list
    $RequestedTables = $IncludeTables -split ',' | ForEach-Object { $_.Trim() }

    # Map simple names to actual table names
    $TableMapping = @{
        'memories' = @('memories', 'memory_links')
        'projects' = @('projects', 'memory_project_association', 'entity_project_association')
        'entities' = @('entities', 'memory_entity_association', 'entity_relationships')
        'documents' = @('documents', 'memory_document_association')
        'code_artifacts' = @('code_artifacts', 'memory_code_artifact_association')
        'associations' = @('memory_project_association', 'memory_code_artifact_association', 'memory_document_association', 'memory_entity_association', 'entity_project_association')
    }

    $ExpandedTables = @('users') # Always include users table
    foreach ($RequestedTable in $RequestedTables) {
        if ($TableMapping.ContainsKey($RequestedTable)) {
            $ExpandedTables += $TableMapping[$RequestedTable]
        }
        elseif ($DataTables -contains $RequestedTable) {
            $ExpandedTables += $RequestedTable
        }
        else {
            Write-Warning "Unknown table: $RequestedTable (skipping)"
        }
    }

    $DataTables = $ExpandedTables | Select-Object -Unique
}

# Build JSON export structure
$ExportData = @{
    export_metadata = @{
        export_timestamp = (Get-Date -Format 'o')
        database_path = $DatabasePath
        forgetful_version = 'unknown'
        schema_version = 'unknown'
        exported_tables = $DataTables
        export_tool = 'Export-ForgetfulMemories.ps1'
    }
    data = @{}
}

# Get schema version from alembic_version table
try {
    $SchemaVersion = sqlite3 $DatabasePath "SELECT version_num FROM alembic_version LIMIT 1;" 2>$null
    if ($SchemaVersion) {
        $ExportData.export_metadata.schema_version = $SchemaVersion.Trim()
    }
}
catch {
    Write-Warning "Could not retrieve schema version: $_"
}

# Export each table
foreach ($Table in $DataTables) {
    Write-Host "  📁 Exporting $Table..." -ForegroundColor Gray

    try {
        # Use SQLite JSON output mode for structured data
        # SECURITY: Quote all variables to prevent SQL injection (CWE-89)
        # WHY: Unquoted variables allow SQL injection attacks
        $TableData = sqlite3 $DatabasePath "SELECT json_group_array(json_object(
            $(
                # Build column list dynamically from table schema
                $Columns = sqlite3 $DatabasePath "PRAGMA table_info($Table);" |
                    ForEach-Object {
                        $Parts = $_ -split '\|'
                        "'$($Parts[1])', $($Parts[1])"
                    }
                $Columns -join ', '
            )
        )) FROM $Table;" 2>$null

        if ($TableData) {
            # Parse JSON and add to export data
            $ParsedData = $TableData | ConvertFrom-Json
            $ExportData.data[$Table] = $ParsedData

            $RowCount = if ($ParsedData) { $ParsedData.Count } else { 0 }
            Write-Host "     ✓ $RowCount rows" -ForegroundColor DarkGray
        }
        else {
            Write-Host "     ⚠ No data (table may be empty)" -ForegroundColor Yellow
            $ExportData.data[$Table] = @()
        }
    }
    catch {
        Write-Warning "Failed to export ${Table}: $_"
        $ExportData.data[$Table] = @()
    }
}

Write-Host ""
Write-Host "💾 Writing export file..." -ForegroundColor Cyan

try {
    # Convert to JSON with indentation for readability
    $JsonContent = $ExportData | ConvertTo-Json -Depth 100

    # Write to file
    Set-Content -Path $OutputFile -Value $JsonContent -Encoding UTF8 -NoNewline

    $FileInfo = Get-Item $OutputFile
    $FileSize = $FileInfo.Length

    Write-Host ""
    Write-Host "✅ Export complete: $OutputFile ($FileSize bytes)" -ForegroundColor Green
    Write-Host ""

    # SECURITY GATE: Automatically run security review
    $SecurityScript = Join-Path $PSScriptRoot '..' 'Review-MemoryExportSecurity.ps1'
    if (Test-Path $SecurityScript) {
        Write-Host "🔒 Running mandatory security review..." -ForegroundColor Cyan
        Write-Host ""

        & $SecurityScript -ExportFile $OutputFile

        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Error "Security review FAILED. Sensitive data detected in export."
            Write-Error "DO NOT commit this file until review passes."
            Write-Error ""
            Write-Error "Next steps:"
            Write-Error "  1. Review and redact sensitive data in: $OutputFile"
            Write-Error "  2. Re-run: pwsh $SecurityScript -ExportFile $OutputFile"
            Write-Error "  3. Only commit after review passes"
            exit 1
        }

        Write-Host ""
        Write-Host "✅ Security review PASSED - Safe to commit" -ForegroundColor Green
    }
    else {
        Write-Host "⚠️  WARNING: Security review script not found at: $SecurityScript" -ForegroundColor Yellow
        Write-Host "   Manually review for sensitive data before committing" -ForegroundColor Yellow
    }
}
catch {
    Write-Error "Failed to write export file: $($_.Exception.Message)"
    Write-Error ""
    Write-Error "Script state at failure:"
    Write-Error "  Output file: $OutputFile"
    Write-Error "  Database path: $DatabasePath"
    Write-Error "  Working directory: $PWD"
    Write-Error ""
    Write-Error "Stack trace:"
    Write-Error $_.ScriptStackTrace
    exit 1
}
