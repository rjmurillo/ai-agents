# !/usr/bin/env pwsh
<#
.SYNOPSIS
    Validates token budget for HANDOFF.md to prevent exceeding context limits.

.DESCRIPTION
    This script checks if .agents/HANDOFF.md exceeds the 5K token budget.
    Used in pre-commit hooks to block commits that would exceed the limit.

    Token estimation uses heuristics based on text characteristics:
    - Base: ~4 chars/token for English prose
    - Non-ASCII: Increases token count (multilingual, emojis)
    - Punctuation-heavy + low whitespace: Code-like text, denser tokenization
    - Digit-heavy: Numbers and IDs tokenize differently
    - Safety margin: 5% buffer to fail safe

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
  EXIT CODES:
  0  - Success: HANDOFF.md within token budget or file not found
  1  - Error: Token budget exceeded (only when -CI flag is set)

  See: ADR-035 Exit Code Standardization
  Token estimation algorithm based on GPT tokenizer heuristics.
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

function Get-ApproxTokenCount {
    <#
    .SYNOPSIS
        Estimates token count for text using heuristic analysis.

    .DESCRIPTION
        Applies multiple heuristics to estimate token count more accurately than
        a simple character divisor. Accounts for non-ASCII, code-like text,
        digit-heavy content, and applies a safety margin.
    
    .PARAMETER Text
        The text content to analyze.
    
    .OUTPUTS
        [int] Estimated token count with 5% safety margin.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Text
    )

    if ([string]::IsNullOrEmpty($Text)) {
        return 0
    }

    # Normalize newlines to reduce platform variance
    $Normalized = $Text -replace "`r`n", "`n"
    $CharCount = $Normalized.Length

    # Base rule-of-thumb for English prose: ~4 chars/token
    $BaseTokens = [math]::Ceiling($CharCount / 4.0)

    # Analyze text characteristics
    $NonAsciiCount = ([regex]::Matches($Normalized, '[^\u0000-\u007F]')).Count
    $PunctCount    = ([regex]::Matches($Normalized, '[\p{P}\p{S}]')).Count  # Punctuation + symbols
    $DigitCount    = ([regex]::Matches($Normalized, '\d')).Count
    $WhitespaceCount = ([regex]::Matches($Normalized, '\s')).Count

    # Calculate density ratios (0.0 to 1.0+)
    $NonAsciiRatio = if ($CharCount -gt 0) { $NonAsciiCount / $CharCount } else { 0.0 }
    $PunctRatio    = if ($CharCount -gt 0) { $PunctCount / $CharCount } else { 0.0 }
    $DigitRatio    = if ($CharCount -gt 0) { $DigitCount / $CharCount } else { 0.0 }
    $WhitespaceRatio = if ($CharCount -gt 0) { $WhitespaceCount / $CharCount } else { 0.0 }

    # Apply multiplier adjustments based on text characteristics
    $Multiplier = 1.0

    # Non-ASCII (multilingual, emojis) tokenizes less efficiently
    # Example: "🚀" is often 2+ tokens despite being 1 character
    if ($NonAsciiRatio -gt 0.01) {
        $Adjustment = [math]::Min(0.60, 2.0 * $NonAsciiRatio)
        $Multiplier += $Adjustment
    }

    # Code-like text: high punctuation, low whitespace
    # Example: "Get-Content -Path $file | Where-Object {$_.Length -gt 0}"
    # Tokenizes denser than prose due to operators and syntax
    if ($PunctRatio -gt 0.08 -and $WhitespaceRatio -lt 0.18) {
        $Adjustment = [math]::Min(0.50, 3.0 * ($PunctRatio - 0.08))
        $Multiplier += $Adjustment
    }

    # Digit-heavy text (IDs, numbers, data)
    # Example: "PR-12345" or "2024-12-22" tokenizes differently than words
    if ($DigitRatio -gt 0.10) {
        $Adjustment = [math]::Min(0.25, 1.5 * ($DigitRatio - 0.10))
        $Multiplier += $Adjustment
    }

    # Apply multiplier and safety margin (5% buffer to fail safe)
    $SafetyMargin = 1.05
    $EstimatedTokens = [int][math]::Ceiling($BaseTokens * $Multiplier * $SafetyMargin)

    return $EstimatedTokens
}

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

# Estimate token count using heuristic analysis

$EstimatedTokens = Get-ApproxTokenCount -Text $Content

# Get file size in KB

$FileSizeKB = [math]::Round((Get-Item $HandoffPath).Length / 1KB, 2)

Write-Host "Token Budget Validation" -ForegroundColor Cyan
Write-Host "  File: .agents/HANDOFF.md" -ForegroundColor Gray
Write-Host "  Size: $FileSizeKB KB" -ForegroundColor Gray
Write-Host "  Characters: $($Content.Length)" -ForegroundColor Gray
Write-Host "  Estimated tokens: $EstimatedTokens (heuristic)" -ForegroundColor Gray
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
