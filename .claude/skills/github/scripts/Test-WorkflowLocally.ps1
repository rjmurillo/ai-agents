<#
.SYNOPSIS
    PowerShell wrapper for testing GitHub Actions workflows locally with act.

.DESCRIPTION
    Simplifies local workflow testing by providing a PowerShell interface to nektos/act.
    Validates prerequisites, constructs act commands, and provides helpful error messages.

    Supported workflows (PowerShell-compatible, no AI dependencies):
    - pester-tests.yml        : Run Pester unit tests
    - validate-paths.yml      : Validate path normalization

    Unsupported workflows (require AI infrastructure):
    - ai-session-protocol.yml : Requires Copilot CLI and BOT_PAT
    - ai-pr-quality-gate.yml  : Requires Copilot CLI and BOT_PAT
    - ai-spec-validation.yml  : Requires Copilot CLI and BOT_PAT

.PARAMETER Workflow
    Workflow name (without .yml extension) or full path to workflow file.
    Examples: "pester-tests", "validate-paths", ".github/workflows/pester-tests.yml"

.PARAMETER Event
    GitHub event type to simulate. Default: "pull_request"
    Common events: push, pull_request, workflow_dispatch

.PARAMETER DryRun
    Run in dry-run mode to validate workflow parsing without execution.
    Useful for checking workflow syntax.

.PARAMETER Verbose
    Enable verbose output from act for detailed execution logs.

.PARAMETER Job
    Specific job name to run (optional). If not specified, all jobs run.

.PARAMETER Secrets
    Hashtable of secrets to pass to the workflow.
    Example: @{ GITHUB_TOKEN = "ghp_..." }

.EXAMPLE
    .\Test-WorkflowLocally.ps1 -Workflow pester-tests
    # Run pester-tests.yml workflow with default settings

.EXAMPLE
    .\Test-WorkflowLocally.ps1 -Workflow validate-paths -DryRun
    # Validate validate-paths.yml syntax without executing

.EXAMPLE
    .\Test-WorkflowLocally.ps1 -Workflow pester-tests -Job test -Verbose
    # Run only the 'test' job with verbose output

.EXAMPLE
    .\Test-WorkflowLocally.ps1 -Workflow pester-tests -Secrets @{ GITHUB_TOKEN = $env:GITHUB_TOKEN }
    # Pass GITHUB_TOKEN secret to workflow

.NOTES
    Prerequisites:
    - act installed (brew install act, choco install act-cli, or download from GitHub)
    - Docker installed and running
    - PowerShell Core 7+ (for cross-platform compatibility)

    Related: Epic #848 (GitHub Actions Local Testing)
    See: .agents/devops/SHIFT-LEFT.md#local-workflow-testing
    See: .agents/analysis/github-actions-local-testing-research.md
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Workflow,

    [Parameter()]
    [string]$Event = 'pull_request',

    [Parameter()]
    [switch]$DryRun,

    [Parameter()]
    [switch]$Verbose,

    [Parameter()]
    [string]$Job,

    [Parameter()]
    [hashtable]$Secrets
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Helper Functions

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Failure {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

#endregion

#region Prerequisites Check

Write-Info "Checking prerequisites..."

# Check for act
if (-not (Get-Command act -ErrorAction SilentlyContinue)) {
    Write-Failure "act not found. Install act to enable local workflow testing."
    Write-Host ""
    Write-Host "Installation instructions:"
    Write-Host "  macOS:       brew install act"
    Write-Host "  Windows:     Download from https://github.com/nektos/act/releases"
    Write-Host "  Linux:       Download from https://github.com/nektos/act/releases"
    Write-Host "  GitHub CLI:  gh extension install https://github.com/nektos/gh-act"
    Write-Host ""
    Write-Host "See: https://nektosact.com/installation/index.html"
    exit 2
}

Write-Success "act found: $(act --version)"

# Check for Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Failure "Docker not found. act requires Docker to run workflows."
    Write-Host ""
    Write-Host "Install Docker:"
    Write-Host "  macOS/Windows: https://www.docker.com/products/docker-desktop"
    Write-Host "  Linux:         https://docs.docker.com/engine/install/"
    exit 2
}

# Check if Docker is running
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Failure "Docker daemon is not running. Start Docker and try again."
        exit 2
    }
    Write-Success "Docker is running"
} catch {
    Write-Failure "Failed to check Docker status: $_"
    exit 2
}

