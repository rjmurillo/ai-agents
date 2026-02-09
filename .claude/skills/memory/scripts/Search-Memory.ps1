<#
.SYNOPSIS
    Unified memory search across Serena and Forgetful.

.DESCRIPTION
    Agent-facing skill script that wraps MemoryRouter.psm1.
    Provides unified memory search with Serena-first routing
    and optional Forgetful augmentation per ADR-037.
    Includes token budget warnings for large memories.

.PARAMETER Query
    Search query (1-500 chars, alphanumeric + common punctuation).

.PARAMETER MaxResults
    Maximum results to return (1-100, default 10).

.PARAMETER LexicalOnly
    Search only Serena (lexical/file-based). Faster, no network.

.PARAMETER SemanticOnly
    Search only Forgetful (semantic/vector). Requires MCP running.

.PARAMETER Format
    Output format: Json (default) or Table.

.EXAMPLE
    pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks"

.EXAMPLE
    pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "powershell arrays" -LexicalOnly -Format Table

.EXAMPLE
    pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "authentication patterns" -MaxResults 5

.NOTES
    ADR: ADR-037 Memory Router Architecture
    Module: scripts/MemoryRouter.psm1
    Task: M-003 (Phase 2A Memory System)

    EXIT CODES:
    0  - Success: Search completed (implicit)
    1  - Error: Invalid query or search failed

    See: ADR-035 Exit Code Standardization
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateLength(1, 500)]
    [ValidatePattern('^[a-zA-Z0-9\s\-.,_()&:]+$')]
    [string]$Query,

    [ValidateRange(1, 100)]
    [int]$MaxResults = 10,

    [switch]$LexicalOnly,

    [switch]$SemanticOnly,

    [ValidateSet('Json', 'Table')]
    [string]$Format = 'Json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Token budget thresholds (from memory-size-001-decomposition-thresholds)
$TOKEN_WARN_THRESHOLD = 5000
$TOKEN_DECOMPOSE_THRESHOLD = 10000

function Get-TokenEstimate {
    param([string]$FilePath)
    if ($FilePath -and (Test-Path $FilePath)) {
        [math]::Round((Get-Content $FilePath -Raw).Length / 4)
    }
    else { 0 }
}

# Import the Memory Router module
$ModulePath = Join-Path $PSScriptRoot "MemoryRouter.psm1"
if (-not (Test-Path $ModulePath)) {
    Write-Error "MemoryRouter module not found at: $ModulePath"
    exit 1
}

Import-Module $ModulePath -Force

# Build parameters for Search-Memory
$searchParams = @{
    Query      = $Query
    MaxResults = $MaxResults
}

if ($LexicalOnly) {
    $searchParams['LexicalOnly'] = $true
}

if ($SemanticOnly) {
    $searchParams['SemanticOnly'] = $true
}

try {
    # Capture search metadata
    $searchStatus = @{
        SerenaQueried    = -not $SemanticOnly
        ForgetfulQueried = -not $LexicalOnly
        SerenaSucceeded  = $false
        ForgetfulSucceeded = $false
        ForgetfulError   = $null
    }

    # Get router status before search to know Forgetful availability
    $routerStatus = Get-MemoryRouterStatus
    $forgetfulWasAvailable = $routerStatus.Forgetful.Available

    # Perform search and capture any warnings
    $warningOutput = @()
    $results = Search-Memory @searchParams -WarningVariable warningOutput

    # Determine success status
    if (-not $SemanticOnly) {
        $searchStatus.SerenaSucceeded = $true  # Serena always succeeds if path exists
    }
    if (-not $LexicalOnly) {
        if ($forgetfulWasAvailable) {
            # Check if there were warnings about Forgetful
            $forgetfulWarning = $warningOutput | Where-Object { $_ -match 'Forgetful' }
            if ($forgetfulWarning) {
                $searchStatus.ForgetfulSucceeded = $false
                $searchStatus.ForgetfulError = $forgetfulWarning -join '; '
            }
            else {
                $searchStatus.ForgetfulSucceeded = $true
            }
        }
        else {
            $searchStatus.ForgetfulSucceeded = $false
            $searchStatus.ForgetfulError = "Forgetful unavailable (TCP health check failed)"
        }
    }

    # Compute token estimates for results with file paths
    $tokenBudget = @{
        TotalEstimate = 0
        Warnings      = @()
    }
    foreach ($result in $results) {
        $estimate = Get-TokenEstimate -FilePath $result.Path
        $result | Add-Member -NotePropertyName 'TokenEstimate' -NotePropertyValue $estimate -Force
        $tokenBudget.TotalEstimate += $estimate
        if ($estimate -ge $TOKEN_DECOMPOSE_THRESHOLD) {
            $tokenBudget.Warnings += "DECOMPOSE: $($result.Name) ($estimate tokens) exceeds $TOKEN_DECOMPOSE_THRESHOLD"
        }
        elseif ($estimate -ge $TOKEN_WARN_THRESHOLD) {
            $tokenBudget.Warnings += "LARGE: $($result.Name) ($estimate tokens) exceeds $TOKEN_WARN_THRESHOLD"
        }
    }

    if ($Format -eq 'Table') {
        if ($results.Count -eq 0) {
            Write-Host "No results found for: $Query"
        }
        else {
            $results | Format-Table -Property Name, Source, Score, TokenEstimate, @{
                Name       = 'Preview'
                Expression = {
                    $preview = $_.Content -replace '\s+', ' '
                    if ($preview.Length -gt 60) { $preview.Substring(0, 57) + '...' } else { $preview }
                }
            } -AutoSize

            # Token budget summary
            Write-Host "Token budget: $($tokenBudget.TotalEstimate) tokens (cumulative for $($results.Count) results)"
            foreach ($warning in $tokenBudget.Warnings) {
                Write-Warning $warning
            }
        }
    }
    else {
        # JSON output for programmatic consumption
        $output = @{
            Query        = $Query
            Count        = $results.Count
            Source       = if ($LexicalOnly) { 'Serena' } elseif ($SemanticOnly) { 'Forgetful' } else { 'Unified' }
            SearchStatus = $searchStatus
            TokenBudget  = $tokenBudget
            Results      = @($results | ForEach-Object {
                    @{
                        Name          = $_.Name
                        Source        = $_.Source
                        Score         = $_.Score
                        Path          = $_.Path
                        Content       = $_.Content
                        TokenEstimate = $_.TokenEstimate
                    }
                })
            Diagnostic   = Get-MemoryRouterStatus
        }
        $output | ConvertTo-Json -Depth 5
    }
}
catch {
    $errorOutput = @{
        Error   = $_.Exception.Message
        Query   = $Query
        Details = $_.ScriptStackTrace
    }
    $errorOutput | ConvertTo-Json -Depth 3
    exit 1
}
