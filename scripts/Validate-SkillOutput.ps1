<#
.SYNOPSIS
    Validates skill script output against the standard envelope schema (ADR-044).

.DESCRIPTION
    Accepts JSON input from stdin or a file path and validates it against
    the skill-output.schema.json schema. Returns exit code 0 for valid,
    1 for invalid output.

.PARAMETER InputFile
    Path to a JSON file to validate. Use '-' or omit to read from stdin.

.EXAMPLE
    pwsh .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest 1 -OutputFormat JSON | pwsh scripts/Validate-SkillOutput.ps1

.EXAMPLE
    pwsh scripts/Validate-SkillOutput.ps1 -InputFile output.json

.NOTES
    Related: ADR-044 (Skill Output Format Standardization)
#>
[CmdletBinding()]
param(
    [Parameter()]
    [string]$InputFile = '-'
)

$ErrorActionPreference = 'Stop'

# Read input
if ($InputFile -eq '-') {
    $jsonText = @($input) -join "`n"
    if (-not $jsonText) {
        $jsonText = [Console]::In.ReadToEnd()
    }
}
else {
    $allowedDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    # Append directory separator to prevent directory name prefix attacks (e.g., "repo-temp" vs "repo")
    $allowedDir = $allowedDir + [IO.Path]::DirectorySeparatorChar
    $resolvedPath = [IO.Path]::GetFullPath($InputFile)

    if (-not $resolvedPath.StartsWith($allowedDir, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "[FAIL] Path traversal attempt detected. Input file must be within the repository." -ForegroundColor Red
        exit 1
    }

    if (-not (Test-Path $resolvedPath)) {
        Write-Host "[FAIL] File not found: $resolvedPath" -ForegroundColor Red
        exit 1
    }

    # Resolve symlinks to prevent bypass via symlink pointing outside the repo (CWE-22)
    $fileItem = Get-Item -Path $resolvedPath -Force
    if ($fileItem.LinkTarget) {
        $realPath = [IO.Path]::GetFullPath($fileItem.LinkTarget)
        if (-not $realPath.StartsWith($allowedDir, [StringComparison]::OrdinalIgnoreCase)) {
            Write-Host "[FAIL] Path traversal attempt detected. Input file must be within the repository." -ForegroundColor Red
            exit 1
        }
    }

    $jsonText = Get-Content -Path $resolvedPath -Raw
}

if (-not $jsonText -or $jsonText.Trim().Length -eq 0) {
    Write-Host '[FAIL] Empty input — no JSON to validate' -ForegroundColor Red
    exit 1
}

# Parse JSON
try {
    $output = $jsonText | ConvertFrom-Json -ErrorAction Stop
}
catch {
    Write-Host "[FAIL] Invalid JSON: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$errors = @()

# Validate required fields
if ($null -eq $output.PSObject.Properties['Success']) {
    $errors += 'Missing required field: Success'
}
elseif ($output.Success -isnot [bool]) {
    $errors += "Field 'Success' must be a boolean, got: $($output.Success.GetType().Name)"
}

if ($null -eq $output.PSObject.Properties['Metadata']) {
    $errors += 'Missing required field: Metadata'
}
else {
    if (-not $output.Metadata.Script) {
        $errors += 'Metadata.Script is required'
    }
    if (-not $output.Metadata.Timestamp) {
        $errors += 'Metadata.Timestamp is required'
    }
}

# Validate error envelope when Success=false
if ($output.Success -eq $false) {
    if ($null -eq $output.PSObject.Properties['Error'] -or $null -eq $output.Error) {
        $errors += 'Error field is required when Success is false'
    }
    else {
        if (-not $output.Error.Message) {
            $errors += 'Error.Message is required'
        }
        if ($null -eq $output.Error.PSObject.Properties['Code']) {
            $errors += 'Error.Code is required'
        }
        $validTypes = @('NotFound', 'ApiError', 'AuthError', 'InvalidParams', 'Timeout', 'General')
        if ($output.Error.Type -and $output.Error.Type -notin $validTypes) {
            $errors += "Error.Type '$($output.Error.Type)' is not valid. Must be one of: $($validTypes -join ', ')"
        }
    }
}

# Report results
if ($errors.Count -gt 0) {
    Write-Host '[FAIL] Skill output validation failed:' -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host "  - $err" -ForegroundColor Red
    }
    exit 1
}

Write-Host '[PASS] Skill output conforms to ADR-044 envelope schema' -ForegroundColor Green
exit 0
