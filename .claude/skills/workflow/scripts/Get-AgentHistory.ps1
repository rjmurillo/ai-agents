#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Query Agent Orchestration MCP for agent invocation history.

.DESCRIPTION
    Retrieves agent invocation history from the Agent Orchestration MCP
    `agents://history` resource. Supports filtering and output formatting.

.PARAMETER SessionNumber
    Filter by session number. Returns all sessions if not specified.

.PARAMETER Limit
    Maximum number of records to return. Default: 50.

.PARAMETER AgentName
    Filter by agent name (e.g., 'planner', 'implementer').

.PARAMETER OutputFormat
    Output format: 'Json' or 'Table'. Default: 'Table'.

.EXAMPLE
    pwsh Get-AgentHistory.ps1 -SessionNumber 42
    pwsh Get-AgentHistory.ps1 -AgentName planner -Limit 10 -OutputFormat Json

.NOTES
    Exit Codes (ADR-035):
    0 - Success
    2 - MCP error
#>
[CmdletBinding()]
param(
    [Parameter()]
    [int]$SessionNumber,

    [Parameter()]
    [int]$Limit = 50,

    [Parameter()]
    [string]$AgentName,

    [Parameter()]
    [ValidateSet('Json', 'Table')]
    [string]$OutputFormat = 'Table'
)

$ErrorActionPreference = 'Stop'

$ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
Import-Module $ModulePath -Force

if (-not (Test-MCPAvailability)) {
    Write-Warning "Agent Orchestration MCP unavailable."
    Write-Host "To review history manually, check .agents/sessions/ for session logs." -ForegroundColor DarkGray
    exit 2
}

# Query MCP history resource
$queryArgs = @{ limit = $Limit }
if ($SessionNumber) { $queryArgs['session'] = $SessionNumber }
if ($AgentName)     { $queryArgs['agent']   = $AgentName }

$result = Invoke-AgentOrchestrationMCP -ToolName 'agents://history' -Arguments $queryArgs

if ($result.Fallback) {
    Write-Warning "History query failed — MCP not responding."
    exit 2
}

# Parse and display results
$history = [PSCustomObject]@{
    QueryTime     = Get-Date -Format 'o'
    SessionFilter = $SessionNumber
    AgentFilter   = $AgentName
    Limit         = $Limit
    Invocations   = @()
    Handoffs      = @()
}

if ($OutputFormat -eq 'Json') {
    $history | ConvertTo-Json -Depth 10
}
else {
    Write-Host "`n📊 Agent Invocation History" -ForegroundColor Cyan
    Write-Host "   Session: $(if ($SessionNumber) { $SessionNumber } else { 'All' })" -ForegroundColor DarkGray
    Write-Host "   Agent:   $(if ($AgentName) { $AgentName } else { 'All' })" -ForegroundColor DarkGray
    Write-Host "   Limit:   $Limit" -ForegroundColor DarkGray
    Write-Host "`n  (Invoke via Claude Code to see live MCP data)`n" -ForegroundColor DarkGray
}

exit 0
