#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Implementation phase workflow command (/2-impl).

.DESCRIPTION
    Invokes implementer agent with optional chaining:
    - Default:    implementer only
    - --full:     implementer → qa → security (sequential)
    - --parallel: implementer + parallel(qa, security)

.PARAMETER Task
    Implementation task description.

.PARAMETER Full
    Run full sequential chain: implementer → qa → security.

.PARAMETER Parallel
    Run implementer, then qa and security in parallel.

.NOTES
    Exit Codes (ADR-035):
    0 - Success
    2 - MCP error
    3 - Validation error
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$Task,

    [Parameter()]
    [switch]$Full,

    [Parameter()]
    [switch]$Parallel
)

$ErrorActionPreference = 'Stop'

$ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
Import-Module $ModulePath -Force

$taskText = $Task -join ' '
if ([string]::IsNullOrWhiteSpace($taskText)) {
    Write-Error 'Task description is required. Usage: /2-impl [--full] [--parallel] <task>'
    exit 3
}

$ctx = Get-WorkflowContext

Write-Host "🔨 Implementing: $taskText" -ForegroundColor Cyan

# Phase 1: Always invoke implementer
Write-Host "`n  [1/1] Invoking: implementer" -ForegroundColor Yellow
$implResult = Invoke-AgentOrchestrationMCP -ToolName 'invoke_agent' -Arguments @{
    agent   = 'implementer'
    task    = $taskText
    context = $ctx | ConvertTo-Json -Compress
}
if ($implResult.Fallback) {
    Write-Warning 'Agent Orchestration MCP unavailable. Instruct implementer agent directly.'
}

# Phase 2: Chained agents based on mode
if ($Full) {
    Write-Host "`n  Running full sequential chain..." -ForegroundColor DarkCyan

    foreach ($agent in @('qa', 'security')) {
        Write-Host "  → Invoking: $agent" -ForegroundColor Yellow
        Invoke-AgentOrchestrationMCP -ToolName 'track_handoff' -Arguments @{
            from_agent = 'implementer'
            to_agent   = $agent
        } | Out-Null
        Invoke-AgentOrchestrationMCP -ToolName 'invoke_agent' -Arguments @{
            agent            = $agent
            task             = $taskText
            prior_impl_output = $implResult | ConvertTo-Json -Compress
        } | Out-Null
    }
}
elseif ($Parallel) {
    Write-Host "`n  Running parallel QA + security..." -ForegroundColor DarkCyan

    $parallelResult = Invoke-AgentOrchestrationMCP -ToolName 'start_parallel_execution' -Arguments @{
        agents = @('qa', 'security')
        task   = $taskText
    }
    if (-not $parallelResult.Fallback) {
        $aggregated = Invoke-AgentOrchestrationMCP -ToolName 'aggregate_parallel_results' -Arguments @{
            results = $parallelResult | ConvertTo-Json -Compress
        }
        Write-Host "  ✓ Parallel results aggregated" -ForegroundColor Green
    }
    else {
        Write-Warning 'Parallel execution unavailable — run /3-qa and /4-security separately.'
    }
}

# Update context
$ctx | Add-Member -NotePropertyName 'LastCommand' -NotePropertyValue '2-impl' -Force
$ctx | Add-Member -NotePropertyName 'ImplTask'    -NotePropertyValue $taskText -Force
Set-WorkflowContext -Context $ctx

Write-Host "`n✅ Implementation complete. Run /3-qa to verify." -ForegroundColor Green
exit 0
