#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create protocol-compliant JSON session log with verification-based enforcement

.DESCRIPTION
    Automates JSON session log creation by:
    1. Auto-detecting or prompting for session number and objective
    2. Detecting date/branch/commit/git status
    3. Generating JSON structure with schemaVersion field
    4. Writing JSON file to .agents/sessions/
    5. Validating with JSON schema + Validate-SessionJson.ps1
    6. Exiting nonzero on validation failure

    Autonomous Operation:
    - If SessionNumber not provided: Auto-increments from latest session
    - If Objective not provided: Derives from branch name or recent commits

.PARAMETER SessionNumber
    Session number (e.g., 375). If not provided, auto-increments from latest.

.PARAMETER Objective
    Session objective. If not provided, derives from branch/commits or prompts.

.PARAMETER SkipValidation
    Skip validation after creating session log. Use for testing only.

.OUTPUTS
    Session log file path on success

.EXAMPLE
    & .claude/skills/session-init/scripts/New-SessionLog.ps1
    Auto-increments session number and derives objective from branch

.EXAMPLE
    & .claude/skills/session-init/scripts/New-SessionLog.ps1 -SessionNumber 375 -Objective "Implement session-init skill"
    Creates session log with provided values

.NOTES
    Exit Codes:
    - 0: Success (session log created and validated)
    - 1: Git repository error
    - 2: Session log write failed
    
    See: ADR-035 Exit Code Standardization
    - 3: JSON schema validation failed
    - 4: Script validation failed
#>

[CmdletBinding()]
param(
    [Parameter()]
    [int]$SessionNumber,

    [Parameter()]
    [string]$Objective,

    [Parameter()]
    [switch]$SkipValidation
)

$ErrorActionPreference = 'Stop'

# Import shared modules
$ScriptDir = Split-Path -Parent $PSCommandPath
Import-Module (Join-Path $ScriptDir "../modules/GitHelpers.psm1") -Force
Import-Module (Join-Path $ScriptDir "../modules/TemplateHelpers.psm1") -Force

#region Helper Functions

# Note: Get-GitInfo is provided by GitHelpers.psm1 module
# Note: Get-DescriptiveKeywords is provided by TemplateHelpers.psm1 module

