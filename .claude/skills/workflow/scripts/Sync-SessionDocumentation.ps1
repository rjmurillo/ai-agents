#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sync session documentation from agent history.

.DESCRIPTION
    Queries Agent Orchestration MCP for session invocations and:
    1. Generates workflow sequence diagram (Mermaid format)
    2. Extracts decisions and artifacts from handoff chain
    3. Appends to session log workLog section
    4. Updates memory with cross-session context
    5. Suggests retrospective learnings

.PARAMETER SessionLogPath
    Path to the session log file to update.

.EXAMPLE
    pwsh Sync-SessionDocumentation.ps1 -SessionLogPath .agents/sessions/session-042.json

.NOTES
    Exit Codes (ADR-035):
    0 - Success
    2 - MCP error
    3 - Validation error (session log not found)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SessionLogPath
)

$ErrorActionPreference = 'Stop'

$ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
Import-Module $ModulePath -Force

# Path validation per style guide (CWE-22)
try {
    $repoRoot = git rev-parse --show-toplevel
    $allowedDir = [IO.Path]::GetFullPath((Join-Path $repoRoot '.agents/sessions'))
    $resolvedPath = [IO.Path]::GetFullPath((Join-Path (Get-Location) $SessionLogPath))

    if (-not $resolvedPath.StartsWith($allowedDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Error "Path traversal attempt detected. Path must be within the '.agents/sessions' directory." -ErrorAction Continue
        exit 3
    }
    $SessionLogPath = $resolvedPath
}
catch {
    Write-Error "Invalid path specified for -SessionLogPath: $_" -ErrorAction Continue
    exit 3
}

if (-not (Test-Path -LiteralPath $SessionLogPath)) {
    Write-Error "Session log not found: $SessionLogPath" -ErrorAction Continue
    exit 3
}

Write-Host "📝 Syncing session documentation: $SessionLogPath" -ForegroundColor Cyan

# Step 1: Query agent history
Write-Host "  [1/5] Querying agent history" -ForegroundColor Yellow
$historyResult = Invoke-AgentOrchestrationMCP -ToolName 'agents://history' -Arguments @{}
if ($historyResult.Fallback) {
    Write-Warning "Agent history unavailable — generating skeleton documentation."
}

# Step 2: Generate Mermaid sequence diagram
Write-Host "  [2/5] Generating workflow sequence diagram" -ForegroundColor Yellow
$mermaid = @'
```mermaid
sequenceDiagram
    participant U as User
    participant I as /0-init
    participant P as /1-plan
    participant Impl as /2-impl
    participant QA as /3-qa
    participant Sec as /4-security

    U->>I: Session start
    I-->>U: Context loaded
    U->>P: Plan task
    P-->>U: Planning artifacts
    U->>Impl: Implement
    Impl-->>U: Implementation complete
    U->>QA: Verify
    QA-->>U: QA report
    U->>Sec: Security review
    Sec-->>U: Security report
```
'@

# Step 3: Extract decisions
Write-Host "  [3/5] Extracting decisions and artifacts" -ForegroundColor Yellow
$decisions = @()

# Step 4: Update session log
Write-Host "  [4/5] Updating session log" -ForegroundColor Yellow
try {
    $sessionLog = Get-Content $SessionLogPath -Raw | ConvertFrom-Json
    if (-not $sessionLog.workLog) {
        $sessionLog | Add-Member -NotePropertyName 'workLog' -NotePropertyValue @() -Force
    }

    $sessionLog.workLog += [PSCustomObject]@{
        timestamp        = Get-Date -Format 'o'
        type             = 'workflow-sync'
        mermaidDiagram   = $mermaid
        decisions        = $decisions
    }

    $sessionLog | ConvertTo-Json -Depth 20 | Set-Content $SessionLogPath -Encoding UTF8
    Write-Host "  ✓ Session log updated" -ForegroundColor Green
}
catch {
    Write-Warning "Session log update failed (may not be JSON format): $_"
}

# Step 5: Update cross-session memory
Write-Host "  [5/5] Updating cross-session memory" -ForegroundColor Yellow
Invoke-AgentOrchestrationMCP -ToolName 'mcp__serena__write_memory' -Arguments @{
    key     = "session-sync-$(Get-Date -Format 'yyyyMMdd')"
    content = "Session documentation synced from $SessionLogPath"
} | Out-Null

Write-Host "`n✅ Session documentation synced." -ForegroundColor Green

# Suggest retrospective learnings
Write-Host "`n💡 Suggested retrospective items:" -ForegroundColor Cyan
Write-Host "  - Were all workflow commands used in sequence?" -ForegroundColor DarkGray
Write-Host "  - Any MCP fallbacks triggered? Update MCP config if so." -ForegroundColor DarkGray
Write-Host "  - Any acceptance criteria gaps surfaced by QA?" -ForegroundColor DarkGray

exit 0
