#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Verifies GitHub Actions are enabled for bot accounts used in the repository.

.DESCRIPTION
    Checks if bot accounts (like rjmurillo-bot) have GitHub Actions enabled by attempting
    to trigger a workflow. This helps diagnose issues where PRs from bot accounts don't
    trigger required status checks.

.PARAMETER BotAccount
    The GitHub username of the bot account to verify. Defaults to 'rjmurillo-bot'.

.PARAMETER Repository
    The repository to check in format 'owner/repo'. Defaults to current repository.

.PARAMETER TestWorkflow
    The workflow file to use for testing. Defaults to 'ai-pr-quality-gate.yml'.

.EXAMPLE
    ./scripts/Verify-BotAccountActions.ps1
    
    Verifies rjmurillo-bot can trigger workflows in the current repository.

.EXAMPLE
    ./scripts/Verify-BotAccountActions.ps1 -BotAccount "my-bot" -Repository "owner/repo"
    
    Verifies a specific bot account in a specific repository.

.NOTES
    Requires: gh CLI authenticated as the bot account
    Related: Issue #208 - GitHub Actions disabled for rjmurillo-bot
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BotAccount = 'rjmurillo-bot',

    [Parameter()]
    [string]$Repository = '',

    [Parameter()]
    [string]$TestWorkflow = 'ai-pr-quality-gate.yml'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Status {
    param([string]$Message, [string]$Type = 'Info')
    
    $color = switch ($Type) {
        'Success' { 'Green' }
        'Error' { 'Red' }
        'Warning' { 'Yellow' }
        default { 'Cyan' }
    }
    
    Write-Host "[$Type] $Message" -ForegroundColor $color
}

function Test-GhCliInstalled {
    try {
        $null = gh --version
        return $true
    }
    catch {
        return $false
    }
}

function Get-CurrentRepository {
    try {
        $repo = gh repo view --json nameWithOwner -q '.nameWithOwner' 2>$null
        return $repo
    }
    catch {
        return $null
    }
}

function Get-AuthenticatedUser {
    try {
        $user = gh api user --jq '.login' 2>$null
        return $user
    }
    catch {
        return $null
    }
}

