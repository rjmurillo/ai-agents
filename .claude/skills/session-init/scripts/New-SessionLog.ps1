#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create protocol-compliant session log with verification-based enforcement

.DESCRIPTION
    Automates session log creation by:
    1. Prompting for session number and objective
    2. Detecting date/branch/commit/git status
    3. Extracting canonical template from SESSION-PROTOCOL.md
    4. Replacing placeholders with actual values
    5. Writing session log to .agents/sessions/
    6. Running validation with scripts/Validate-SessionProtocol.ps1
    7. Exiting nonzero on validation failure

.PARAMETER SessionNumber
    Session number (e.g., 375). If not provided, will prompt.

.PARAMETER Objective
    Session objective. If not provided, will prompt.

.PARAMETER SkipValidation
    Skip validation after creating session log. Use for testing only.

.OUTPUTS
    Session log file path on success

.EXAMPLE
    & .claude/skills/session-init/scripts/New-SessionLog.ps1
    Prompts for session number and objective, then creates session log

.EXAMPLE
    & .claude/skills/session-init/scripts/New-SessionLog.ps1 -SessionNumber 375 -Objective "Implement session-init skill"
    Creates session log with provided values

.NOTES
    Exit Codes:
    - 0: Success (session log created and validated)
    - 1: Git repository error
    - 2: Template extraction failed
    - 3: Session log write failed
    - 4: Validation failed
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

#region Helper Functions

function Get-GitInfo {
    <#
    .SYNOPSIS
        Gather git repository information
    .NOTES
        Throws:
        - InvalidOperationException: Not in a git repository or git operations failed
        - ApplicationFailedException: Git command execution failed
    #>
    param()

    try {
        # Capture git output and errors separately
        $repoRootOutput = git rev-parse --show-toplevel 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = $repoRootOutput -join "`n"
            throw [System.InvalidOperationException]::new(
                "Not in a git repository. Git error (exit code $LASTEXITCODE): $errorDetails`n`nEnsure you are in a git repository by running 'git status'. If you are in a git repository, check for corruption with 'git fsck'."
            )
        }
        $repoRoot = $repoRootOutput

        $branchOutput = git branch --show-current 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = $branchOutput -join "`n"
            throw [System.InvalidOperationException]::new(
                "Failed to get current branch. Git error (exit code $LASTEXITCODE): $errorDetails`n`nThis usually means you are in a detached HEAD state or the repository is corrupted. Run 'git branch --show-current' manually to investigate."
            )
        }
        $branch = $branchOutput

        $commitOutput = git log --oneline -1 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = $commitOutput -join "`n"
            throw [System.InvalidOperationException]::new(
                "Failed to get commit history. Git error (exit code $LASTEXITCODE): $errorDetails`n`nThis usually means the repository has no commits yet. Create an initial commit with 'git commit --allow-empty -m \"Initial commit\"'."
            )
        }
        $commit = $commitOutput

        $statusOutput = git status --short 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorDetails = $statusOutput -join "`n"
            throw [System.InvalidOperationException]::new(
                "Failed to get git status. Git error (exit code $LASTEXITCODE): $errorDetails`n`nThis indicates repository corruption or permission issues. Run 'git status' manually to investigate."
            )
        }

        $gitStatus = if ([string]::IsNullOrWhiteSpace($statusOutput)) { "clean" } else { "dirty" }

        return @{
            RepoRoot = $repoRoot.Trim()
            Branch = $branch.Trim()
            Commit = $commit.Trim()
            Status = $gitStatus
        }
    } catch [System.InvalidOperationException] {
        # Expected git operation failures - already have detailed messages
        Write-Error $_.Exception.Message
        exit 1
    } catch {
        # Unexpected errors - provide full diagnostic information
        Write-Error "UNEXPECTED ERROR in Get-GitInfo"
        Write-Error "Exception Type: $($_.Exception.GetType().FullName)"
        Write-Error "Message: $($_.Exception.Message)"
        Write-Error "Stack Trace: $($_.ScriptStackTrace)"
        Write-Error ""
        Write-Error "This is a bug. Please report this error with the above details."
        throw
    }
}

