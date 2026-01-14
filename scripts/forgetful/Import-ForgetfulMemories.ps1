#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Import Forgetful database from JSON format

.DESCRIPTION
    Idempotent import of JSON memory files into Forgetful SQLite database.
    Merges with existing data using upsert semantics (INSERT OR REPLACE).

    Safe to run multiple times:
    - New records are inserted
    - Existing records are updated with imported values
    - No data is lost from existing database

    See .forgetful/exports/README.md for complete workflow documentation.

.PARAMETER InputFiles
    Array of JSON file paths to import. If not specified, processes all .json files
    in .forgetful/exports/ directory.

.PARAMETER DatabasePath
    Path to Forgetful SQLite database. Defaults to ~/.local/share/forgetful/forgetful.db

.PARAMETER MergeMode
    How to handle existing records:
    - 'Replace' (default): Update existing records with imported values (upsert)
    - 'Skip': Skip existing records, only insert new ones
    - 'Fail': Fail if any record already exists

.PARAMETER Force
    Skip confirmation prompt for imports affecting existing data.

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1

    Imports all JSON files from .forgetful/exports/, merging with existing data

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -MergeMode Skip

    Only insert new records, skip duplicates

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -InputFiles @('.forgetful/exports/backup.json')

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -Force

.NOTES
    Uses SQLite3 command-line tool to import data into Forgetful database.
    Requires sqlite3 to be installed and available in PATH.

    IDEMPOTENCY: Default mode uses INSERT OR REPLACE for upsert semantics.
    Existing records with matching primary keys are updated with new values.
    This allows merging exports from different machines/installations.

    LIMITATION: Only imports .json files from the top-level exports directory.
    Files in subdirectories are NOT imported. Organize exports at the root level.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string[]]$InputFiles,

    [Parameter(Mandatory = $false)]
    [string]$DatabasePath = (Join-Path $env:HOME '.local' 'share' 'forgetful' 'forgetful.db'),

    [Parameter(Mandatory = $false)]
    [ValidateSet('Replace', 'Skip', 'Fail')]
    [string]$MergeMode = 'Replace',

    [Parameter(Mandatory = $false)]
    [switch]$Force
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
    Write-Error "  4. Run Forgetful MCP server at least once to create schema"
    exit 1
}

$ExportsDir = Join-Path $PSScriptRoot '..' '..' '.forgetful' 'exports'

# Determine which files to import
if (-not $InputFiles) {
    if (-not (Test-Path $ExportsDir)) {
        Write-Host "No exports directory found at: $ExportsDir" -ForegroundColor Yellow
        Write-Host "Creating directory..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $ExportsDir -Force | Out-Null
        Write-Host "No memory files to import" -ForegroundColor Cyan
        exit 0
    }

    # NOTE: Only top-level .json files are imported (no subdirectory scanning)
    # WHY: Prevents accidental imports from backup/temp subdirectories
    # LIMITATION: Organize all import files at the root of .forgetful/exports/
    $Files = @(Get-ChildItem -Path $ExportsDir -Filter '*.json' -File)
    if ($Files.Count -eq 0) {
        Write-Host "No memory files to import from: $ExportsDir" -ForegroundColor Cyan
        exit 0
    }

    $InputFiles = $Files | ForEach-Object { $_.FullName }
}
else {
    # Validate provided files exist
    $MissingFiles = @()
    foreach ($File in $InputFiles) {
        if (-not (Test-Path $File)) {
            $MissingFiles += $File
        }
    }

    if ($MissingFiles.Count -gt 0) {
        Write-Error "Input files not found:"
        foreach ($Missing in $MissingFiles) {
            Write-Error "  - $Missing"
        }
        exit 1
    }
}

Write-Host "🔄 Importing $($InputFiles.Count) memory file(s) from .forgetful/exports/" -ForegroundColor Green
Write-Host "   Merge mode: $MergeMode" -ForegroundColor Gray
Write-Host ""

if (-not $Force) {
    Write-Host "⚠️  WARNING: This will modify the Forgetful database at:" -ForegroundColor Yellow
    Write-Host "   $DatabasePath" -ForegroundColor Yellow
    Write-Host ""
    switch ($MergeMode) {
        'Replace' {
            Write-Host "   Mode: REPLACE - Existing records will be UPDATED with imported values" -ForegroundColor Cyan
            Write-Host "   New records will be inserted, existing records will be merged" -ForegroundColor Gray
        }
        'Skip' {
            Write-Host "   Mode: SKIP - Existing records will be SKIPPED (insert new only)" -ForegroundColor Cyan
            Write-Host "   Only new records will be inserted, duplicates ignored" -ForegroundColor Gray
        }
        'Fail' {
            Write-Host "   Mode: FAIL - Import will ABORT if duplicates found" -ForegroundColor Cyan
            Write-Host "   Ensures no existing data is modified" -ForegroundColor Gray
        }
    }
    Write-Host ""
    $Confirm = Read-Host "Continue? (y/N)"
    if ($Confirm -ne 'y' -and $Confirm -ne 'Y') {
        Write-Host "Import cancelled by user" -ForegroundColor Cyan
        exit 0
    }
    Write-Host ""
}

