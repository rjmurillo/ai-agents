#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Workflow helper functions for Agent Orchestration MCP integration.

.DESCRIPTION
    Provides reusable functions for workflow commands:
    - MCP tool invocation wrappers
    - Workflow context management
    - MCP availability checks

.NOTES
    ADR-005: PowerShell-only scripting
    ADR-006: Thin workflows, testable modules
#>

$ErrorActionPreference = 'Stop'

<#
.SYNOPSIS
    Wrapper for Agent Orchestration MCP tool invocation.
.PARAMETER ToolName
    The MCP tool name (e.g., 'invoke_agent', 'track_handoff').
.PARAMETER Arguments
    Hashtable of arguments to pass to the tool.
.OUTPUTS
    PSCustomObject with tool result.
#>
function Invoke-AgentOrchestrationMCP {
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory)]
        [string]$ToolName,

        [Parameter()]
        [hashtable]$Arguments = @{}
    )

    if (-not (Test-MCPAvailability)) {
        Write-Warning "Agent Orchestration MCP unavailable. Falling back to direct invocation."
        return [PSCustomObject]@{
            Success   = $false
            Fallback  = $true
            ToolName  = $ToolName
            Arguments = $Arguments
        }
    }

    # In Claude Code context, MCP tools are invoked via their prefixed names.
    # This function documents the invocation pattern for the agent.
    Write-Verbose "Invoking MCP tool: $ToolName with arguments: $($Arguments | ConvertTo-Json -Compress)"

    return [PSCustomObject]@{
        Success   = $true
        ToolName  = $ToolName
        Arguments = $Arguments
    }
}

<#
.SYNOPSIS
    Retrieve current workflow state from context file.
.PARAMETER WorkflowContextPath
    Path to workflow context JSON file. Defaults to .agents/workflow-context.json.
.OUTPUTS
    PSCustomObject with workflow state, or empty object if not found.
#>
function Get-WorkflowContext {
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter()]
        [string]$WorkflowContextPath = '.agents/workflow-context.json'
    )

    if (Test-Path $WorkflowContextPath) {
        try {
            return Get-Content $WorkflowContextPath -Raw | ConvertFrom-Json
        }
        catch {
            Write-Warning "Failed to read workflow context: $_"
        }
    }

    return [PSCustomObject]@{
        SessionNumber   = $null
        LastCommand     = $null
        PlanningArtifacts = @()
        ImplArtifacts   = @()
        Branch          = $null
        Timestamp       = $null
    }
}

<#
.SYNOPSIS
    Update workflow state in context file.
.PARAMETER Context
    PSCustomObject with workflow state to persist.
.PARAMETER WorkflowContextPath
    Path to workflow context JSON file. Defaults to .agents/workflow-context.json.
#>
function Set-WorkflowContext {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [PSCustomObject]$Context,

        [Parameter()]
        [string]$WorkflowContextPath = '.agents/workflow-context.json'
    )

    $Context.Timestamp = (Get-Date -Format 'o')

    $dir = Split-Path $WorkflowContextPath -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $Context | ConvertTo-Json -Depth 10 | Set-Content $WorkflowContextPath -Encoding UTF8
    Write-Verbose "Workflow context saved to $WorkflowContextPath"
}

<#
.SYNOPSIS
    Check if Agent Orchestration MCP is available.
.OUTPUTS
    Boolean indicating MCP availability.
#>
function Test-MCPAvailability {
    [CmdletBinding()]
    [OutputType([bool])]
    param()

    # Check for MCP environment indicators
    $mcpEnv = $env:AGENT_ORCHESTRATION_MCP_URL
    if ($mcpEnv) {
        return $true
    }

    # Check for MCP config in .claude/
    $mcpConfig = '.claude/mcp-config.json', '.mcp.json', 'mcp.json' |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1

    return ($null -ne $mcpConfig)
}

Export-ModuleMember -Function @(
    'Invoke-AgentOrchestrationMCP',
    'Get-WorkflowContext',
    'Set-WorkflowContext',
    'Test-MCPAvailability'
)
