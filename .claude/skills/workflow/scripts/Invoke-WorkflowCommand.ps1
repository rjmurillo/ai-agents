#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generic workflow command executor.

.DESCRIPTION
    Routes workflow commands to their corresponding Invoke-*.ps1 scripts.
    Validates command exists before execution.

.PARAMETER Command
    Workflow command name (e.g., '0-init', '1-plan', '2-impl', '3-qa', '4-security').

.PARAMETER Arguments
    Arguments to pass to the command script.

.EXAMPLE
    pwsh Invoke-WorkflowCommand.ps1 -Command '0-init'
    pwsh Invoke-WorkflowCommand.ps1 -Command '1-plan' -Arguments @{ Task = 'Add feature X'; Arch = $true }

.NOTES
    Exit Codes (ADR-035):
    0 - Success
    3 - Validation error (unknown command)
    Other - Forwarded from invoked script
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Command,

    [Parameter()]
    [hashtable]$Arguments = @{}
)

$ErrorActionPreference = 'Stop'

$ScriptsDir = $PSScriptRoot
$CommandsDir = Join-Path $PSScriptRoot '../../../../commands/workflow'

$CommandMap = @{
    '0-init'      = Join-Path $ScriptsDir 'Invoke-Init.ps1'
    '1-plan'      = Join-Path $ScriptsDir 'Invoke-Plan.ps1'
    '2-impl'      = Join-Path $ScriptsDir 'Invoke-Impl.ps1'
    '3-qa'        = Join-Path $ScriptsDir 'Invoke-QA.ps1'
    '4-security'  = Join-Path $ScriptsDir 'Invoke-Security.ps1'
}

# Validate command
if (-not $CommandMap.ContainsKey($Command)) {
    $validCommands = $CommandMap.Keys -join ', '
    Write-Host "Unknown command: '$Command'. Valid: $validCommands" -ForegroundColor Red
    exit 3
}

$ScriptPath = $CommandMap[$Command]
if (-not (Test-Path $ScriptPath)) {
    Write-Host "Command script not found: $ScriptPath" -ForegroundColor Red
    exit 3
}

# Log execution
Write-Host "▶ Running workflow command: $Command" -ForegroundColor Cyan

# Convert hashtable arguments to splatted parameters
$startTime = Get-Date
& $ScriptPath @Arguments
$exitCode = $LASTEXITCODE

$elapsed = (Get-Date) - $startTime
Write-Host "  Duration: $($elapsed.TotalSeconds.ToString('F1'))s | Exit: $exitCode" -ForegroundColor DarkGray

exit $exitCode
