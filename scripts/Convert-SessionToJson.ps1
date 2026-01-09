<#
.SYNOPSIS
  Migrates markdown session logs to JSON format (wrapper for skill version).

.DESCRIPTION
  This script delegates to the session-migration skill for the actual conversion logic.
  The skill version has additional features like work log parsing.

.PARAMETER Path
  Path to markdown session log file or directory of logs.

.PARAMETER Force
  Overwrite existing JSON files.

.PARAMETER DryRun
  Show what would be migrated without writing files.

.OUTPUTS
  Array of migrated file paths.

.NOTES
  The actual implementation is in .claude/skills/session-migration/scripts/Convert-SessionToJson.ps1
  This wrapper exists for backward compatibility with workflows.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [string]$Path,

  [switch]$Force,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Get script directory and navigate to repo root
$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent $scriptDir

# Delegate to skill version
$skillScript = Join-Path $repoRoot '.claude/skills/session-migration/scripts/Convert-SessionToJson.ps1'

if (-not (Test-Path $skillScript)) {
  Write-Error "Skill script not found: $skillScript"
  Write-Error "This script delegates to the session-migration skill. Ensure the skill is present."
  exit 1
}

# Forward all parameters
$params = @{ Path = $Path }
if ($Force) { $params.Force = $true }
if ($DryRun) { $params.DryRun = $true }

& $skillScript @params