function Get-UserInput {
    <#
    .SYNOPSIS
        Prompt user for session details
    .NOTES
        Throws:
        - InvalidOperationException: Cannot prompt in non-interactive terminal
    #>
    param(
        [Parameter()]
        [int]$SessionNumber,

        [Parameter()]
        [string]$Objective
    )

    # Check if we need to prompt and if we can
    $needsPrompt = (-not $SessionNumber) -or (-not $Objective)
    if ($needsPrompt) {
        # Detect non-interactive terminal
        if (-not [Environment]::UserInteractive) {
            throw [System.InvalidOperationException]::new(
                "Cannot prompt for input in non-interactive terminal.`n`nProvide required parameters:`n  -SessionNumber <number>`n  -Objective `"<description>`"`n`nExample:`n  pwsh New-SessionLog.ps1 -SessionNumber 375 -Objective `"Implement feature X`""
            )
        }

        # Additional check for stdin availability (CI/CD environments)
        try {
            $null = [Console]::KeyAvailable
        } catch {
            throw [System.InvalidOperationException]::new(
                "Console input not available (running in CI/CD or redirected stdin?).`n`nProvide required parameters:`n  -SessionNumber <number>`n  -Objective `"<description>`""
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

function Invoke-TemplateExtraction {
    <#
    .SYNOPSIS
        Extract canonical template using Extract-SessionTemplate.ps1
    .NOTES
        Throws:
        - FileNotFoundException: Extract script not found
        - ApplicationFailedException: Extract script failed to execute
        - UnauthorizedAccessException: Permission denied executing script
    #>
    param(
        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $extractScript = Join-Path $RepoRoot ".claude/skills/session-init/scripts/Extract-SessionTemplate.ps1"

    if (-not (Test-Path $extractScript)) {
        throw [System.IO.FileNotFoundException]::new(
            "Extract-SessionTemplate.ps1 not found at: $extractScript`n`nEnsure you are running from the repository root and the session-init skill is properly installed."
        )
    }

    try {
        $template = & $extractScript 2>&1
        if ($LASTEXITCODE -ne 0) {
            $errorOutput = $template -join "`n"
            throw [System.Management.Automation.ApplicationFailedException]::new(
                "Template extraction script failed (exit code $LASTEXITCODE).`n`nScript: $extractScript`n`nError output:`n$errorOutput`n`nCheck the extract script for syntax errors or missing dependencies."
            )
        }
        
        # Validate template is not empty
        if ([string]::IsNullOrWhiteSpace($template)) {
            throw [System.InvalidOperationException]::new(
                "Template extraction returned empty content.`n`nScript: $extractScript`n`nThis indicates the SESSION-PROTOCOL.md file may be missing the canonical template section."
            )
        }
        
        return $template
    } catch [System.Management.Automation.ApplicationFailedException] {
        # Expected failure - script execution error
        Write-Error $_.Exception.Message
        exit 2
    } catch [System.UnauthorizedAccessException] {
        Write-Error "Permission denied executing template extraction script: $extractScript"
        Write-Error "Ensure the script has execute permissions: chmod +x $extractScript"
        exit 2
    } catch [System.InvalidOperationException] {
        # Expected failure - empty template
        Write-Error $_.Exception.Message
        exit 2
    } catch {
        # Unexpected errors
        Write-Error "UNEXPECTED ERROR during template extraction"
        Write-Error "Exception Type: $($_.Exception.GetType().FullName)"
        Write-Error "Message: $($_.Exception.Message)"
        Write-Error "Script: $extractScript"
        Write-Error "Stack Trace: $($_.ScriptStackTrace)"
        Write-Error ""
        Write-Error "This is a bug. Please report this error with the above details."
        throw
    }
}

function New-PopulatedSessionLog {
    <#
    .SYNOPSIS
        Replace template placeholders with actual values
    .NOTES
        Validates that template contains expected placeholders before replacement
        and verifies successful replacement afterward.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Template,

        [Parameter(Mandatory)]
        [hashtable]$GitInfo,

        [Parameter(Mandatory)]
        [hashtable]$UserInput
    )

    # Verify template has expected placeholders before replacement
    $requiredPlaceholders = @(
        @{ Pattern = '\bNN\b'; Name = 'NN (session number)' },
        @{ Pattern = 'YYYY-MM-DD'; Name = 'YYYY-MM-DD (date)' },
        @{ Pattern = '\[branch name\]'; Name = '[branch name]' },
        @{ Pattern = '\[SHA\]'; Name = '[SHA]' },
        @{ Pattern = '\[What this session aims to accomplish\]'; Name = '[What this session aims to accomplish]' },
        @{ Pattern = '\[clean/dirty\]'; Name = '[clean/dirty]' }
    )
    
    $missingPlaceholders = @()
    foreach ($placeholder in $requiredPlaceholders) {
        if ($Template -notmatch $placeholder.Pattern) {
            $missingPlaceholders += $placeholder.Name
        }
    }
    
    if ($missingPlaceholders.Count -gt 0) {
        Write-Warning "Template missing expected placeholders: $($missingPlaceholders -join ', ')"
        Write-Warning "Template may be from an incompatible version of SESSION-PROTOCOL.md."
        Write-Warning "Session log may be invalid. Proceeding anyway, but validation will likely fail."
    }

    $currentDate = Get-Date -Format "yyyy-MM-dd"

    # Replace placeholders
    $populated = $Template `
        -replace '\bNN\b', $UserInput.SessionNumber `
        -replace 'YYYY-MM-DD', $currentDate `
        -replace '\[branch name\]', $GitInfo.Branch `
        -replace '\[SHA\]', $GitInfo.Commit `
        -replace '\[What this session aims to accomplish\]', $UserInput.Objective `
        -replace '\[clean/dirty\]', $GitInfo.Status

    # Verify replacements occurred
    $unreplacedPlaceholders = @()
    if ($populated -match '\bNN\b') { $unreplacedPlaceholders += 'NN' }
    if ($populated -match '\[branch name\]') { $unreplacedPlaceholders += '[branch name]' }
    if ($populated -match '\[SHA\]') { $unreplacedPlaceholders += '[SHA]' }
    if ($populated -match '\[What this session aims to accomplish\]') { $unreplacedPlaceholders += '[objective]' }
    if ($populated -match '\[clean/dirty\]') { $unreplacedPlaceholders += '[clean/dirty]' }
    
    if ($unreplacedPlaceholders.Count -gt 0) {
        Write-Warning "Some placeholders were not replaced: $($unreplacedPlaceholders -join ', ')"
        Write-Warning "Session log may be invalid. Verify content manually."
    }

    return $populated
}

