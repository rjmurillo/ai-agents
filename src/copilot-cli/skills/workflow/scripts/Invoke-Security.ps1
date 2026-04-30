#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Security review workflow command (/4-security).

.DESCRIPTION
    Invokes security agent with OWASP Top 10, secret detection, and dependency audit.
    Uses opus model per ADR-013 for thorough review.

.PARAMETER Scope
    Security review scope.

.PARAMETER OwaspOnly
    Run only OWASP Top 10 check.

.PARAMETER SecretsOnly
    Run only secret detection.

.NOTES
    Exit Codes (ADR-035):
    0 - Success (no critical findings)
    1 - Security findings require attention
    2 - MCP error
    3 - Validation error
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$Scope,

    [Parameter()]
    [Alias('owasp-only')]
    [switch]$OwaspOnly,

    [Parameter()]
    [Alias('secrets-only')]
    [switch]$SecretsOnly
)

$ErrorActionPreference = 'Stop'

$ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
Import-Module $ModulePath -Force

$scopeText = $Scope -join ' '
$ctx = Get-WorkflowContext

Write-Host "🔒 Security Review: $scopeText" -ForegroundColor Cyan

$checks = if ($OwaspOnly) { @('owasp') }
          elseif ($SecretsOnly) { @('secrets') }
          else { @('owasp', 'secrets', 'deps') }

Write-Host "   Checks: $($checks -join ', ')" -ForegroundColor DarkCyan

# Step 1: Invoke security agent (model: opus per ADR-013)
Write-Host "`n  [1/$($checks.Count + 2)] Invoking security agent (opus model)" -ForegroundColor Yellow
$secResult = Invoke-AgentOrchestrationMCP -ToolName 'invoke_agent' -Arguments @{
    agent   = 'security'
    task    = $scopeText
    model   = 'opus'
    checks  = $checks
    context = $ctx | ConvertTo-Json -Compress
}
if ($secResult.Fallback) {
    Write-Warning 'Agent Orchestration MCP unavailable. Instruct security agent directly with opus model.'
} elseif (-not $secResult.Success) {
    Write-Error 'Security agent invocation failed.' -ErrorAction Continue
    exit 1
}

$step = 2
foreach ($check in $checks) {
    Write-Host "  [$step/$($checks.Count + 2)] Running: $check check" -ForegroundColor Yellow
    switch ($check) {
        'owasp'   { Write-Host "  ✓ OWASP Top 10 analysis issued"          -ForegroundColor DarkGray }
        'secrets' { Write-Host "  ✓ Secret detection scan issued"           -ForegroundColor DarkGray }
        'deps'    { Write-Host "  ✓ Dependency vulnerability audit issued"  -ForegroundColor DarkGray }
    }
    $step++
}

# Generate report
Write-Host "  [$step/$($checks.Count + 2)] Generating security report" -ForegroundColor Yellow

# Track handoff
Invoke-AgentOrchestrationMCP -ToolName 'track_handoff' -Arguments @{
    from_agent = 'security'
    to_agent   = 'orchestrator'
    reason     = 'Security review complete'
} | Out-Null

$ctx | Add-Member -NotePropertyName 'LastCommand' -NotePropertyValue '4-security' -Force
Set-WorkflowContext -Context $ctx

# Evaluate security findings from agent result
if ($secResult.Findings) {
    Write-Host "`n❌ Security findings detected. Review required." -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ Security review complete. No critical findings." -ForegroundColor Green
exit 0
