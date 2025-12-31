<#
.SYNOPSIS
    Diagnose session protocol validation failures
.DESCRIPTION
    Analyzes GitHub Actions run to identify NON_COMPLIANT session files.
    Provides job-level status, runner assignment, and stuck job detection.
.PARAMETER RunId
    GitHub Actions run ID (required)
.PARAMETER Repo
    Repository in owner/repo format (default: rjmurillo/ai-agents)
.EXAMPLE
    .\diagnose.ps1 -RunId 20548622722
.NOTES
    See references/ci-debugging-patterns.md for advanced debugging patterns.
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
Write-Host "=== Job-Level Status ===" -ForegroundColor Cyan
$jobStatus = gh api "/repos/$Repo/actions/runs/$RunId/jobs" --jq '.jobs[] | {name: .name, status: .status, conclusion: .conclusion, runner: .runner_name}' 2>&1
if ($LASTEXITCODE -eq 0) {
    $jobStatus | ForEach-Object {
        $job = $_ | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($job) {
            $icon = switch ($job.status) {
                "completed" {
                    switch ($job.conclusion) {
                        "success" { "[OK]" }
                        "failure" { "[FAIL]" }
                        "skipped" { "[SKIP]" }
                        default { "[?]" }
                    }
                }
                "queued" { "[WAIT]" }
                "in_progress" { "[RUN]" }
                default { "[?]" }
            }
            $color = switch ($job.conclusion) {
                "success" { "Green" }
                "failure" { "Red" }
                "skipped" { "DarkGray" }
                default { "Yellow" }
            }
            Write-Host "  $icon $($job.name)" -ForegroundColor $color
        }
        else {
            Write-Host $_
        }
    }
}
else {
    Write-Host "  (Could not retrieve job details via API, using run view)" -ForegroundColor Yellow
    gh run view $RunId --repo $Repo --json jobs --jq '.jobs[] | "  \(.status) \(.name)"'
}

Write-Host ""
Write-Host "=== Stuck/Incomplete Jobs ===" -ForegroundColor Cyan
$stuckJobs = gh api "/repos/$Repo/actions/runs/$RunId/jobs" --jq '.jobs[] | select(.status != \"completed\") | {name: .name, status: .status, runner: .runner_name}' 2>&1
if ($LASTEXITCODE -eq 0 -and $stuckJobs) {
    Write-Host "  Jobs still running or queued:" -ForegroundColor Yellow
    $stuckJobs | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    Write-Host "  Note: runner=null means job is waiting for runner assignment" -ForegroundColor DarkGray
}
else {
    Write-Host "  All jobs completed" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== NON_COMPLIANT Sessions ===" -ForegroundColor Cyan
$logs = gh run view $RunId --repo $Repo --log 2>&1
$verdictMatches = $logs | Select-String -Pattern "(Found verdict|NON_COMPLIANT)"
if ($verdictMatches) {
    $verdictMatches | ForEach-Object { Write-Host $_.Line }
}
else {
    Write-Host "No NON_COMPLIANT sessions found in logs"
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