#endregion

#region Workflow Path Resolution

$repoRoot = Split-Path -Parent $PSScriptRoot
$workflowsDir = Join-Path $repoRoot ".github" "workflows"

# Map short names to full paths
$workflowMap = @{
    'pester-tests' = 'pester-tests.yml'
    'validate-paths' = 'validate-paths.yml'
    'memory-validation' = 'memory-validation.yml'
}

# Resolve workflow path
$workflowPath = $null
if ($Workflow.EndsWith('.yml') -or $Workflow.EndsWith('.yaml')) {
    if (Test-Path $Workflow) {
        $workflowPath = $Workflow
    } elseif (Test-Path (Join-Path $workflowsDir $Workflow)) {
        $workflowPath = Join-Path $workflowsDir $Workflow
    }
} elseif ($workflowMap.ContainsKey($Workflow)) {
    $workflowPath = Join-Path $workflowsDir $workflowMap[$Workflow]
} else {
    # Try appending .yml
    $workflowPath = Join-Path $workflowsDir "$Workflow.yml"
}

if (-not (Test-Path $workflowPath)) {
    Write-Failure "Workflow file not found: $Workflow"
    Write-Host ""
    Write-Host "Available workflows:"
    foreach ($key in $workflowMap.Keys | Sort-Object) {
        Write-Host "  - $key"
    }
    Write-Host ""
    Write-Host "Unsupported workflows (require AI infrastructure or Copilot CLI):"
    Write-Host "  - ai-session-protocol (requires Copilot CLI with BOT_PAT)"
    Write-Host "  - ai-pr-quality-gate (requires Copilot CLI with BOT_PAT)"
    Write-Host "  - ai-spec-validation (requires Copilot CLI with BOT_PAT)"
    Write-Host ""
    Write-Host "Note: While Copilot CLI can be installed locally, these workflows"
    Write-Host "require BOT_PAT and GitHub secrets that are only available in CI."
    exit 1
}

Write-Info "Workflow: $workflowPath"

#endregion

#region Build act Command

# Start with base command
$actArgs = @()

# Add event type
$actArgs += $Event

# Add workflow file
$actArgs += '-W', $workflowPath

# Add job filter if specified
if ($Job) {
    $actArgs += '-j', $Job
}

# Add dry-run flag
if ($DryRun) {
    $actArgs += '-n'
    Write-Info "Dry-run mode: validating workflow without execution"
}

# Add verbose flag
if ($Verbose) {
    $actArgs += '-v'
}

# Add secrets
if ($Secrets) {
    foreach ($key in $Secrets.Keys) {
        $actArgs += '-s', "$key=$($Secrets[$key])"
    }
}

# Try to get GITHUB_TOKEN from gh CLI if not provided
if (-not $Secrets -or -not $Secrets.ContainsKey('GITHUB_TOKEN')) {
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        try {
            $token = gh auth token 2>&1
            if ($LASTEXITCODE -eq 0 -and $token) {
                $actArgs += '-s', "GITHUB_TOKEN=$token"
                Write-Info "Using GITHUB_TOKEN from gh CLI"
            }
        } catch {
            Write-Warning "Failed to retrieve GITHUB_TOKEN from gh CLI: $_"
        }
    }
}

#endregion

#region Execute act

Write-Info "Running: act $($actArgs -join ' ')"
Write-Host ""

# Change to repo root (act expects to run from repo root)
Push-Location $repoRoot

try {
    # Execute act
    & act @actArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Success "Workflow execution completed successfully"
        exit 0
    } else {
        Write-Host ""
        Write-Failure "Workflow execution failed with exit code $LASTEXITCODE"
        Write-Host ""
        Write-Host "Troubleshooting tips:"
        Write-Host "  1. Check Docker logs: docker ps -a | grep act-"
        Write-Host "  2. Run with -Verbose for detailed output"
        Write-Host "  3. Use -DryRun to validate workflow syntax"
        Write-Host "  4. Ensure Docker has sufficient resources"
        Write-Host ""
        Write-Host "Common issues:"
        Write-Host "  - Missing dependencies: Use catthehacker/ubuntu:act-latest image"
        Write-Host "  - Windows-specific code: act uses Linux containers"
        Write-Host "  - Secrets not available: Pass via -Secrets parameter"
        exit 1
    }
} finally {
    Pop-Location
}

#endregion
