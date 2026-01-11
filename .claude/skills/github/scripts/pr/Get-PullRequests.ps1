<#
.SYNOPSIS
    Lists GitHub Pull Requests with optional filters.

.DESCRIPTION
    Enumerates PRs in a repository with filtering capabilities:
    - State (open, closed, merged, all)
    - Labels (comma-separated or single label)
    - Author
    - Base branch
    - Head branch
    - Result limit

    Returns a JSON array with PR metadata for downstream processing.

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.

.PARAMETER State
    PR state filter: open, closed, merged, all. Default: open.

.PARAMETER Label
    Filter by label(s). Can be a single label or comma-separated list.

.PARAMETER Author
    Filter by PR author username.

.PARAMETER Base
    Filter by base (target) branch name.

.PARAMETER Head
    Filter by head (source) branch name. Format: OWNER:branch or branch.

.PARAMETER Limit
    Maximum number of PRs to return. Default: 30, max: 1000.

.EXAMPLE
    .\Get-PullRequests.ps1
    # Lists open PRs (default state=open, limit=30)

.EXAMPLE
    .\Get-PullRequests.ps1 -State all -Limit 100
    # Lists up to 100 PRs in any state

.EXAMPLE
    .\Get-PullRequests.ps1 -Label "bug,priority:P1" -State open
    # Lists open PRs with either the 'bug' or 'priority:P1' label

.EXAMPLE
    .\Get-PullRequests.ps1 -Author rjmurillo -Base main
    # Lists PRs by rjmurillo targeting main branch

.EXAMPLE
    .\Get-PullRequests.ps1 -Head "copilot/sub-pr-123"
    # Lists PRs from a specific head branch

.NOTES
    EXIT CODES:
    0  - Success: PRs retrieved successfully
    3  - Error: API error (gh pr list failed)
    4  - Error: Not authenticated (GitHub CLI authentication required)

    See: ADR-035 Exit Code Standardization

.OUTPUTS
    JSON array with objects containing:
    - number: PR number
    - title: PR title
    - head: Head branch name
    - base: Base branch name
    - state: PR state (OPEN, CLOSED, MERGED)
#>

[CmdletBinding()]
param(
    [string]$Owner,
    [string]$Repo,

    [ValidateSet("open", "closed", "merged", "all")]
    [string]$State = "open",

    [string]$Label,

    [string]$Author,

    [string]$Base,

    [string]$Head,

    [ValidateRange(1, 1000)]
    [int]$Limit = 30
)

$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubCore.psm1") -Force

Assert-GhAuthenticated
$resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
$Owner = $resolved.Owner
$Repo = $resolved.Repo

Write-Verbose "Listing PRs in $Owner/$Repo (state=$State, limit=$Limit)"

# Build gh pr list command arguments
$listArgs = @("--repo", "$Owner/$Repo", "--limit", $Limit, "--json", "number,title,headRefName,baseRefName,state")

# Apply state filter
# Note: gh pr list uses --state for open/closed/all, but "merged" requires --state closed plus filtering
if ($State -eq "merged") {
    # For merged PRs, we query closed and filter by merged state
    $listArgs += @("--state", "closed")
}
elseif ($State -ne "all") {
    $listArgs += @("--state", $State)
}

# Apply optional filters
if ($Label) {
    # Support comma-separated labels by splitting and adding multiple --label flags
    $labels = $Label -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    foreach ($lbl in $labels) {
        $listArgs += @("--label", $lbl)
    }
}

if ($Author) {
    $listArgs += @("--author", $Author)
}

if ($Base) {
    $listArgs += @("--base", $Base)
}

if ($Head) {
    $listArgs += @("--head", $Head)
}

Write-Verbose "Running: gh pr list $($listArgs -join ' ')"

$result = gh pr list @listArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-ErrorAndExit "Failed to list PRs: $result" 3
}

# Parse and transform the output
$prs = $result | ConvertFrom-Json

# Filter for merged PRs if requested
if ($State -eq "merged") {
    $prs = $prs | Where-Object { $_.state -eq "MERGED" }
}

# Transform to output format
$output = @($prs | ForEach-Object {
    [PSCustomObject]@{
        number = $_.number
        title  = $_.title
        head   = $_.headRefName
        base   = $_.baseRefName
        state  = $_.state
    }
})

# Output as JSON
$output | ConvertTo-Json -Depth 3 -AsArray

# Summary output to stderr for visibility
$count = $output.Count
Write-Host "Found $count PR(s) in $Owner/$Repo" -ForegroundColor Cyan
if ($count -gt 0) {
    Write-Host "  State filter: $State | Limit: $Limit" -ForegroundColor Gray
    foreach ($pr in $output | Select-Object -First 5) {
        Write-Host "  #$($pr.number): $($pr.title)" -ForegroundColor Gray
    }
    if ($count -gt 5) {
        Write-Host "  ... and $($count - 5) more" -ForegroundColor Gray
    }
}
