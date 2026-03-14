#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Session initialization workflow command (/0-init).

.DESCRIPTION
    Enforces ADR-007 memory-first architecture at session start:
    1. Activate Serena project
    2. Load initial instructions from AGENTS.md
    3. Read HANDOFF.md (read-only reference)
    4. Query relevant memories
    5. Create session log
    6. Declare current branch
    7. Record evidence to Session State MCP if available

.PARAMETER SessionNumber
    Session number. Auto-detected if not provided.

.PARAMETER Objective
    Session objective. Derived from branch if not provided.

.EXAMPLE
    pwsh .claude/skills/workflow/scripts/Invoke-Init.ps1
    pwsh .claude/skills/workflow/scripts/Invoke-Init.ps1 --session-number 42 --objective "Implement feature X"

.NOTES
    Exit Codes (ADR-035):
    0 - Success
    1 - Git error
    2 - MCP error
    3 - Validation error
#>
[CmdletBinding()]
param(
    [Parameter()]
    [Alias('session-number')]
    [string]$SessionNumber,

    [Parameter()]
    [string]$Objective
)

$ErrorActionPreference = 'Stop'

$ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
Import-Module $ModulePath -Force

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host "[$Step] $Message" -ForegroundColor Cyan
}

function Write-StepResult {
    param([string]$Status, [string]$Message)
    $color = if ($Status -eq 'OK') { 'Green' } elseif ($Status -eq 'WARN') { 'Yellow' } else { 'Red' }
    Write-Host "  → [$Status] $Message" -ForegroundColor $color
}

# Step 1: Activate Serena project
Write-Step '1/7' 'Activating Serena project'
$mcpResult = Invoke-AgentOrchestrationMCP -ToolName 'activate_project' -Arguments @{}
if ($mcpResult.Fallback) {
    Write-StepResult 'WARN' 'Agent Orchestration MCP unavailable — skipping project activation'
}
else {
    Write-StepResult 'OK' 'Project context activated'
}

# Step 2: Load initial instructions
Write-Step '2/7' 'Loading initial instructions from AGENTS.md'
$agentsPath = 'AGENTS.md'
if (Test-Path $agentsPath) {
    $agentsContent = Get-Content $agentsPath -Raw
    Write-StepResult 'OK' "AGENTS.md loaded ($($agentsContent.Length) chars)"
}
else {
    Write-StepResult 'WARN' 'AGENTS.md not found'
}

# Step 3: Read HANDOFF.md
Write-Step '3/7' 'Reading HANDOFF.md'
$handoffPath = 'HANDOFF.md'
if (Test-Path $handoffPath) {
    Write-StepResult 'OK' 'HANDOFF.md found — prior session context available'
}
else {
    Write-StepResult 'WARN' 'HANDOFF.md not found — starting fresh'
}

# Step 4: Query relevant memories
Write-Step '4/7' 'Querying relevant memories'
$memResult = Invoke-AgentOrchestrationMCP -ToolName 'query_memories' -Arguments @{}
if ($memResult.Fallback) {
    Write-StepResult 'WARN' 'Memory query skipped — Agent Orchestration MCP unavailable'
}
else {
    Write-StepResult 'OK' 'Memory query issued'
}

# Step 5: Create session log
Write-Step '5/7' 'Creating session log'
$sessionInitScript = '.claude/skills/session-init/scripts/New-SessionLog.ps1'
if (Test-Path $sessionInitScript) {
    $initArgs = @()
    if ($SessionNumber) { $initArgs += '--session-number', $SessionNumber }
    if ($Objective)     { $initArgs += '--objective', $Objective }

    try {
        & pwsh $sessionInitScript @initArgs
        Write-StepResult 'OK' 'Session log created'
    }
    catch {
        Write-StepResult 'FAIL' "Session log creation failed: $_"
        exit 3
    }
}
else {
    Write-StepResult 'WARN' "Session init script not found at $sessionInitScript"
}

# Step 6: Declare current branch
Write-Step '6/7' 'Detecting current branch'
try {
    $branch = git branch --show-current 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-StepResult 'FAIL' "Git error: $branch"
        exit 1
    }
    Write-StepResult 'OK' "Branch: $branch"
}
catch {
    Write-StepResult 'FAIL' "Git not available: $_"
    exit 1
}

# Step 7: Record evidence to Session State MCP
Write-Step '7/7' 'Recording session evidence'
$evidenceResult = Invoke-AgentOrchestrationMCP -ToolName 'record_evidence' -Arguments @{
    command   = '0-init'
    branch    = $branch
    timestamp = (Get-Date -Format 'o')
}
if ($evidenceResult.Fallback) {
    Write-StepResult 'WARN' 'Agent Orchestration MCP unavailable — evidence not recorded'
}
else {
    Write-StepResult 'OK' 'Evidence recorded'
}

# Persist workflow context for downstream commands
$ctx = Get-WorkflowContext
$ctx | Add-Member -NotePropertyName 'SessionNumber' -NotePropertyValue $SessionNumber -Force
$ctx | Add-Member -NotePropertyName 'LastCommand'   -NotePropertyValue '0-init'       -Force
$ctx | Add-Member -NotePropertyName 'Branch'        -NotePropertyValue $branch        -Force
Set-WorkflowContext -Context $ctx

Write-Host "`n✅ Session initialized. Run /1-plan <task> to begin planning." -ForegroundColor Green
exit 0
