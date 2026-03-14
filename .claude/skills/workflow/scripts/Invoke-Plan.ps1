#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Planning phase workflow command (/1-plan).

.DESCRIPTION
    Routes task to appropriate planning agent:
    - Default: planner agent
    - --arch:     architect agent
    - --strategic: roadmap → high-level-advisor chain

.PARAMETER Task
    Task description to plan.

.PARAMETER Arch
    Use architect agent for design decisions.

.PARAMETER Strategic
    Chain roadmap → high-level-advisor agents.

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
    [switch]$Arch,

    [Parameter()]
    [switch]$Strategic
)

$ErrorActionPreference = 'Stop'

$ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
Import-Module $ModulePath -Force

$taskText = $Task -join ' '

if ([string]::IsNullOrWhiteSpace($taskText)) {
    Write-Host 'Task description is required. Usage: /1-plan [--arch] [--strategic] <task>' -ForegroundColor Red
    exit 3
}

# Determine routing
if ($Strategic) {
    $agentChain = @('roadmap', 'high-level-advisor')
    $routeDesc  = 'Strategic: roadmap → high-level-advisor'
}
elseif ($Arch) {
    $agentChain = @('architect')
    $routeDesc  = 'Architecture: architect'
}
else {
    $agentChain = @('planner')
    $routeDesc  = 'Default: planner'
}

Write-Host "🎯 Planning: $taskText" -ForegroundColor Cyan
Write-Host "   Route: $routeDesc" -ForegroundColor DarkCyan

# Load workflow context from /0-init
$ctx = Get-WorkflowContext

# Invoke agents in chain
$previousResult = $null
foreach ($agent in $agentChain) {
    Write-Host "`n  → Invoking: $agent" -ForegroundColor Yellow

    $invokeArgs = @{
        agent   = $agent
        task    = $taskText
        context = $ctx | ConvertTo-Json -Compress
    }
    if ($previousResult) {
        $invokeArgs['prior_output'] = $previousResult | ConvertTo-Json -Compress
    }

    $result = Invoke-AgentOrchestrationMCP -ToolName 'invoke_agent' -Arguments $invokeArgs
    if ($result.Fallback) {
        Write-Warning "Agent Orchestration MCP unavailable. Instruct agent '$agent' directly."
    }

    # Track handoff between agents
    if ($agentChain.Count -gt 1 -and $agent -ne $agentChain[-1]) {
        $nextAgent = $agentChain[$agentChain.IndexOf($agent) + 1]
        Invoke-AgentOrchestrationMCP -ToolName 'track_handoff' -Arguments @{
            from_agent = $agent
            to_agent   = $nextAgent
            reason     = "Strategic planning chain"
        } | Out-Null
    }

    $previousResult = $result
}

# Update workflow context
$ctx | Add-Member -NotePropertyName 'LastCommand'        -NotePropertyValue '1-plan'   -Force
$ctx | Add-Member -NotePropertyName 'PlanningAgent'      -NotePropertyValue $agentChain[-1] -Force
$ctx | Add-Member -NotePropertyName 'PlanningTask'       -NotePropertyValue $taskText  -Force
Set-WorkflowContext -Context $ctx

Write-Host "`n✅ Planning complete. Run /2-impl <task> to implement." -ForegroundColor Green
exit 0