function Test-WorkflowDispatch {
    param(
        [string]$Workflow,
        [string]$Repo
    )
    
    try {
        # Attempt to list workflows (doesn't trigger, just checks access)
        $workflows = gh workflow list --repo $Repo --json name,state 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            return @{
                Success = $false
                Error = $workflows
            }
        }
        
        # Try to get workflow details
        $workflowInfo = gh workflow view $Workflow --repo $Repo --json name,state 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            return @{
                Success = $false
                Error = $workflowInfo
            }
        }
        
        return @{
            Success = $true
            Error = $null
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

function Test-BotPRWorkflows {
    param(
        [string]$Repo,
        [string]$Bot
    )
    
    try {
        # Find recent PRs by the bot
        $prs = gh pr list --repo $Repo --author $Bot --limit 5 --json number,headRefName,state 2>$null
        
        if ($LASTEXITCODE -ne 0 -or -not $prs) {
            Write-Status "No recent PRs found from $Bot" -Type 'Warning'
            return $null
        }
        
        $prData = $prs | ConvertFrom-Json
        
        if ($prData.Count -eq 0) {
            Write-Status "No recent PRs found from $Bot" -Type 'Warning'
            return $null
        }
        
        # Check workflow runs for the most recent PR
        $recentPR = $prData[0]
        $branch = $recentPR.headRefName
        
        Write-Status "Checking workflow runs for PR #$($recentPR.number) (branch: $branch)"
        
        $runs = gh run list --repo $Repo --branch $branch --limit 10 --json status,conclusion,name 2>$null
        
        if ($LASTEXITCODE -ne 0) {
            return @{
                PR = $recentPR.number
                Branch = $branch
                HasRuns = $false
                Runs = @()
            }
        }
        
        $runData = $runs | ConvertFrom-Json
        
        return @{
            PR = $recentPR.number
            Branch = $branch
            HasRuns = ($runData.Count -gt 0)
            Runs = $runData
        }
    }
    catch {
        Write-Status "Error checking bot PRs: $_" -Type 'Error'
        return $null
    }
}

# Main execution
Write-Host "`n=== GitHub Actions Bot Account Verification ===" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
if (-not (Test-GhCliInstalled)) {
    Write-Status "GitHub CLI (gh) is not installed or not in PATH" -Type 'Error'
    Write-Status "Install from: https://cli.github.com/" -Type 'Info'
    exit 1
}

Write-Status "GitHub CLI found" -Type 'Success'

# Get current user
$currentUser = Get-AuthenticatedUser

if (-not $currentUser) {
    Write-Status "Not authenticated with GitHub CLI" -Type 'Error'
    Write-Status "Run: gh auth login" -Type 'Info'
    exit 1
}

Write-Status "Authenticated as: $currentUser"

# Determine repository
if (-not $Repository) {
    $Repository = Get-CurrentRepository
    
    if (-not $Repository) {
        Write-Status "Could not determine repository. Use -Repository parameter." -Type 'Error'
        exit 1
    }
}

Write-Status "Repository: $Repository"
Write-Status "Bot account to verify: $BotAccount"
Write-Host ""

# Check if current user is the bot
$isBotUser = ($currentUser -eq $BotAccount)

if ($isBotUser) {
    Write-Status "Currently authenticated as bot account" -Type 'Success'
    Write-Host ""
    
    # Test workflow access
    Write-Status "Testing workflow access..."
    $workflowTest = Test-WorkflowDispatch -Workflow $TestWorkflow -Repo $Repository
    
    if ($workflowTest.Success) {
        Write-Status "✅ Bot can access workflows" -Type 'Success'
        Write-Status "GitHub Actions appear to be ENABLED for $BotAccount" -Type 'Success'
    }
    else {
        Write-Status "❌ Bot cannot access workflows" -Type 'Error'
        Write-Status "Error: $($workflowTest.Error)" -Type 'Error'
        Write-Host ""
        Write-Status "This indicates GitHub Actions are DISABLED for $BotAccount" -Type 'Error'
        Write-Host ""
        Write-Host "To fix:" -ForegroundColor Yellow
        Write-Host "  1. Go to: https://github.com/settings/security_analysis" -ForegroundColor White
        Write-Host "  2. Enable GitHub Actions" -ForegroundColor White
        Write-Host "  3. Run this script again to verify" -ForegroundColor White
        exit 1
    }
}
else {
    Write-Status "Not authenticated as bot account (current: $currentUser)" -Type 'Warning'
    Write-Status "Checking bot PR history instead..."
    Write-Host ""
    
    # Check if bot PRs trigger workflows
    $prCheck = Test-BotPRWorkflows -Repo $Repository -Bot $BotAccount
    
    if ($null -eq $prCheck) {
        Write-Status "Could not verify bot account (no recent PRs found)" -Type 'Warning'
        Write-Host ""
        Write-Host "To verify directly:" -ForegroundColor Yellow
        Write-Host "  1. Authenticate as bot: gh auth login" -ForegroundColor White
        Write-Host "  2. Run: ./scripts/Verify-BotAccountActions.ps1" -ForegroundColor White
        exit 0
    }
    
    if ($prCheck.HasRuns) {
        Write-Status "✅ PR #$($prCheck.PR) has workflow runs" -Type 'Success'
        Write-Status "Found $($prCheck.Runs.Count) workflow run(s)" -Type 'Success'
        Write-Status "GitHub Actions appear to be ENABLED for $BotAccount" -Type 'Success'
        
        Write-Host ""
        Write-Host "Recent workflow runs:" -ForegroundColor Cyan
        foreach ($run in $prCheck.Runs | Select-Object -First 5) {
            $status = if ($run.conclusion) { $run.conclusion } else { $run.status }
            Write-Host "  - $($run.name): $status"
        }
    }
    else {
        Write-Status "❌ PR #$($prCheck.PR) has NO workflow runs" -Type 'Error'
        Write-Status "This indicates GitHub Actions are DISABLED for $BotAccount" -Type 'Error'
        Write-Host ""
        Write-Host "To fix:" -ForegroundColor Yellow
        Write-Host "  1. Log in as $BotAccount" -ForegroundColor White
        Write-Host "  2. Go to: https://github.com/settings/security_analysis" -ForegroundColor White
        Write-Host "  3. Enable GitHub Actions" -ForegroundColor White
        Write-Host "  4. Trigger workflows for PR #$($prCheck.PR):" -ForegroundColor White
        Write-Host "     gh workflow run $TestWorkflow --field pr_number=$($prCheck.PR)" -ForegroundColor Gray
        exit 1
    }
}

Write-Host ""
Write-Status "Verification complete" -Type 'Success'
exit 0
