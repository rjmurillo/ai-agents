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
    #>
    param()

    try {
        $repoRoot = git rev-parse --show-toplevel 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Not in a git repository"
        }

        $branch = git branch --show-current 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to get current branch"
        }

        $commit = git log --oneline -1 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to get commit history"
        }

        $statusOutput = git status --short 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to get git status"
        }

        $gitStatus = if ([string]::IsNullOrWhiteSpace($statusOutput)) { "clean" } else { "dirty" }

        return @{
            RepoRoot = $repoRoot.Trim()
            Branch = $branch.Trim()
            Commit = $commit.Trim()
            Status = $gitStatus
        }
    } catch {
        Write-Error "Git error: $_"
        exit 1
    }
}

function Get-UserInput {
    <#
    .SYNOPSIS
        Prompt user for session details
    #>
    param(
        [Parameter()]
        [int]$SessionNumber,

        [Parameter()]
        [string]$Objective
    )

    if (-not $SessionNumber) {
        do {
            $input = Read-Host "Enter session number (e.g., 375)"
            $parsed = 0
            $valid = [int]::TryParse($input, [ref]$parsed)
        } while (-not $valid -or $parsed -le 0)
        $SessionNumber = $parsed
    }

    if (-not $Objective) {
        do {
            $Objective = Read-Host "Enter session objective (e.g., 'Implement session-init skill')"
        } while ([string]::IsNullOrWhiteSpace($Objective))
    }

    return @{
        SessionNumber = $SessionNumber
        Objective = $Objective.Trim()
    }
}

function Invoke-TemplateExtraction {
    <#
    .SYNOPSIS
        Extract canonical template using Extract-SessionTemplate.ps1
    #>
    param(
        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $extractScript = Join-Path $RepoRoot ".claude/skills/session-init/scripts/Extract-SessionTemplate.ps1"

    if (-not (Test-Path $extractScript)) {
        Write-Error "Extract-SessionTemplate.ps1 not found at: $extractScript"
        exit 2
    }

    try {
        $template = & $extractScript
        if ($LASTEXITCODE -ne 0) {
            throw "Template extraction failed with exit code $LASTEXITCODE"
        }
        return $template
    } catch {
        Write-Error "Failed to extract template: $_"
        exit 2
    }
}

function New-PopulatedSessionLog {
    <#
    .SYNOPSIS
        Replace template placeholders with actual values
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Template,

        [Parameter(Mandatory)]
        [hashtable]$GitInfo,

        [Parameter(Mandatory)]
        [hashtable]$UserInput
    )

    $currentDate = Get-Date -Format "yyyy-MM-dd"

    # Replace placeholders
    $populated = $Template `
        -replace '\bNN\b', $UserInput.SessionNumber `
        -replace 'YYYY-MM-DD', $currentDate `
        -replace '\[branch name\]', $GitInfo.Branch `
        -replace '\[SHA\]', $GitInfo.Commit `
        -replace '\[What this session aims to accomplish\]', $UserInput.Objective `
        -replace '\[clean/dirty\]', $GitInfo.Status

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

    if (-not (Test-Path $sessionDir)) {
        New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null
    }

    # Generate descriptive filename with keywords from objective
    $keywords = Get-DescriptiveKeywords -Objective $Objective
    $keywordSuffix = if ($keywords) { "-$keywords" } else { "" }
    $fileName = "$currentDate-session-$SessionNumber$keywordSuffix.md"
    $filePath = Join-Path $sessionDir $fileName

    try {
        $Content | Out-File -FilePath $filePath -Encoding utf8 -NoNewline
        return $filePath
    } catch {
        Write-Error "Failed to write session log: $_"
        exit 3
    }
}

function Invoke-ValidationScript {
    <#
    .SYNOPSIS
        Validate session log using Validate-SessionProtocol.ps1
    #>
    param(
        [Parameter(Mandatory)]
        [string]$SessionLogPath,

        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $validationScript = Join-Path $RepoRoot "scripts/Validate-SessionProtocol.ps1"

    if (-not (Test-Path $validationScript)) {
        Write-Warning "Validate-SessionProtocol.ps1 not found at: $validationScript"
        Write-Warning "Skipping validation"
        return $true
    }

    try {
        Write-Host "Running validation: pwsh $validationScript -SessionPath $SessionLogPath -Format markdown"
        & $validationScript -SessionPath $SessionLogPath -Format markdown

        if ($LASTEXITCODE -ne 0) {
            Write-Error "Validation FAILED with exit code $LASTEXITCODE"
            return $false
        }

        Write-Host "Validation PASSED" -ForegroundColor Green
        return $true
    } catch {
        Write-Error "Validation error: $_"
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

    # Success
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Session log created and validated" -ForegroundColor Green
    Write-Host "  File: $sessionLogPath" -ForegroundColor Gray
    Write-Host "  Session: $($userInput.SessionNumber)" -ForegroundColor Gray
    Write-Host "  Branch: $($gitInfo.Branch)" -ForegroundColor Gray
    Write-Host "  Commit: $($gitInfo.Commit)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Next: Complete Session Start checklist in the session log" -ForegroundColor Cyan

    exit 0

} catch {
    Write-Host "=== ERROR ===" -ForegroundColor Red
    Write-Host ""
    Write-Error "Unexpected error: $_"
    exit 1
}

#endregion
