#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Validates token budget for HANDOFF.md to prevent exceeding context limits.

.DESCRIPTION
    This script checks if .agents/HANDOFF.md exceeds the 5K token budget.
    Used in pre-commit hooks to block commits that would exceed the limit.

.PARAMETER Path
    Path to the repository root. Defaults to current directory.

.PARAMETER MaxTokens
    Maximum allowed tokens. Defaults to 5000.

.PARAMETER CI
    Run in CI mode (exit code 1 on failure).

.EXAMPLE
    .\scripts\Validate-TokenBudget.ps1

.EXAMPLE
    .\scripts\Validate-TokenBudget.ps1 -Path /path/to/repo -MaxTokens 5000 -CI

.NOTES
    Token estimation: ~4 characters per token (conservative estimate for English text)
    Related: Issue #190 (HANDOFF.md merge conflicts)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Path = ".",

    [Parameter(Mandatory = $false)]
    [int]$MaxTokens = 5000,

    [Parameter(Mandatory = $false)]
    [switch]$CI
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve to absolute path
$RepoRoot = Resolve-Path $Path | Select-Object -ExpandProperty Path
$HandoffPath = Join-Path $RepoRoot ".agents" "HANDOFF.md"

# Check if HANDOFF.md exists
if (-not (Test-Path $HandoffPath)) {
    Write-Host "✓ HANDOFF.md not found (OK for new repos)" -ForegroundColor Green
    exit 0
}

# Read file content
$Content = Get-Content -Path $HandoffPath -Raw

# Estimate token count (conservative: 4 chars per token)
$CharCount = $Content.Length
$EstimatedTokens = [math]::Ceiling($CharCount / 4)

# Get file size in KB
$FileSizeKB = [math]::Round((Get-Item $HandoffPath).Length / 1KB, 2)

Write-Host "Token Budget Validation" -ForegroundColor Cyan
Write-Host "  File: .agents/HANDOFF.md" -ForegroundColor Gray
Write-Host "  Size: $FileSizeKB KB" -ForegroundColor Gray
Write-Host "  Characters: $CharCount" -ForegroundColor Gray
Write-Host "  Estimated tokens: $EstimatedTokens" -ForegroundColor Gray
Write-Host "  Budget: $MaxTokens tokens" -ForegroundColor Gray

if ($EstimatedTokens -gt $MaxTokens) {
    $OverBudget = $EstimatedTokens - $MaxTokens
    $PercentOver = [math]::Round(($OverBudget / $MaxTokens) * 100, 1)
    
    Write-Host ""
    Write-Host "✗ FAILED: HANDOFF.md exceeds token budget" -ForegroundColor Red
    Write-Host "  Over budget by: $OverBudget tokens ($PercentOver%)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Action Required:" -ForegroundColor Yellow
    Write-Host "  1. Archive current content to .agents/archive/HANDOFF-YYYY-MM-DD.md" -ForegroundColor White
    Write-Host "  2. Create minimal dashboard (see ADR-014)" -ForegroundColor White
    Write-Host "  3. Use session logs and Serena memory for context" -ForegroundColor White
    Write-Host ""
    Write-Host "See: .agents/architecture/ADR-014-distributed-handoff-architecture.md" -ForegroundColor Gray
    
    if ($CI) {
        exit 1
    }
    return $false
}

$UnderBudget = $MaxTokens - $EstimatedTokens
$PercentUsed = [math]::Round(($EstimatedTokens / $MaxTokens) * 100, 1)

Write-Host ""
Write-Host "✓ PASS: HANDOFF.md within token budget" -ForegroundColor Green
Write-Host "  Remaining: $UnderBudget tokens ($PercentUsed% used)" -ForegroundColor Green

exit 0