$ImportCount = 0
$UpdateCount = 0
$SkipCount = 0
$FailedFiles = @()

# Determine SQL operation based on merge mode
# WHY: Different modes support different use cases:
# - Replace: Merge data from multiple sources (default, augments existing)
# - Skip: Import only new records (safe, no overwrites)
# - Fail: Strict import (ensures no conflicts)
$SqlOperation = switch ($MergeMode) {
    'Replace' { 'INSERT OR REPLACE INTO' }
    'Skip' { 'INSERT OR IGNORE INTO' }
    'Fail' { 'INSERT INTO' }
}

# Define import order (dependencies first)
# WHY: Foreign key constraints require parent records to exist before children
$ImportOrder = @(
    'users',
    'projects',
    'entities',
    'memories',
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

# Philosophy: Partial import success is acceptable - some files may fail while others succeed
# We track failures but continue processing remaining files for maximum data recovery
foreach ($FilePath in $InputFiles) {
    $FileName = Split-Path $FilePath -Leaf
    Write-Host "  📁 $FileName" -ForegroundColor Gray

    try {
        # Read and parse JSON
        $JsonContent = Get-Content -Path $FilePath -Raw -Encoding UTF8
        $ImportData = $JsonContent | ConvertFrom-Json

        # Validate export format
        if (-not $ImportData.export_metadata) {
            Write-Warning "Invalid export format: missing export_metadata (skipping)"
            $FailedFiles += [PSCustomObject]@{
                File = $FileName
                Reason = 'Invalid export format'
            }
            continue
        }

        if (-not $ImportData.data) {
            Write-Warning "Invalid export format: missing data section (skipping)"
            $FailedFiles += [PSCustomObject]@{
                File = $FileName
                Reason = 'Invalid export format'
            }
            continue
        }

        # Import each table in dependency order
        foreach ($Table in $ImportOrder) {
            if (-not $ImportData.data.$Table) {
                continue # Table not present in export
            }

            $Rows = $ImportData.data.$Table
            if ($Rows.Count -eq 0) {
                continue # Empty table
            }

            Write-Host "     Importing $Table ($($Rows.Count) rows)..." -ForegroundColor DarkGray

            # Build INSERT statement based on merge mode
            # WHY: Different SQL operations support different merge behaviors
            $SampleRow = $Rows[0]
            $Columns = $SampleRow.PSObject.Properties.Name

            $InsertedCount = 0
            $UpdatedCount = 0
            $SkippedCount = 0

            # For Replace mode, we need to check if record exists before insert
            # to distinguish between inserts and updates
            $PrimaryKeyColumn = switch ($Table) {
                'users' { 'id' }
                'memories' { 'id' }
                'projects' { 'id' }
                'entities' { 'id' }
                'documents' { 'id' }
                'code_artifacts' { 'id' }
                'memory_links' { 'id' }
                # Association tables use composite keys
                'memory_project_association' { $null }
                'memory_code_artifact_association' { $null }
                'memory_document_association' { $null }
                'memory_entity_association' { $null }
                'entity_project_association' { $null }
                'entity_relationships' { 'id' }
                default { 'id' }
            }

            foreach ($Row in $Rows) {
                try {
                    # Build column names and values
                    $ColumnNames = ($Columns -join ', ')

                    # Build values array, handling NULL values
                    $Values = $Columns | ForEach-Object {
                        $Value = $Row.$_
                        if ($null -eq $Value) {
                            'NULL'
                        }
                        elseif ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
                            # JSON array/object - convert back to JSON string
                            "'$($Value | ConvertTo-Json -Compress -Depth 10 | ForEach-Object { $_ -replace "'", "''" })'"
                        }
                        elseif ($Value -is [bool]) {
                            if ($Value) { '1' } else { '0' }
                        }
                        else {
                            # Escape single quotes for SQL
                            "'$($Value -replace "'", "''")'"
                        }
                    }

                    $ValuesString = $Values -join ', '

                    # Check if record exists BEFORE insert (for accurate tracking)
                    # SECURITY: Quote $DatabasePath to prevent command injection (CWE-78)
                    # SECURITY: Quote $PkValue to prevent SQL injection (CWE-89)
                    $RecordExistedBefore = $false
                    if ($PrimaryKeyColumn -and $Row.$PrimaryKeyColumn) {
                        $PkValue = $Row.$PrimaryKeyColumn
                        # Escape and quote string values for SQL
                        $QuotedPkValue = if ($PkValue -is [string]) { "'$($PkValue -replace "'", "''")'" } else { $PkValue }
                        $ExistsCheck = sqlite3 "$DatabasePath" "SELECT COUNT(*) FROM $Table WHERE $PrimaryKeyColumn = $QuotedPkValue;" 2>&1
                        $RecordExistedBefore = ($ExistsCheck -eq '1')
                    }

                    # Execute INSERT with appropriate conflict handling
                    # SECURITY: Values are escaped above to prevent SQL injection
                    $InsertSQL = "$SqlOperation $Table ($ColumnNames) VALUES ($ValuesString);"

                    $ErrorOutput = sqlite3 "$DatabasePath" "$InsertSQL" 2>&1

                    # Handle Fail mode - check for constraint violation
                    if ($MergeMode -eq 'Fail' -and $ErrorOutput -match 'UNIQUE constraint failed') {
                        throw "Duplicate record found in $Table (Fail mode enabled)"
                    }

                    # Determine outcome based on pre-check and mode
                    # NOTE: We check existence BEFORE insert, not SELECT changes()
                    # because SELECT changes() runs in separate process (always 0)
                    if ($ErrorOutput -and $ErrorOutput -notmatch 'UNIQUE constraint failed') {
                        # Error occurred (other than expected constraint violation)
                        $SkippedCount++
                    }
                    elseif ($MergeMode -eq 'Replace') {
                        # Replace mode: update if existed, insert if new
                        if ($RecordExistedBefore) {
                            $UpdatedCount++
                        }
                        else {
                            $InsertedCount++
                        }
                    }
                    elseif ($MergeMode -eq 'Skip') {
                        # Skip mode: skip if existed, insert if new
                        if ($RecordExistedBefore) {
                            $SkippedCount++
                        }
                        else {
                            $InsertedCount++
                        }
                    }
                    else {
                        # Fail mode - if we got here without exception, it was inserted
                        $InsertedCount++
                    }
                }
                catch {
                    if ($MergeMode -eq 'Fail') {
                        # In Fail mode, abort on any error
                        throw $_
                    }
                    Write-Warning "Failed to import row in ${Table}: $_"
                }
            }

            # Display results based on merge mode
            if ($MergeMode -eq 'Replace') {
                Write-Host "       ✓ Inserted: $InsertedCount, Updated: $UpdatedCount, Skipped: $SkippedCount" -ForegroundColor DarkGray
            }
            else {
                Write-Host "       ✓ Inserted: $InsertedCount, Skipped: $SkippedCount (duplicates)" -ForegroundColor DarkGray
            }

            $ImportCount += $InsertedCount
            $UpdateCount += $UpdatedCount
            $SkipCount += $SkippedCount
        }
    }
    catch {
        $FailedFiles += [PSCustomObject]@{
            File = $FileName
            Reason = $_.Exception.Message
        }
        Write-Warning "Failed to import ${FileName}: $_"
    }
}

Write-Host ""

if ($FailedFiles.Count -eq 0) {
    if ($MergeMode -eq 'Replace') {
        Write-Host "✅ Import complete: $ImportCount inserted, $UpdateCount updated, $SkipCount unchanged" -ForegroundColor Green
        Write-Host "   Merge mode: Records merged via INSERT OR REPLACE (idempotent upsert)" -ForegroundColor Gray
    }
    else {
        Write-Host "✅ Import complete: $ImportCount records inserted, $SkipCount duplicates skipped" -ForegroundColor Green
        Write-Host "   Mode: $MergeMode (idempotent)" -ForegroundColor Gray
    }
}
else {
    Write-Host "⚠️  Import completed with failures: $ImportCount succeeded, $($FailedFiles.Count) files failed" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Failed files:" -ForegroundColor Red
    foreach ($Failed in $FailedFiles) {
        Write-Host "  ❌ $($Failed.File): $($Failed.Reason)" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Verify JSON file syntax is valid" -ForegroundColor Gray
    Write-Host "  2. Check export was created with Export-ForgetfulMemories.ps1" -ForegroundColor Gray
    Write-Host "  3. Ensure database schema version matches export" -ForegroundColor Gray
    Write-Host "  4. Check foreign key constraints are satisfied" -ForegroundColor Gray
    exit 1
}
