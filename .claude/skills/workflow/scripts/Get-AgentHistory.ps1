<#
.SYNOPSIS
    Retrieves agent invocation history from session logs and git history.

.DESCRIPTION
    Get-AgentHistory.ps1 queries session logs (JSON) and git commit history
    to build a timeline of agent invocations. When Agent Orchestration MCP
    (agents://history) is available, it will be the primary source. Until then,
    this script uses heuristic detection from git and session artifacts.

.PARAMETER LookbackHours
    How many hours to look back. Default: 8.

.PARAMETER Format
    Output format: 'json' or 'table'. Default: 'json'.

.EXAMPLE
    pwsh .claude/skills/workflow/scripts/Get-AgentHistory.ps1
    pwsh .claude/skills/workflow/scripts/Get-AgentHistory.ps1 -LookbackHours 24 -Format table

.NOTES
    Follows ADR-005 (PowerShell-only scripting).
    Future: integrate with Agent Orchestration MCP agents://history resource.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [int]$LookbackHours = 8,

    [Parameter()]
    [ValidateSet('json', 'table')]
    [string]$Format = 'json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    Write-Error "Not inside a git repository."
    exit 1
}

# Agent detection patterns
$agentPatterns = @{
    'orchestrator'        = @('orchestrat', 'routing', 'dispatch')
    'planner'             = @('plan', 'milestone', 'breakdown')
    'implementer'         = @('implement', 'feat:', 'fix:', 'refactor:')
    'qa'                  = @('test:', 'qa', 'validation', 'coverage')
    'security'            = @('security', 'cwe', 'owasp', 'vulnerability')
    'architect'           = @('architect', 'adr', 'design')
    'critic'              = @('critic', 'critique', 'blocker')
    'devops'              = @('ci:', 'cd:', 'workflow', 'deploy', 'devops')
    'analyst'             = @('analysis', 'research', 'rca', 'root cause')
    'explainer'           = @('docs:', 'prd', 'documentation', 'explainer')
    'retrospective'       = @('retrospective', 'learning', 'retro')
    'memory'              = @('memory', 'serena', 'forgetful')
    'merge-resolver'      = @('merge', 'conflict', 'resolution')
}

$since = (Get-Date).AddHours(-$LookbackHours).ToString('yyyy-MM-ddTHH:mm:ss')
$logOutput = git log --since="$since" --format='%H|%s|%ai' 2>$null

$history = @()
$order = 1

foreach ($line in $logOutput) {
    if (-not $line -or -not $line.Trim()) { continue }
    $parts = $line -split '\|', 3
    if ($parts.Count -lt 2) { continue }

    $hash = $parts[0].Substring(0, [Math]::Min(8, $parts[0].Length))
    $message = $parts[1]
    $timestamp = if ($parts.Count -ge 3) { $parts[2] } else { '' }

    $detectedAgents = @()
    $msgLower = $message.ToLower()

    foreach ($kv in $agentPatterns.GetEnumerator()) {
        foreach ($pattern in $kv.Value) {
            if ($msgLower -match [regex]::Escape($pattern)) {
                $detectedAgents += $kv.Key
                break
            }
        }
    }

    if ($detectedAgents.Count -gt 0) {
        foreach ($agent in ($detectedAgents | Select-Object -Unique)) {
            $history += [PSCustomObject]@{
                Order     = $order
                Agent     = $agent
                Commit    = $hash
                Message   = $message
                Timestamp = $timestamp
            }
            $order++
        }
    }
}

# Output
if ($Format -eq 'table') {
    $history | Format-Table -AutoSize
} else {
    $history | ConvertTo-Json -Depth 3
}