function Get-UserInput {
    <#
    .SYNOPSIS
        Gather session details with autonomous input detection
    .DESCRIPTION
        Autonomous behavior when parameters not provided:
        - SessionNumber: Auto-increments from latest session in .agents/sessions/
        - Objective: Derives from branch name or recent commit messages
        Falls back to interactive prompts if autonomous detection fails
    .NOTES
        Throws:
        - InvalidOperationException: Cannot prompt in non-interactive terminal
    #>
    param(
        [Parameter()]
        [int]$SessionNumber,

        [Parameter()]
        [string]$Objective,

        [Parameter(Mandatory)]
        [string]$RepoRoot,

        [Parameter(Mandatory)]
        [string]$Branch
    )

    # Autonomous session number detection
    if (-not $SessionNumber) {
        try {
            $sessionDir = Join-Path $RepoRoot ".agents/sessions"
            if (Test-Path $sessionDir) {
                $latestSession = Get-ChildItem $sessionDir -Filter "*.json" |
                    Where-Object { $_.Name -match 'session-(\d+)' } |
                    ForEach-Object { [int]$Matches[1] } |
                    Sort-Object -Descending |
                    Select-Object -First 1

                if ($latestSession) {
                    $SessionNumber = $latestSession + 1
                    Write-Verbose "Auto-incremented session number to $SessionNumber (latest: $latestSession)"
                }
            }
        } catch {
            Write-Warning "Failed to auto-detect session number: $($_.Exception.Message)"
        }
    }

    # Autonomous objective derivation
    if (-not $Objective) {
        try {
            # Try to derive from branch name (e.g., "feat/session-init" -> "Work on session-init")
            if ($Branch -and $Branch -match '^(?:feat|feature|fix|refactor|chore|docs)/(.+)$') {
                $branchTopic = $Matches[1] -replace '-', ' '
                $Objective = "Work on $branchTopic"
                Write-Verbose "Derived objective from branch: $Objective"
            }
            # Try to derive from recent commit messages if branch derivation failed
            elseif ($Branch) {
                try {
                    $recentCommits = git log --oneline -3 2>&1 | Out-String
                    if ($LASTEXITCODE -eq 0 -and $recentCommits) {
                        # Extract first commit subject (most relevant)
                        $firstCommit = ($recentCommits -split "`n")[0]
                        if ($firstCommit -match '^\w+\s+(.+)$') {
                            $commitSubject = $Matches[1].Trim()
                            $Objective = "Continue: $commitSubject"
                            Write-Verbose "Derived objective from commit: $Objective"
                        }
                    }
                } catch {
                    Write-Verbose "Failed to derive objective from commits: $($_.Exception.Message)"
                }
            }
        } catch {
            Write-Warning "Failed to auto-derive objective: $($_.Exception.Message)"
        }
    }

    # Fall back to prompts if autonomous detection failed and interactive terminal available
    $needsPrompt = (-not $SessionNumber) -or (-not $Objective)
    if ($needsPrompt) {
        # Detect non-interactive terminal
        if (-not [Environment]::UserInteractive) {
            throw [System.InvalidOperationException]::new(
                "Cannot prompt for input in non-interactive terminal and autonomous detection failed.`n`nProvide required parameters:`n  -SessionNumber <number>`n  -Objective `"<description>`"`n`nExample:`n  pwsh New-SessionLog.ps1 -SessionNumber 375 -Objective `"Implement feature X`""
            )
        }

        # Additional check for stdin availability (CI/CD environments)
        try {
            $null = [Console]::KeyAvailable
        } catch {
            throw [System.InvalidOperationException]::new(
                "Console input not available (running in CI/CD or redirected stdin?) and autonomous detection failed.`n`nProvide required parameters:`n  -SessionNumber <number>`n  -Objective `"<description>`""
            )
        }
    }

    try {
        if (-not $SessionNumber) {
            do {
                $input = Read-Host "Enter session number (e.g., 375)"
                $parsed = 0
                $valid = [int]::TryParse($input, [ref]$parsed)
                if (-not $valid -or $parsed -le 0) {
                    Write-Host "Invalid number. Please enter a positive integer." -ForegroundColor Yellow
                }
            } while (-not $valid -or $parsed -le 0)
            $SessionNumber = $parsed
        }

        if (-not $Objective) {
            do {
                $Objective = Read-Host "Enter session objective (e.g., 'Implement session-init skill')"
                if ([string]::IsNullOrWhiteSpace($Objective)) {
                    Write-Host "Objective cannot be empty. Please provide a description." -ForegroundColor Yellow
                }
            } while ([string]::IsNullOrWhiteSpace($Objective))
        }

        return @{
            SessionNumber = $SessionNumber
            Objective = $Objective.Trim()
        }
    } catch [System.InvalidOperationException] {
        # Re-throw InvalidOperationException from non-interactive detection
        throw
    } catch {
        throw [System.InvalidOperationException]::new(
            "Failed to read user input. Stdin may be closed or redirected.`n`nUse parameters instead:`n  -SessionNumber <number>`n  -Objective `"<description>`"",
            $_.Exception
        )
    }
}

function New-JsonSessionLog {
    <#
    .SYNOPSIS
        Create JSON session log with structured data
    .DESCRIPTION
        Generates JSON structure with schemaVersion field and protocol compliance
        checklist. Writes directly to .agents/sessions/ with descriptive filename.
    .NOTES
        Throws:
        - UnauthorizedAccessException: Permission denied
        - IOException: Disk full or file in use
        - PathTooLongException: Path exceeds OS limits
    #>
    param(
        [Parameter(Mandatory)]
        [hashtable]$GitInfo,

        [Parameter(Mandatory)]
        [hashtable]$UserInput,

        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $currentDate = Get-Date -Format "yyyy-MM-dd"
    $sessionDir = Join-Path $RepoRoot ".agents/sessions"

    # Create directory with explicit error handling
    if (-not (Test-Path $sessionDir)) {
        try {
            $null = New-Item -ItemType Directory -Path $sessionDir -Force -ErrorAction Stop
            Write-Verbose "Created directory: $sessionDir"
        } catch [System.UnauthorizedAccessException] {
            throw [System.UnauthorizedAccessException]::new(
                "Permission denied creating directory: $sessionDir`n`nEnsure you have write permissions to the .agents/ folder.",
                $_.Exception
            )
        } catch [System.IO.IOException] {
            throw [System.IO.IOException]::new(
                "Failed to create directory: $sessionDir`n`nPossible causes: disk full, corrupted filesystem, or path conflicts.",
                $_.Exception
            )
        }
    }

    # Generate descriptive filename
    $keywords = Get-DescriptiveKeywords -Objective $UserInput.Objective
    $keywordSuffix = if ($keywords) { "-$keywords" } else { "" }
    $fileName = "$currentDate-session-$($UserInput.SessionNumber)$keywordSuffix.json"
    $filePath = Join-Path $sessionDir $fileName

    # Create JSON structure with schema version
    $sessionData = @{
        schemaVersion = "1.0"
        session = @{
            number = $UserInput.SessionNumber
            date = $currentDate
            branch = $GitInfo.Branch
            startingCommit = $GitInfo.Commit
            objective = $UserInput.Objective
        }
        protocolCompliance = @{
            sessionStart = @{
                serenaActivated = @{ Complete = $false; level = "MUST"; Evidence = "" }
                serenaInstructions = @{ Complete = $false; level = "MUST"; Evidence = "" }
                handoffRead = @{ Complete = $false; level = "MUST"; Evidence = "" }
                sessionLogCreated = @{ Complete = $true; level = "MUST"; Evidence = "This file exists" }
                skillScriptsListed = @{ Complete = $false; level = "MUST"; Evidence = "" }
                usageMandatoryRead = @{ Complete = $false; level = "MUST"; Evidence = "" }
                constraintsRead = @{ Complete = $false; level = "MUST"; Evidence = "" }
                memoriesLoaded = @{ Complete = $false; level = "MUST"; Evidence = "" }
                branchVerified = @{ Complete = $true; level = "MUST"; Evidence = "Branch: $($GitInfo.Branch)" }
                notOnMain = @{ Complete = ($GitInfo.Branch -ne 'main' -and $GitInfo.Branch -ne 'master'); level = "MUST"; Evidence = "" }
                gitStatusVerified = @{ Complete = $false; level = "SHOULD"; Evidence = "" }
                startingCommitNoted = @{ Complete = $true; level = "SHOULD"; Evidence = "SHA: $($GitInfo.Commit)" }
            }
            sessionEnd = @{
                checklistComplete = @{ Complete = $false; level = "MUST"; Evidence = "" }
                serenaMemoryUpdated = @{ Complete = $false; level = "MUST"; Evidence = "" }
                markdownLintRun = @{ Complete = $false; level = "MUST"; Evidence = "" }
                changesCommitted = @{ Complete = $false; level = "MUST"; Evidence = "" }
                validationPassed = @{ Complete = $false; level = "MUST"; Evidence = "" }
                handoffNotUpdated = @{ Complete = $false; level = "MUST NOT"; Evidence = "" }
                tasksUpdated = @{ Complete = $false; level = "SHOULD"; Evidence = "" }
                retrospectiveInvoked = @{ Complete = $false; level = "SHOULD"; Evidence = "" }
            }
        }
        workLog = @()
        endingCommit = ""
        nextSteps = @()
    }

    try {
        # Convert to JSON with depth for nested structures
        $json = $sessionData | ConvertTo-Json -Depth 10

        # Write JSON to file
        $json | Out-File -FilePath $filePath -Encoding utf8 -NoNewline -ErrorAction Stop

        # Verify file was created and has content
        if (-not (Test-Path $filePath)) {
            throw [System.IO.IOException]::new(
                "File was not created at expected path: $filePath"
            )
        }

        $fileInfo = Get-Item $filePath -ErrorAction Stop
        if ($fileInfo.Length -eq 0) {
            throw [System.IO.IOException]::new(
                "Session log file was created but is empty: $filePath"
            )
        }

        Write-Verbose "Session log written: $filePath ($($fileInfo.Length) bytes)"
        return $filePath

    } catch [System.UnauthorizedAccessException] {
        Write-Error "Permission denied writing session log to: $filePath"
        exit 2
    } catch [System.IO.PathTooLongException] {
        Write-Error "Path too long for session log file: $filePath"
        Write-Error "File path length: $($filePath.Length) characters"
        exit 2
    } catch [System.IO.IOException] {
        Write-Error "File I/O error writing session log to: $filePath"
        Write-Error "Error details: $($_.Exception.Message)"
        exit 2
    } catch {
        Write-Error "UNEXPECTED ERROR writing session log"
        Write-Error "Target path: $filePath"
        Write-Error "Exception Type: $($_.Exception.GetType().FullName)"
        Write-Error "Message: $($_.Exception.Message)"
        throw
    }
}

function Invoke-ValidationScript {
    <#
    .SYNOPSIS
        Validate session log using JSON schema + Validate-SessionJson.ps1
    .DESCRIPTION
        Two-tier validation:
        1. JSON Schema validation (structural, deterministic)
        2. Script validation (business rules, cross-field checks)
    .NOTES
        This function enforces validation - missing validation script is treated as FAILURE,
        not silently skipped. This ensures verification-based enforcement.

        Throws:
        - FileNotFoundException: Schema or validation script not found
        - ApplicationFailedException: Validation script execution failed
    #>
    param(
        [Parameter(Mandatory)]
        [string]$SessionLogPath,

        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    # Phase 1: JSON Schema Validation (structural)
    $schemaPath = Join-Path $RepoRoot ".agents/schemas/session-log.schema.json"
    if (-not (Test-Path $schemaPath)) {
        Write-Error "CRITICAL: JSON schema not found at: $schemaPath"
        Write-Error "Cannot perform structural validation without schema."
        return $false
    }

    try {
        Write-Host "Running JSON schema validation..." -ForegroundColor Yellow
        $jsonContent = Get-Content $SessionLogPath -Raw -ErrorAction Stop
        $schemaContent = Get-Content $schemaPath -Raw -ErrorAction Stop

        # Test-Json with -Schema parameter for validation
        $isValid = Test-Json -Json $jsonContent -Schema $schemaContent -ErrorAction SilentlyContinue

        if (-not $isValid) {
            Write-Error "JSON schema validation FAILED"
            Write-Error "Session log does not conform to schema: $schemaPath"
            Write-Error "Fix structural issues before proceeding."
            return $false
        }

        Write-Host "  Schema validation PASSED" -ForegroundColor Green
    } catch {
        Write-Error "JSON schema validation error: $($_.Exception.Message)"
        return $false
    }

    # Phase 2: Script Validation (business rules)
    $validationScript = Join-Path $RepoRoot "scripts/Validate-SessionJson.ps1"

    # Missing validation script is a CRITICAL failure - no silent fallback
    if (-not (Test-Path $validationScript)) {
        Write-Error "CRITICAL: Validation script not found at: $validationScript"
        Write-Error "Cannot verify session log compliance without validation."
        Write-Error "This violates the verification-based enforcement principle."
        Write-Error ""
        Write-Error "To fix:"
        Write-Error "  1. Ensure you are in the correct repository root"
        Write-Error "  2. Verify scripts/Validate-SessionJson.ps1 exists"
        Write-Error "  3. Do not run this script from a subdirectory"
        Write-Error ""
        Write-Error "If you MUST skip validation (testing only), use -SkipValidation flag."
        return $false
    }

    try {
        Write-Host "Running script validation..." -ForegroundColor Yellow

        # Capture output and error separately to avoid exception handling issues
        $ErrorActionPreference = 'Continue'  # Allow Write-Error to not throw
        $validationOutput = & $validationScript -SessionPath $SessionLogPath 2>&1
        $validationExitCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'  # Restore for other errors

        if ($validationExitCode -ne 0) {
            Write-Host "  Script validation FAILED with exit code $validationExitCode" -ForegroundColor Red
            if ($validationOutput) {
                Write-Host ""
                Write-Host "Validation output:" -ForegroundColor Yellow
                $validationOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
            }
            return $false
        }

        Write-Host "  Script validation PASSED" -ForegroundColor Green
        return $true

    } catch [System.Management.Automation.ApplicationFailedException] {
        Write-Host "  Validation script execution failed" -ForegroundColor Red
        Write-Host "  Script: $validationScript" -ForegroundColor Gray
        Write-Host "  This indicates a problem with the validation infrastructure" -ForegroundColor Yellow
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Gray
        return $false
    } catch [System.UnauthorizedAccessException] {
        Write-Host "  Permission denied executing validation script" -ForegroundColor Red
        Write-Host "  Script: $validationScript" -ForegroundColor Gray
        Write-Host "  Fix: chmod +x $validationScript" -ForegroundColor Yellow
        return $false
    } catch {
        Write-Host "  UNEXPECTED ERROR during validation" -ForegroundColor Red
        Write-Host "  Exception: $($_.Exception.GetType().FullName)" -ForegroundColor Gray
        Write-Host "  Message: $($_.Exception.Message)" -ForegroundColor Gray
        Write-Host "  This is a bug" -ForegroundColor Yellow
        return $false
    }
}

#endregion

#region Main Execution

try {
    Write-Host "=== JSON Session Log Creator ===" -ForegroundColor Cyan
    Write-Host ""

    # Phase 1: Gather inputs (with autonomous detection)
    Write-Host "Phase 1: Gathering inputs..." -ForegroundColor Yellow
    try {
        $gitInfo = Get-GitInfo
    } catch [System.InvalidOperationException] {
        Write-Error $_.Exception.Message
        exit 1
    } catch {
        Write-Error "UNEXPECTED ERROR in Get-GitInfo"
        Write-Error "Exception Type: $($_.Exception.GetType().FullName)"
        Write-Error "Message: $($_.Exception.Message)"
        Write-Error "Stack Trace: $($_.ScriptStackTrace)"
        Write-Error ""
        Write-Error "This is a bug. Please report this error with the above details."
        throw
    }
    Write-Host "  Repository: $($gitInfo.RepoRoot)" -ForegroundColor Gray
    Write-Host "  Branch: $($gitInfo.Branch)" -ForegroundColor Gray
    Write-Host "  Commit: $($gitInfo.Commit)" -ForegroundColor Gray
    Write-Host "  Status: $($gitInfo.Status)" -ForegroundColor Gray
    Write-Host ""

    $userInput = Get-UserInput -SessionNumber $SessionNumber -Objective $Objective -RepoRoot $gitInfo.RepoRoot -Branch $gitInfo.Branch
    Write-Host "  Session Number: $($userInput.SessionNumber)" -ForegroundColor Gray
    Write-Host "  Objective: $($userInput.Objective)" -ForegroundColor Gray
    Write-Host ""

    # Phase 2: Create JSON session log
    Write-Host "Phase 2: Creating JSON session log..." -ForegroundColor Yellow
    $sessionLogPath = New-JsonSessionLog -GitInfo $gitInfo -UserInput $userInput -RepoRoot $gitInfo.RepoRoot
    Write-Host "  File: $sessionLogPath" -ForegroundColor Gray
    Write-Host ""

    # Phase 3: Validate with JSON schema + script
    if (-not $SkipValidation) {
        Write-Host "Phase 3: Validating session log..." -ForegroundColor Yellow
        $validationResult = Invoke-ValidationScript -SessionLogPath $sessionLogPath -RepoRoot $gitInfo.RepoRoot
        Write-Host ""

        if (-not $validationResult) {
            Write-Host "=== FAILED ===" -ForegroundColor Red
            Write-Host ""
            Write-Host "Session log created but validation FAILED" -ForegroundColor Red
            Write-Host "  File: $sessionLogPath" -ForegroundColor Gray
            Write-Host ""
            Write-Host "Fix the issues and re-validate with:" -ForegroundColor Yellow
            Write-Host "  pwsh scripts/Validate-SessionJson.ps1 -SessionPath `"$sessionLogPath`"" -ForegroundColor Gray
            exit 4
        }
    } else {
        Write-Host "Phase 3: Validation skipped (SkipValidation flag set)" -ForegroundColor Yellow
        Write-Host ""
    }

    # Success
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    if ($SkipValidation) {
        Write-Host "Session log created (validation SKIPPED)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "WARNING: This session log has NOT been validated." -ForegroundColor Yellow
        Write-Host "It may contain errors or missing required sections." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Validate manually with:" -ForegroundColor Yellow
        Write-Host "  pwsh scripts/Validate-SessionJson.ps1 -SessionPath `"$sessionLogPath`"" -ForegroundColor Gray
    } else {
        Write-Host "JSON session log created and validated" -ForegroundColor Green
    }
    Write-Host "  File: $sessionLogPath" -ForegroundColor Gray
    Write-Host "  Session: $($userInput.SessionNumber)" -ForegroundColor Gray
    Write-Host "  Branch: $($gitInfo.Branch)" -ForegroundColor Gray
    Write-Host "  Commit: $($gitInfo.Commit)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Next: Complete Session Start checklist in the session log" -ForegroundColor Cyan

    exit 0

} catch {
    Write-Host "=== FATAL ERROR ===" -ForegroundColor Red
    Write-Host ""
    Write-Host "An unexpected error occurred that was not handled by specific error handlers." -ForegroundColor Red
    Write-Host "This indicates a bug in the script. Please report this issue." -ForegroundColor Red
    Write-Host ""
    Write-Host "Exception Type: $($_.Exception.GetType().FullName)" -ForegroundColor Yellow
    Write-Host "Message: $($_.Exception.Message)" -ForegroundColor Yellow
    if ($_.InvocationInfo.ScriptName) {
        Write-Host "At: $($_.InvocationInfo.ScriptName):$($_.InvocationInfo.ScriptLineNumber)" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Full Error Details:" -ForegroundColor Gray
    Write-Host $_.Exception.ToString() -ForegroundColor Gray
    Write-Host ""
    if ($_.ScriptStackTrace) {
        Write-Host "Stack Trace:" -ForegroundColor Gray
        Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    }
    exit 1
}

#endregion
