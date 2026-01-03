#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Security review script for Claude-Mem export files.

.DESCRIPTION
    Scans exported memory JSON files for sensitive information patterns including:
    - API keys, tokens, passwords, secrets
    - Private file paths
    - Database connection strings
    - Email addresses and PII patterns

    Exits with code 1 if sensitive data is found, 0 if clean.

.PARAMETER ExportFile
    Path to the exported memory JSON file to review.

.PARAMETER Quiet
    Suppress output, only set exit code.

.EXAMPLE
    .\scripts\Review-MemoryExportSecurity.ps1 -ExportFile .claude-mem/memories/export.json

.EXAMPLE
    .\scripts\Review-MemoryExportSecurity.ps1 -ExportFile export.json -Quiet
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateScript({ Test-Path $_ -PathType Leaf })]
    [string]$ExportFile,

    [Parameter(Mandatory = $false)]
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Sensitive data patterns to scan for
# NOTE: These are regex patterns - literal special characters must be escaped
# Example: To match "key.value", use "key\.value" not "key.value"
$SensitivePatterns = @{
    'API Keys/Tokens'          = @(
        'api[_-]?key',
        'access[_-]?token',
        'bearer\s+[a-zA-Z0-9_-]{20,}',
        'github[_-]?token',
        'gh[ps]_[a-zA-Z0-9]{36}',
        'AKIA[0-9A-Z]{16}',                                    # AWS Access Keys
        'xox[baprs]-[0-9a-zA-Z]{10,}',                        # Slack Tokens
        'npm_[A-Za-z0-9]{36}'                                 # npm Tokens
    )
    'Passwords/Secrets'        = @(
        'password\s*[:=]\s*[\"\x27]?[^\"\s]{8,}',
        'secret\s*[:=]',
        'credential',
        'auth[_-]?key',
        '[a-zA-Z0-9~_.-]{34}',                                # Azure Client Secrets
        '[A-Za-z0-9+/=]{40,}'                                 # Long base64-like strings (40+ chars, may include legitimate data)
    )
    'Private Keys'             = @(
        'BEGIN\s+(RSA|PRIVATE|ENCRYPTED)\s+KEY',
        'private[_-]?key',
        'SHA256:[A-Za-z0-9+/=]{43}'                           # SSH key fingerprints
    )
    'File Paths'               = @(
        '/home/[a-z]+/',
        'C:\\Users\\[^\\]+\\',
        '/Users/[^/]+/'
    )
    'Database Credentials'     = @(
        'connection[_-]?string',
        'jdbc:',
        'mongodb://',
        'postgres://',
        'mysql://'
    )
    'Email/PII'                = @(
        '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        'ssn\s*[:=]',
        'social[_-]?security',
        '(10|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.\d+\.\d+' # Private IP addresses
    )
}

if (-not $Quiet) {
    Write-Host "🔍 Scanning export file for sensitive data: $ExportFile" -ForegroundColor Cyan
    Write-Host ""
}

$FoundIssues = @()
$TotalMatches = 0

foreach ($Category in $SensitivePatterns.Keys) {
    $Patterns = $SensitivePatterns[$Category]

    foreach ($Pattern in $Patterns) {
        try {
            $PatternMatches = Select-String -Path $ExportFile -Pattern $Pattern -AllMatches -CaseSensitive:$false

            if ($PatternMatches) {
                $MatchCount = ($PatternMatches | Measure-Object).Count
                $TotalMatches += $MatchCount

                $FoundIssues += [PSCustomObject]@{
                    Category = $Category
                    Pattern  = $Pattern
                    Count    = $MatchCount
                    Lines    = ($PatternMatches | Select-Object -First 3 -ExpandProperty LineNumber) -join ', '
                }
            }
        }
        catch {
            # Pattern may be malformed or file may have issues
            # FAIL-SAFE: Treat pattern failure as potential security risk
            Write-Warning "Pattern scanning failed for category '$Category', pattern '$Pattern': $_"

            $FoundIssues += [PSCustomObject]@{
                Category = "$Category (SCAN FAILED)"
                Pattern  = $Pattern
                Count    = 1
                Lines    = "Error: $($_.Exception.Message)"
            }
        }
    }
}

if ($FoundIssues.Count -eq 0) {
    if (-not $Quiet) {
        Write-Host "✅ CLEAN - No sensitive data patterns detected" -ForegroundColor Green
        Write-Host ""
        Write-Host "Export file is safe to commit to version control." -ForegroundColor Green
    }
    exit 0
}
else {
    if (-not $Quiet) {
        Write-Host "⚠️  WARNING - Sensitive data patterns detected!" -ForegroundColor Red
        Write-Host ""
        Write-Host "Found $TotalMatches potential sensitive data matches:" -ForegroundColor Yellow
        Write-Host ""

        $FoundIssues | Format-Table -AutoSize @{
            Label      = 'Category'
            Expression = { $_.Category }
        }, @{
            Label      = 'Pattern'
            Expression = { $_.Pattern }
        }, @{
            Label      = 'Matches'
            Expression = { $_.Count }
        }, @{
            Label      = 'Sample Lines'
            Expression = { $_.Lines }
        }

        Write-Host ""
        Write-Host "ACTION REQUIRED:" -ForegroundColor Red
        Write-Host "1. Review the export file manually at: $ExportFile" -ForegroundColor Yellow
        Write-Host "2. Remove or redact sensitive data" -ForegroundColor Yellow
        Write-Host "3. Re-run this script to verify clean" -ForegroundColor Yellow
        Write-Host "4. DO NOT commit until scan is clean" -ForegroundColor Yellow
        Write-Host ""
    }
    exit 1
}
