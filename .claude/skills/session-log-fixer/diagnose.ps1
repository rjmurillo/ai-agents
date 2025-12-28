<#
.SYNOPSIS
    Diagnose session protocol validation failures
.DESCRIPTION
    Analyzes GitHub Actions run to identify NON_COMPLIANT session files
.PARAMETER RunId
    GitHub Actions run ID (required)
.PARAMETER Repo
    Repository in owner/repo format (default: rjmurillo/ai-agents)
.EXAMPLE
    .\diagnose.ps1 -RunId 20548622722
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$RunId,

    [Parameter(Position = 1)]
    [string]$Repo = "rjmurillo/ai-agents"
)

$ErrorActionPreference = 'Stop'

Write-Host "=== Run Status ===" -ForegroundColor Cyan
gh run view $RunId --repo $Repo --json status,conclusion,jobs --jq '{
  status,
  conclusion,
  failed_jobs: [.jobs[] | select(.conclusion == \"failure\") | {name, conclusion}]
}'

Write-Host ""
Write-Host "=== NON_COMPLIANT Sessions ===" -ForegroundColor Cyan
$logs = gh run view $RunId --repo $Repo --log 2>&1
$matches = $logs | Select-String -Pattern "(Found verdict|NON_COMPLIANT)"
if ($matches) {
    $matches | ForEach-Object { Write-Host $_.Line }
}
else {
    Write-Host "No NON_COMPLIANT sessions found"
}

Write-Host ""
Write-Host "=== Downloading Artifacts ===" -ForegroundColor Cyan
$artifactDir = Join-Path $env:TEMP "session-artifacts-$RunId"
if (Test-Path $artifactDir) {
    Remove-Item $artifactDir -Recurse -Force
}

try {
    gh run download $RunId --repo $Repo --dir $artifactDir 2>$null
}
catch {
    Write-Host "No artifacts to download or download failed"
    exit 0
}

Write-Host ""
Write-Host "=== Verdict Details ===" -ForegroundColor Cyan
Get-ChildItem -Path $artifactDir -Filter "*-verdict.txt" -Recurse | ForEach-Object {
    Write-Host "--- $($_.Name) ---" -ForegroundColor Yellow
    Get-Content $_.FullName
    Write-Host ""
}

Write-Host ""
Write-Host "=== Validation Output ===" -ForegroundColor Cyan
Get-ChildItem -Path $artifactDir -Filter "*.txt" -Recurse |
    Where-Object { $_.Name -notlike "*-verdict.txt" } |
    ForEach-Object {
        Write-Host "--- $($_.Name) ---" -ForegroundColor Yellow
        Get-Content $_.FullName | Select-Object -First 100
        Write-Host ""
    }