function Get-DescriptiveKeywords {
    <#
    .SYNOPSIS
        Extract descriptive keywords from session objective for filename
    .DESCRIPTION
        Extracts up to 5 most relevant keywords from objective using NLP heuristics:
        - Remove common stop words (the, a, an, to, for, with, etc.)
        - Keep domain-specific verbs (implement, debug, fix, refactor, etc.)
        - Convert to kebab-case
        - Limit to 5 keywords maximum
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Objective
    )

    # Stop words to remove (common English words with low information value)
    $stopWords = @(
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might',
        'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
        'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some',
        'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
        'very', 's', 't', 'just', 'now', 'before', 'after', 'new'
    )

    # Split objective into words, convert to lowercase, remove punctuation
    $words = $Objective -replace '[^\w\s-]', '' -split '\s+' | ForEach-Object { $_.ToLower() }

    # Filter out stop words and empty strings
    $keywords = $words | Where-Object {
        $_ -and                              # Not empty
        $_.Length -gt 2 -and                 # At least 3 characters
        $_ -notin $stopWords                 # Not a stop word
    }

    # Take first 5 keywords (most relevant are usually at the start)
    $keywords = $keywords | Select-Object -First 5

    # Join with hyphens for kebab-case
    return ($keywords -join '-')
}

function Write-SessionLogFile {
    <#
    .SYNOPSIS
        Write session log to file with descriptive filename
    .NOTES
        Throws:
        - UnauthorizedAccessException: Permission denied
        - IOException: Disk full or file in use
        - PathTooLongException: Path exceeds OS limits
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Content,

        [Parameter(Mandatory)]
        [string]$RepoRoot,

        [Parameter(Mandatory)]
        [int]$SessionNumber,

        [Parameter(Mandatory)]
        [string]$Objective
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
                "Permission denied creating directory: $sessionDir`n`nEnsure you have write permissions to the .agents/ folder.`n`nTry: chmod +w .agents/ (Linux/Mac) or check folder permissions (Windows)",
                $_.Exception
            )
        } catch [System.IO.IOException] {
            throw [System.IO.IOException]::new(
                "Failed to create directory: $sessionDir`n`nPossible causes: disk full, corrupted filesystem, or path conflicts.`n`nCheck disk space: df -h (Linux/Mac) or Get-PSDrive (Windows)",
                $_.Exception
            )
        }
    }

    # Generate descriptive filename with keywords from objective
    $keywords = Get-DescriptiveKeywords -Objective $Objective
    $keywordSuffix = if ($keywords) { "-$keywords" } else { "" }
    $fileName = "$currentDate-session-$SessionNumber$keywordSuffix.md"
    $filePath = Join-Path $sessionDir $fileName

    try {
        # Write content to file
        $Content | Out-File -FilePath $filePath -Encoding utf8 -NoNewline -ErrorAction Stop
        
        # Verify file was created and has content
        if (-not (Test-Path $filePath)) {
            throw [System.IO.IOException]::new(
                "File was not created at expected path: $filePath`n`nThis indicates a filesystem error or race condition."
            )
        }
        
        $fileInfo = Get-Item $filePath -ErrorAction Stop
        if ($fileInfo.Length -eq 0) {
            throw [System.IO.IOException]::new(
                "Session log file was created but is empty: $filePath`n`nThis indicates the write operation failed silently."
            )
        }
        
        # Verify content length is reasonable (within 10% of expected)
        $expectedLength = [System.Text.Encoding]::UTF8.GetByteCount($Content)
        if ($fileInfo.Length -lt ($expectedLength * 0.9)) {
            Write-Warning "Session log file may be truncated."
            Write-Warning "  Expected: ~$expectedLength bytes"
            Write-Warning "  Actual: $($fileInfo.Length) bytes"
            Write-Warning "File: $filePath"
        }
        
        Write-Verbose "Session log written: $filePath ($($fileInfo.Length) bytes)"
        return $filePath
        
    } catch [System.UnauthorizedAccessException] {
        Write-Error "Permission denied writing session log to: $filePath"
        Write-Error "Ensure you have write permissions to the .agents/sessions/ directory."
        Write-Error "Try: chmod +w `"$sessionDir`" (Linux/Mac) or check folder permissions (Windows)"
        exit 3
    } catch [System.IO.IOException] {
        Write-Error "File I/O error writing session log to: $filePath"
        Write-Error "Possible causes:"
        Write-Error "  - Disk full (check with: df -h on Linux/Mac or Get-PSDrive on Windows)"
        Write-Error "  - File in use by another process"
        Write-Error "  - Corrupted filesystem"
        Write-Error "  - Antivirus blocking write"
        Write-Error "Error details: $($_.Exception.Message)"
        exit 3
    } catch [System.IO.PathTooLongException] {
        Write-Error "Path too long for session log file: $filePath"
        Write-Error "File path length: $($filePath.Length) characters"
        Write-Error "Consider using a shorter objective description or moving the repository to a shallower directory."
        exit 3
    } catch {
        Write-Error "UNEXPECTED ERROR writing session log"
        Write-Error "Target path: $filePath"
        Write-Error "Exception Type: $($_.Exception.GetType().FullName)"
        Write-Error "Message: $($_.Exception.Message)"
        Write-Error "Stack Trace: $($_.ScriptStackTrace)"
        Write-Error ""
        Write-Error "This is a bug. Please report this error with the above details."
        throw
    }
}

function Invoke-ValidationScript {
    <#
    .SYNOPSIS
        Validate session log using Validate-SessionProtocol.ps1
    .NOTES
        This function enforces validation - missing validation script is treated as FAILURE,
        not silently skipped. This ensures verification-based enforcement.
        
        Throws:
        - FileNotFoundException: Validation script not found
        - ApplicationFailedException: Validation script execution failed
    #>
    param(
        [Parameter(Mandatory)]
        [string]$SessionLogPath,

        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $validationScript = Join-Path $RepoRoot "scripts/Validate-SessionProtocol.ps1"

    # Missing validation script is a CRITICAL failure - no silent fallback
    if (-not (Test-Path $validationScript)) {
        Write-Error "CRITICAL: Validation script not found at: $validationScript"
        Write-Error "Cannot verify session log compliance without validation."
        Write-Error "This violates the verification-based enforcement principle."
        Write-Error ""
        Write-Error "To fix:"
        Write-Error "  1. Ensure you are in the correct repository root"
        Write-Error "  2. Verify scripts/Validate-SessionProtocol.ps1 exists"
        Write-Error "  3. Do not run this script from a subdirectory"
        Write-Error ""
        Write-Error "If you MUST skip validation (testing only), use -SkipValidation flag."
        return $false
    }

    try {
        Write-Host "Running validation: pwsh $validationScript -SessionPath $SessionLogPath -Format markdown"
        $validationOutput = & $validationScript -SessionPath $SessionLogPath -Format markdown 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Error "Validation FAILED with exit code $LASTEXITCODE"
            if ($validationOutput) {
                Write-Error "Validation output:"
                $validationOutput | ForEach-Object { Write-Error "  $_" }
            }
            return $false
        }

        Write-Host "Validation PASSED" -ForegroundColor Green
        return $true
        
    } catch [System.Management.Automation.ApplicationFailedException] {
        Write-Error "Validation script execution failed"
        Write-Error "Script: $validationScript"
        Write-Error "This indicates a problem with the validation infrastructure, not your session log."
        Write-Error "Error: $($_.Exception.Message)"
        Write-Error ""
        Write-Error "Check the validation script for syntax errors or missing dependencies."
        return $false
    } catch [System.UnauthorizedAccessException] {
        Write-Error "Permission denied executing validation script: $validationScript"
        Write-Error "Ensure the script has execute permissions: chmod +x $validationScript"
        return $false
    } catch {
        Write-Error "UNEXPECTED ERROR during validation"
        Write-Error "Exception Type: $($_.Exception.GetType().FullName)"
        Write-Error "Message: $($_.Exception.Message)"
        Write-Error "Validation Script: $validationScript"
        Write-Error "Session Log: $SessionLogPath"
        Write-Error "Stack Trace: $($_.ScriptStackTrace)"
        Write-Error ""
        Write-Error "This is a bug. Please report this error with the above details."
        return $false
    }
}

#endregion

#region Main Execution

try {
    Write-Host "=== Session Log Creator ===" -ForegroundColor Cyan
    Write-Host ""

    # Phase 1: Gather inputs
    Write-Host "Phase 1: Gathering inputs..." -ForegroundColor Yellow
    $gitInfo = Get-GitInfo
    Write-Host "  Repository: $($gitInfo.RepoRoot)" -ForegroundColor Gray
    Write-Host "  Branch: $($gitInfo.Branch)" -ForegroundColor Gray
    Write-Host "  Commit: $($gitInfo.Commit)" -ForegroundColor Gray
    Write-Host "  Status: $($gitInfo.Status)" -ForegroundColor Gray
    Write-Host ""

    $userInput = Get-UserInput -SessionNumber $SessionNumber -Objective $Objective
    Write-Host "  Session Number: $($userInput.SessionNumber)" -ForegroundColor Gray
    Write-Host "  Objective: $($userInput.Objective)" -ForegroundColor Gray
    Write-Host ""

    # Phase 2: Read canonical template
    Write-Host "Phase 2: Reading canonical template..." -ForegroundColor Yellow
    $template = Invoke-TemplateExtraction -RepoRoot $gitInfo.RepoRoot
    Write-Host "  Template extracted successfully" -ForegroundColor Gray
    Write-Host ""

    # Phase 3: Populate template
    Write-Host "Phase 3: Populating template..." -ForegroundColor Yellow
    $sessionLog = New-PopulatedSessionLog -Template $template -GitInfo $gitInfo -UserInput $userInput
    Write-Host "  Placeholders replaced" -ForegroundColor Gray
    Write-Host ""

    # Phase 4: Write session log
    Write-Host "Phase 4: Writing session log..." -ForegroundColor Yellow
    $sessionLogPath = Write-SessionLogFile -Content $sessionLog -RepoRoot $gitInfo.RepoRoot -SessionNumber $userInput.SessionNumber -Objective $userInput.Objective
    Write-Host "  File: $sessionLogPath" -ForegroundColor Gray
    Write-Host ""

    # Phase 5: Validate
    if (-not $SkipValidation) {
        Write-Host "Phase 5: Validating session log..." -ForegroundColor Yellow
        $validationResult = Invoke-ValidationScript -SessionLogPath $sessionLogPath -RepoRoot $gitInfo.RepoRoot
        Write-Host ""

        if (-not $validationResult) {
            Write-Host "=== FAILED ===" -ForegroundColor Red
            Write-Host ""
            Write-Host "Session log created but validation FAILED" -ForegroundColor Red
            Write-Host "  File: $sessionLogPath" -ForegroundColor Gray
            Write-Host ""
            Write-Host "Fix the issues and re-validate with:" -ForegroundColor Yellow
            Write-Host "  pwsh scripts/Validate-SessionProtocol.ps1 -SessionPath `"$sessionLogPath`" -Format markdown" -ForegroundColor Gray
            exit 4
        }
    } else {
        Write-Host "Phase 5: Validation skipped (SkipValidation flag set)" -ForegroundColor Yellow
        Write-Host ""
    }

    # Success - adjust message based on whether validation actually ran
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    if ($SkipValidation) {
        Write-Host "Session log created (validation SKIPPED)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "WARNING: This session log has NOT been validated." -ForegroundColor Yellow
        Write-Host "It may contain errors or missing required sections." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Validate manually with:" -ForegroundColor Yellow
        Write-Host "  pwsh scripts/Validate-SessionProtocol.ps1 -SessionPath `"$sessionLogPath`" -Format markdown" -ForegroundColor Gray
    } else {
        Write-Host "Session log created and validated" -ForegroundColor Green
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
