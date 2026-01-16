<#
.SYNOPSIS
    Verifies install.ps1 output for a specific environment and scope.

.DESCRIPTION
    Validates that install.ps1 created the expected directories and files by
    comparing the configured source files against the resolved destination paths.
    Designed for CI file-based verification without CLI authentication.

.PARAMETER Environment
    Target environment: Claude, Copilot, or VSCode.

.PARAMETER Scope
    Installation scope: Global or Repo.

.PARAMETER RepoPath
    Repository path used for Repo scope resolution. Defaults to current directory.

.PARAMETER CI
    Exit with non-zero status when verification fails.

.EXAMPLE
    ./scripts/tests/Verify-InstallOutput.ps1 -Environment Claude -Scope Global -CI

.EXAMPLE
    ./scripts/tests/Verify-InstallOutput.ps1 -Environment Copilot -Scope Repo -RepoPath .
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("Claude", "Copilot", "VSCode")]
    [string]$Environment,

    [Parameter(Mandatory)]
    [ValidateSet("Global", "Repo")]
    [string]$Scope,

    [string]$RepoPath,

    [switch]$CI
)

$ErrorActionPreference = "Stop"

$ModulePath = Join-Path $PSScriptRoot "..\lib\Install-Common.psm1"
if (-not (Test-Path $ModulePath)) {
    Write-Host "[FAIL] Required module not found: $ModulePath" -ForegroundColor Red
    if ($CI) {
        exit 1
    }
    return $false
}

Import-Module $ModulePath -Force

if ($Scope -eq "Repo") {
    if (-not $RepoPath) {
        $RepoPath = (Get-Location).Path
    }
    $RepoPath = (Resolve-Path -Path $RepoPath -ErrorAction Stop).Path
}

$Config = Get-InstallConfig -Environment $Environment -Scope $Scope

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$SourceDir = Join-Path $RepoRoot $Config.SourceDir

$ExcludeFiles = @()
if ($Config.InstructionsFile) {
    $ExcludeFiles += $Config.InstructionsFile
}
if ($Config.ExcludeFiles) {
    $ExcludeFiles += $Config.ExcludeFiles
}

$Errors = New-Object System.Collections.Generic.List[string]

function Add-VerificationError {
    param([string]$Message)
    $Errors.Add($Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Test-ExpectedFile {
    param(
        [string]$Path,
        [string]$Label
    )
    if (-not (Test-Path $Path -PathType Leaf)) {
        Add-VerificationError "$Label missing: $Path"
    }
}

try {
    Test-SourceDirectory -Path $SourceDir | Out-Null
}
catch {
    Add-VerificationError $_.Exception.Message
}

$AgentFiles = @()
if ($Errors.Count -eq 0) {
    $AgentFiles = Get-AgentFiles -SourceDir $SourceDir -FilePattern $Config.FilePattern -ExcludeFiles $ExcludeFiles
}

$DestinationDir = Resolve-DestinationPath -PathExpression $Config.DestDir -RepoPath $RepoPath
if (-not $DestinationDir -or -not (Test-Path $DestinationDir -PathType Container)) {
    Add-VerificationError "Destination directory missing: $DestinationDir"
}
else {
    foreach ($File in $AgentFiles) {
        Test-ExpectedFile -Path (Join-Path $DestinationDir $File.Name) -Label "Agent file"
    }
}

if ($Config.CommandsDir -and $Config.CommandFiles) {
    $CommandsDir = Resolve-DestinationPath -PathExpression $Config.CommandsDir -RepoPath $RepoPath
    if (-not (Test-Path $CommandsDir -PathType Container)) {
        Add-VerificationError "Commands directory missing: $CommandsDir"
    }
    else {
        foreach ($CommandFile in $Config.CommandFiles) {
            Test-ExpectedFile -Path (Join-Path $CommandsDir $CommandFile) -Label "Command file"
        }
    }
}

if ($Config.PromptFiles -and $DestinationDir) {
    foreach ($PromptFile in $Config.PromptFiles) {
        $PromptFileName = $PromptFile -replace '\.agent\.md$', '.prompt.md'
        Test-ExpectedFile -Path (Join-Path $DestinationDir $PromptFileName) -Label "Prompt file"
    }
}

if ($Config.InstructionsFile -and $null -ne $Config.InstructionsDest) {
    $InstructionsDir = Resolve-DestinationPath -PathExpression $Config.InstructionsDest -RepoPath $RepoPath
    if ($InstructionsDir) {
        Test-ExpectedFile -Path (Join-Path $InstructionsDir $Config.InstructionsFile) -Label "Instructions file"
    }
}

if ($Config.Skills -and $Config.SkillsDir) {
    $SkillsDir = Resolve-DestinationPath -PathExpression $Config.SkillsDir -RepoPath $RepoPath
    if (-not (Test-Path $SkillsDir -PathType Container)) {
        Add-VerificationError "Skills directory missing: $SkillsDir"
    }
    else {
        foreach ($Skill in $Config.Skills) {
            $SkillPath = Join-Path $SkillsDir $Skill
            if (-not (Test-Path $SkillPath -PathType Container)) {
                Add-VerificationError "Skill directory missing: $SkillPath"
            }
        }
    }
}

if ($Scope -eq "Repo") {
    foreach ($AgentsDir in $Config.AgentsDirs) {
        $ResolvedDir = Resolve-DestinationPath -PathExpression $AgentsDir -RepoPath $RepoPath
        if (-not (Test-Path $ResolvedDir -PathType Container)) {
            Add-VerificationError "Agents directory missing: $ResolvedDir"
        }
    }
}

if ($Errors.Count -eq 0) {
    Write-Host "[PASS] Install verification succeeded." -ForegroundColor Green
    if ($CI) {
        exit 0
    }
    return $true
}

Write-Host "[FAIL] Install verification failed with $($Errors.Count) issue(s)." -ForegroundColor Red
if ($CI) {
    exit 1
}
return $false
