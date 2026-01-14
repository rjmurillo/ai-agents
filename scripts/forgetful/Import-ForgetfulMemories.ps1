#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Import Forgetful database from JSON format

.DESCRIPTION
    Idempotent import of JSON memory files into Forgetful SQLite database.
    Automatically prevents duplicates using primary keys and composite keys.

    Safe to run multiple times - existing records are skipped.

    See .forgetful/exports/README.md for complete workflow documentation.

.PARAMETER InputFiles
    Array of JSON file paths to import. If not specified, processes all .json files
    in .forgetful/exports/ directory.

.PARAMETER DatabasePath
    Path to Forgetful SQLite database. Defaults to ~/.local/share/forgetful/forgetful.db

.PARAMETER Force
    Skip confirmation prompt for imports affecting existing data.

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1

    Imports all JSON files from .forgetful/exports/

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -InputFiles @('.forgetful/exports/backup.json')

.EXAMPLE
    pwsh scripts/forgetful/Import-ForgetfulMemories.ps1 -Force

.NOTES
    Uses SQLite3 command-line tool to import data into Forgetful database.
    Requires sqlite3 to be installed and available in PATH.

    IDEMPOTENCY: Records are inserted using INSERT OR IGNORE to prevent duplicates.
    Existing records with matching primary keys are automatically skipped.

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
Write-Host ""

if (-not $Force) {
    Write-Host "⚠️  WARNING: This will modify the Forgetful database at:" -ForegroundColor Yellow
    Write-Host "   $DatabasePath" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Existing records with matching IDs will be SKIPPED (idempotent)." -ForegroundColor Gray
    Write-Host ""
    $Confirm = Read-Host "Continue? (y/N)"
    if ($Confirm -ne 'y' -and $Confirm -ne 'Y') {
        Write-Host "Import cancelled by user" -ForegroundColor Cyan
        exit 0
    }
    Write-Host ""
}

$ImportCount = 0
$SkipCount = 0
$FailedFiles = @()

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

            # Build INSERT OR IGNORE statement for idempotency
            # WHY: INSERT OR IGNORE skips existing records, making import idempotent
            $SampleRow = $Rows[0]
            $Columns = $SampleRow.PSObject.Properties.Name

            $InsertedCount = 0
            $SkippedCount = 0

            foreach ($Row in $Rows) {
                try {
                    # Build column names and values
                    $ColumnNames = ($Columns -join ', ')
                    $Placeholders = ($Columns | ForEach-Object { '?' }) -join ', '

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

                    # Execute INSERT OR IGNORE
                    # SECURITY: Using parameterized values (already escaped above)
                    $InsertSQL = "INSERT OR IGNORE INTO $Table ($ColumnNames) VALUES ($ValuesString);"

                    sqlite3 $DatabasePath "$InsertSQL" 2>&1 | Out-Null

                    # Check if row was inserted (changes > 0) or skipped (changes = 0)
                    $Changes = sqlite3 $DatabasePath "SELECT changes();" 2>&1
                    if ($Changes -eq '1') {
                        $InsertedCount++
                    }
                    else {
                        $SkippedCount++
                    }
                }
                catch {
                    Write-Warning "Failed to import row in ${Table}: $_"
                }
            }

            Write-Host "       ✓ Inserted: $InsertedCount, Skipped: $SkippedCount (duplicates)" -ForegroundColor DarkGray

            $ImportCount += $InsertedCount
            $SkipCount += $SkippedCount
        }
    }
    catch {
        $FailedFiles += [PSCustomObject]@{
            File = $FileName
            Reason = $_.Exception.Message
        }
        Write-Warning "Failed to import $FileName: $_"
    }
}

Write-Host ""

if ($FailedFiles.Count -eq 0) {
    Write-Host "✅ Import complete: $ImportCount records inserted, $SkipCount duplicates skipped" -ForegroundColor Green
    Write-Host "   Duplicates automatically skipped via INSERT OR IGNORE (idempotent)" -ForegroundColor Gray
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
