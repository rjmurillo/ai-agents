<#
.SYNOPSIS
    Checks if a skill script exists for the specified operation and action.

.DESCRIPTION
    Self-documenting tool that discovers skills via file system scan.
    Used by Phase 1.5 BLOCKING gate to verify skill availability before operations.

.PARAMETER Operation
    The operation type: pr, issue, reactions, label, milestone

.PARAMETER Action
    The action name to check for (uses substring matching)

.PARAMETER ListAvailable
    Lists all available skills instead of checking for a specific one

.EXAMPLE
    .\Check-SkillExists.ps1 -Operation "pr" -Action "PRContext"
    Returns: $true (if .claude/skills/github/scripts/pr/*PRContext*.ps1 exists)

.EXAMPLE
    .\Check-SkillExists.ps1 -ListAvailable
    Lists all available skill scripts organized by operation type
#>
[CmdletBinding()]
param(
    [Parameter(ParameterSetName = 'Check')]
    [ValidateSet('pr', 'issue', 'reactions', 'label', 'milestone')]
    [string]$Operation,

    [Parameter(ParameterSetName = 'Check')]
    [string]$Action,

    [Parameter(ParameterSetName = 'List')]
    [switch]$ListAvailable
)

$skillBasePath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts"

if ($ListAvailable) {
    $operations = @('pr', 'issue', 'reactions', 'label', 'milestone')
    foreach ($op in $operations) {
        $opPath = Join-Path $skillBasePath $op
        if (Test-Path $opPath) {
            Write-Output "`n=== $op ==="
            Get-ChildItem -Path $opPath -Filter "*.ps1" | ForEach-Object {
                Write-Output "  - $($_.BaseName)"
            }
        }
    }
    return
}

if (-not $Operation -or -not $Action) {
    Write-Error "Both -Operation and -Action are required when not using -ListAvailable"
    return $false
}

$searchPath = Join-Path $skillBasePath $Operation
if (-not (Test-Path $searchPath)) {
    return $false
}

$matchingScripts = Get-ChildItem -Path $searchPath -Filter "*$Action*.ps1" -ErrorAction SilentlyContinue
return ($null -ne $matchingScripts -and $matchingScripts.Count -gt 0)
