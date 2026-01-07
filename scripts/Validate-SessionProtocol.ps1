<#
.SYNOPSIS
    Validates session protocol compliance for agent session logs.

.DESCRIPTION
    Implements verification-based enforcement of the session protocol defined in
    .agents/SESSION-PROTOCOL.md. Checks that session logs contain required sections,
    MUST requirements are completed, and verification evidence exists.

    This script enforces RFC 2119 requirement levels:
    - MUST/REQUIRED: Violation is a protocol failure (error)
    - SHOULD/RECOMMENDED: Missing is a warning
    - MAY/OPTIONAL: Not checked

.PARAMETER SessionPath
    Path to a specific session log file to validate.

.PARAMETER All
    Validate all session logs in .agents/sessions/.

.PARAMETER Recent
    Validate only sessions from the last N days. Default: 7.

.PARAMETER Format
    Output format: "console", "markdown", or "json".
    Default: "console"

.PARAMETER CI
    CI mode - returns non-zero exit code on failures.

.PARAMETER Path
    Base path to scan. Default: current directory.

.EXAMPLE
    .\Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2025-12-17-session-01.md"

.EXAMPLE
    .\Validate-SessionProtocol.ps1 -All -CI

.EXAMPLE
    .\Validate-SessionProtocol.ps1 -Recent 3 -Format markdown
#>

[CmdletBinding(DefaultParameterSetName = 'Recent')]
param(
    [Parameter(ParameterSetName = 'Session', Mandatory = $true)]
    [string]$SessionPath,

    [Parameter(ParameterSetName = 'All', Mandatory = $true)]
    [switch]$All,

    [Parameter(ParameterSetName = 'Recent')]
    [int]$Recent = 7,

    [Parameter()]
    [ValidateSet("console", "markdown", "json")]
    [string]$Format = "console",

    [Parameter()]
    [switch]$CI,

    [Parameter()]
    [string]$Path = "."
)

$ErrorActionPreference = 'Stop'

# Import shared validation functions
$sessionValidationModule = Join-Path $PSScriptRoot "modules/SessionValidation.psm1"
Import-Module $sessionValidationModule -Force

#region Color Output
$ColorReset = "`e[0m"
$ColorRed = "`e[31m"
$ColorYellow = "`e[33m"
$ColorGreen = "`e[32m"
$ColorCyan = "`e[36m"
$ColorMagenta = "`e[35m"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    if ($Format -eq "console") {
        Write-Host "${Color}${Message}${ColorReset}"
    }
}
#endregion

#region Table Extraction and Parsing Helpers

# Maximum lines to search for table after heading
$MaxTableSearchLines = 80

function Get-HeadingTable {
    <#
    .SYNOPSIS
        Extracts the first markdown table after a heading matching the given regex.

    .DESCRIPTION
        Returns table lines (including header, separator, and data rows) or $null if not found.
        Searches up to $MaxTableSearchLines lines after heading for table start.
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string[]]$Lines,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$HeadingRegex
    )

    # Find heading
    $headingIdx = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match $HeadingRegex) {
            $headingIdx = $i
            break
        }
    }

    if ($headingIdx -lt 0) {
        return $null
    }

    # Find table header row after heading
    $tableStart = -1
    $searchLimit = [Math]::Min($headingIdx + $script:MaxTableSearchLines, $Lines.Count)
    for ($i = $headingIdx; $i -lt $searchLimit; $i++) {
        if ($Lines[$i] -match '^\|\s*Req\s*\|\s*Step\s*\|\s*Status\s*\|\s*Evidence\s*\|\s*$') {
            $tableStart = $i
            break
        }
    }

    if ($tableStart -lt 0) {
        return $null
    }

    # Extract all table rows until non-table line
    $tableLines = New-Object System.Collections.Generic.List[string]
    for ($i = $tableStart; $i -lt $Lines.Count; $i++) {
        $line = $Lines[$i]
        if ($line -match '^\|') {
            $tableLines.Add($line)
            continue
        }
        break
    }

    return $tableLines.ToArray()
}

function ConvertFrom-ChecklistTable {
    <#
    .SYNOPSIS
        Converts markdown table rows into structured checklist items.

    .DESCRIPTION
        Delegates to Parse-ChecklistTable in SessionValidation.psm1.
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string[]]$TableLines
    )

    return ,(Parse-ChecklistTable -TableLines $TableLines)
}

function ConvertTo-NormalizedStep {
    <#
    .SYNOPSIS
        Converts step text to normalized form by collapsing whitespace and removing markdown.
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$StepText
    )

    return ($StepText -replace '\s+', ' ' -replace '\*', '').Trim()
}

function Test-MemoryEvidence {
    <#
    .SYNOPSIS
        Validates that memory-related checklist rows have valid Evidence per ADR-007.

    .DESCRIPTION
        Finds the "memory-index" row in Session Start checklist and verifies:
        1. Evidence column is not empty or placeholder text
        2. Evidence contains memory names (kebab-case identifiers)
        3. Each referenced memory exists in .serena/memories/

    .OUTPUTS
        Hashtable with: IsValid, MemoriesFound, MissingMemories, ErrorMessage
    #>
    param(
        [Parameter(Mandatory)]
        [hashtable[]]$SessionRows,

        [Parameter(Mandatory)]
        [string]$RepoRoot
    )

    $result = @{
        IsValid = $true
        MemoriesFound = @()
        MissingMemories = @()
        ErrorMessage = $null
    }

    # Find the memory-index row
    $memoryRow = $SessionRows | Where-Object {
        (ConvertTo-NormalizedStep $_.Step) -match 'memory-index.*memories'
    } | Select-Object -First 1

    if (-not $memoryRow) {
        # No memory-index row found - not an error
        return $result
    }

    $evidence = $memoryRow.Evidence

    # Check for empty or placeholder evidence
    $placeholderPatterns = @(
        '^\s*$',                           # Empty
        '^List memories loaded$',          # Template placeholder
        '^\[.*\]$',                        # Bracketed placeholder
        '^-+$'                             # Dashes only
    )

    foreach ($pattern in $placeholderPatterns) {
        if ($evidence -match $pattern) {
            $result.IsValid = $false
            $result.ErrorMessage = "Memory-index Evidence column contains placeholder text: '$evidence'. List actual memory names read (e.g., 'memory-index, skills-pr-review-index')."
            return $result
        }
    }

    # Extract memory names (kebab-case identifiers; allow single-word names as well)
    $memoryPattern = '[a-z][a-z0-9]*(?:-[a-z0-9]+)*'
    $foundMemories = @(
        [regex]::Matches($evidence, $memoryPattern, 'IgnoreCase') |
            ForEach-Object { $_.Value.ToLowerInvariant() } |
            Select-Object -Unique
    )

    if ($foundMemories.Count -eq 0) {
        $result.IsValid = $false
        $result.ErrorMessage = "Memory-index Evidence column doesn't contain valid memory names: '$evidence'. Expected format: 'memory-index, skills-pr-review-index, ...' (kebab-case names)."
        return $result
    }

    $result.MemoriesFound = $foundMemories

    # Verify each memory exists in .serena/memories/
    $memoriesDir = Join-Path $RepoRoot ".serena" "memories"

    # Check that memories directory exists before checking individual files
    if (-not (Test-Path -LiteralPath $memoriesDir -PathType Container)) {
        $result.IsValid = $false
        $result.ErrorMessage = "Serena memories directory not found: $memoriesDir. Initialize Serena memory system (mcp__serena__activate_project) before validation."
        return $result
    }

    $missingMemories = [System.Collections.Generic.List[string]]::new()

    foreach ($memName in $foundMemories) {
        $memPath = Join-Path $memoriesDir "$memName.md"
        if (-not (Test-Path -LiteralPath $memPath)) {
            $missingMemories.Add($memName)
        }
    }

    if ($missingMemories.Count -gt 0) {
        $result.MissingMemories = $missingMemories.ToArray()
        $result.IsValid = $false
        $missing = $missingMemories -join ', '
        $result.ErrorMessage = "Memory-index Evidence references memories that don't exist: $missing. Verify memory names or create missing memories in .serena/memories/."
    }

    return $result
}

# Shared exempt paths (audit artifacts common to investigation and QA skip rules)
$script:CommonExemptPaths = @(
    '^[.]agents/sessions/',        # Session logs (audit trail)
    '^[.]agents/analysis/',        # Investigation outputs
    '^[.]serena/memories($|/)'     # Cross-session context
)

# Investigation-only allowlist patterns (ADR-034)
$script:InvestigationAllowlist = $script:CommonExemptPaths + @(
    '^[.]agents/retrospective/',   # Learnings
    '^[.]agents/security/'         # Security assessments
)

# Session audit artifacts (exempt from QA validation)
$script:AuditArtifacts = $script:CommonExemptPaths

function Test-DocsOnly {
    <#
    .SYNOPSIS
        Tests if all files are documentation (.md) for QA skip eligibility.
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateNotNull()]
        [AllowEmptyCollection()]
        [string[]]$Files
    )

    if ($Files.Count -eq 0) {
        # Empty file list is NOT considered "docs only"
        # Rationale: No files changed could be merge commit, revert, etc. - still need QA
        return $false
    }

    foreach ($f in $Files) {
        $ext = [IO.Path]::GetExtension($f).ToLowerInvariant()
        if ($ext -ne '.md') {
            return $false
        }
    }

    return $true
}

function Test-InvestigationOnlyEligibility {
    <#
    .SYNOPSIS
        Tests if all files match investigation-only allowlist per ADR-034.

    .OUTPUTS
        Hashtable with: IsEligible, ImplementationFiles
    #>
    param(
        [string[]]$Files
    )

    $result = @{
        IsEligible = $true
        ImplementationFiles = @()
    }

    if (-not $Files -or $Files.Count -eq 0) {
        return $result
    }

    $implementationFiles = [System.Collections.Generic.List[string]]::new()
    foreach ($file in $Files) {
        # Normalize path separators
        $normalizedFile = $file -replace '\\', '/'

        $isAllowed = $false
        foreach ($pattern in $script:InvestigationAllowlist) {
            if ($normalizedFile -match $pattern) {
                $isAllowed = $true
                break
            }
        }

        if (-not $isAllowed) {
            $implementationFiles.Add($file)
        }
    }

    if ($implementationFiles.Count -gt 0) {
        $result.IsEligible = $false
        $result.ImplementationFiles = $implementationFiles.ToArray()
    }

    return $result
}

function Get-ImplementationFiles {
    <#
    .SYNOPSIS
        Filters out audit artifacts from file list, returning only implementation files.

    .DESCRIPTION
        Session logs, analysis, and memories are audit trail, not implementation.
        This allows them to be committed WITH implementation without false positives.
    #>
    param(
        [string[]]$Files
    )

    if (-not $Files -or $Files.Count -eq 0) {
        return @()
    }

    $implementationFiles = [System.Collections.Generic.List[string]]::new()
    foreach ($file in $Files) {
        # Normalize path separators
        $normalizedFile = $file -replace '\\', '/'

        $isAuditArtifact = $false
        foreach ($pattern in $script:AuditArtifacts) {
            if ($normalizedFile -match $pattern) {
                $isAuditArtifact = $true
                break
            }
        }

        if (-not $isAuditArtifact) {
            $implementationFiles.Add($file)
        }
    }

    return $implementationFiles.ToArray()
}

#endregion

#region Validation Functions
# Extracted to scripts/modules/SessionValidation.psm1
#endregion

#region Main Validation Logic

function Invoke-SessionValidation {
    param(
        [string]$SessionFile,
        [string]$BasePath
    )

    $validation = @{
        SessionPath = $SessionFile
        SessionName = Split-Path -Leaf $SessionFile
        Passed = $true
        MustPassed = $true
        ShouldPassed = $true
        Results = @{}
        Issues = @()
        Warnings = @()
    }

    # Test 1: Session log exists and naming
    $existsResult = Test-SessionLogExists -FilePath $SessionFile
    $validation.Results['SessionLogExists'] = $existsResult
    if (-not $existsResult.Passed) {
        $validation.Passed = $false
        $validation.MustPassed = $false
        $validation.Issues += $existsResult.Issues
        return $validation  # Can't continue without file
    }

    # Read content
    $content = Get-Content -Path $SessionFile -Raw

    # Test 2: Memory evidence validation (ADR-007)
    $lines = ($content -split "`r?`n") | Where-Object { $_ -ne '' }
    $sessionStartTable = Get-HeadingTable -Lines $lines -HeadingRegex '^\s*##\s+Session\s+Start\s*$'
    if ($sessionStartTable) {
        $sessionStartRows = ConvertFrom-ChecklistTable -TableLines $sessionStartTable
        $memoryResult = Test-MemoryEvidence -SessionRows $sessionStartRows -RepoRoot $BasePath
        $validation.Results['MemoryEvidence'] = $memoryResult
        if (-not $memoryResult.IsValid) {
            $validation.Passed = $false
            $validation.MustPassed = $false
            $validation.Issues += $memoryResult.ErrorMessage
        }
    }

    # Test 3: Protocol Compliance section
    $complianceResult = Test-ProtocolComplianceSection -Content $content
    $validation.Results['ProtocolComplianceSection'] = $complianceResult
    if (-not $complianceResult.Passed) {
        $validation.Passed = $false
        $validation.MustPassed = $false
        $validation.Issues += $complianceResult.Issues
    }

    # Test 4: MUST requirements completed
    $mustResult = Test-MustRequirements -Content $content
    $validation.Results['MustRequirements'] = $mustResult
    if (-not $mustResult.Passed) {
        $validation.Passed = $false
        $validation.MustPassed = $false
        $validation.Issues += $mustResult.Issues
    }

    # Test 5: MUST NOT requirements (violations)
    $mustNotResult = Test-MustNotRequirements -Content $content
    $validation.Results['MustNotRequirements'] = $mustNotResult
    if (-not $mustNotResult.Passed) {
        $validation.Passed = $false
        $validation.MustPassed = $false
        $validation.Issues += $mustNotResult.Issues
    }

    # Test 6: HANDOFF.md updated
    $handoffResult = Test-HandoffUpdated -SessionPath $SessionFile -BasePath $BasePath
    $validation.Results['HandoffUpdated'] = $handoffResult
    if (-not $handoffResult.Passed) {
        $validation.Passed = $false
        $validation.MustPassed = $false
        $validation.Issues += $handoffResult.Issues
    }

    # Test 7: SHOULD requirements (warnings)
    $shouldResult = Test-ShouldRequirements -Content $content
    $validation.Results['ShouldRequirements'] = $shouldResult
    if ($shouldResult.Issues.Count -gt 0) {
        $validation.ShouldPassed = $false
        $validation.Warnings += $shouldResult.Issues
    }

    # Test 8: Commit evidence
    $commitResult = Test-GitCommitEvidence -Content $content
    $validation.Results['CommitEvidence'] = $commitResult
    if ($commitResult.Issues.Count -gt 0) {
        $validation.Warnings += $commitResult.Issues
    }

    # Test 8: Session log completeness
    $completenessResult = Test-SessionLogCompleteness -Content $content
    $validation.Results['SessionLogCompleteness'] = $completenessResult
    if (-not $completenessResult.Passed) {
        $validation.ShouldPassed = $false
        $validation.Warnings += $completenessResult.Issues
    }

    return $validation
}

function Get-SessionLogs {
    param(
        [string]$BasePath,
        [int]$Days = 0
    )

    $sessionsPath = Join-Path $BasePath ".agents/sessions"

    if (-not (Test-Path $sessionsPath)) {
        return @()
    }

    try {
        $sessions = Get-ChildItem -Path $sessionsPath -Filter "*.md" -ErrorAction Stop |
            Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}-session-\d+(-.+)?\.md$' }
    } catch [System.UnauthorizedAccessException] {
        Write-Error "Permission denied reading sessions directory: $sessionsPath. Check file permissions and retry."
        throw
    } catch [System.IO.PathTooLongException] {
        Write-Error "Sessions directory path exceeds maximum length: $sessionsPath. Move project to shorter path."
        throw
    } catch [System.IO.DirectoryNotFoundException] {
        Write-Error "Sessions directory not found: $sessionsPath. Verify .agents folder exists at project root."
        throw
    } catch [System.IO.IOException] {
        Write-Error "I/O error reading sessions directory: $sessionsPath. Error: $($_.Exception.Message). Check disk health and file locks."
        throw
    } catch [System.ArgumentException] {
        Write-Error "Invalid sessions directory path: $sessionsPath. Path contains invalid characters. Verify project location and path formatting."
        throw
    } catch {
        # Unexpected error - provide full context and suggest bug report
        $errorMsg = "Unexpected error reading sessions directory: $sessionsPath`n" +
                    "Error Type: $($_.Exception.GetType().FullName)`n" +
                    "Message: $($_.Exception.Message)`n" +
                    "Stack Trace: $($_.ScriptStackTrace)`n" +
                    "This is likely a bug. Please report this issue with the above details."
        Write-Error $errorMsg
        throw
    }

    if ($Days -gt 0) {
        $cutoffDate = (Get-Date).AddDays(-$Days)
        $excludedSessions = [System.Collections.Generic.List[string]]::new()

        $sessions = $sessions | Where-Object {
            if ($_.Name -match '^(\d{4}-\d{2}-\d{2})') {
                try {
                    $fileDate = [DateTime]::ParseExact($Matches[1], 'yyyy-MM-dd', $null)
                    return $fileDate -ge $cutoffDate
                } catch {
                    $excludedSessions.Add($_.Name)
                    Write-Warning "Excluding session with invalid date format: $($_.Name). Expected: YYYY-MM-DD-session-N.md"
                    return $false
                }
            }
            return $false
        }

        if ($excludedSessions.Count -gt 0) {
            Write-Warning "Excluded $($excludedSessions.Count) session(s) due to date parsing errors:"
            foreach ($excluded in $excludedSessions) {
                Write-Warning "  - $excluded"
            }
        }
    }

    return $sessions | Sort-Object Name -Descending
}

#endregion

#region Output Formatting

function Format-ConsoleOutput {
    param([array]$Validations)

    Write-ColorOutput "=== Session Protocol Validation ===" $ColorCyan
    Write-ColorOutput "RFC 2119: MUST = error, SHOULD = warning" $ColorMagenta
    Write-ColorOutput ""

    $totalPassed = 0
    $totalFailed = 0
    $totalWarnings = 0

    foreach ($v in $Validations) {
        $status = if ($v.MustPassed) {
            if ($v.ShouldPassed) { "${ColorGreen}PASS${ColorReset}" }
            else { "${ColorYellow}PASS (with warnings)${ColorReset}" }
        } else {
            "${ColorRed}FAIL${ColorReset}"
        }

        Write-ColorOutput "Session: $($v.SessionName) - $status"

        if ($null -ne $v.Results) {
            foreach ($checkName in $v.Results.Keys) {
                $check = $v.Results[$checkName]
                $level = if ($check.Level -eq 'MUST') { $ColorRed } else { $ColorYellow }
                $checkStatus = if ($check.Passed) { "${ColorGreen}[PASS]${ColorReset}" }
                              elseif ($check.Level -eq 'MUST') { "${ColorRed}[FAIL]${ColorReset}" }
                              else { "${ColorYellow}[WARN]${ColorReset}" }

                Write-ColorOutput "  $checkStatus $checkName ($($check.Level))"

                if ($check.Issues.Count -gt 0) {
                    foreach ($issue in $check.Issues) {
                        Write-ColorOutput "    - $issue" $ColorYellow
                    }
                }
            }
        }

        if ($v.MustPassed) { $totalPassed++ } else { $totalFailed++ }
        if (-not $v.ShouldPassed) { $totalWarnings++ }

        Write-ColorOutput ""
    }

    Write-ColorOutput "=== Summary ===" $ColorCyan
    Write-ColorOutput "Passed: $totalPassed" $ColorGreen
    if ($totalFailed -gt 0) {
        Write-ColorOutput "Failed: $totalFailed (MUST violations)" $ColorRed
    }
    if ($totalWarnings -gt 0) {
        Write-ColorOutput "Warnings: $totalWarnings (SHOULD violations)" $ColorYellow
    }

    return $totalFailed
}

function Format-MarkdownOutput {
    param([array]$Validations)

    $sb = [System.Text.StringBuilder]::new()

    [void]$sb.AppendLine("# Session Protocol Validation Report")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("**Date**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
    [void]$sb.AppendLine("**RFC 2119**: MUST = error, SHOULD = warning")
    [void]$sb.AppendLine("")

    foreach ($v in $Validations) {
        $status = if ($v.MustPassed) { "PASSED" } else { "FAILED" }
        [void]$sb.AppendLine("## Session: $($v.SessionName)")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("**Status**: $status")
        [void]$sb.AppendLine("")

        [void]$sb.AppendLine("### Validation Results")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("| Check | Level | Status | Issues |")
        [void]$sb.AppendLine("|-------|-------|--------|--------|")

        foreach ($checkName in $v.Results.Keys) {
            $check = $v.Results[$checkName]
            $checkStatus = if ($check.Passed) { "PASS" } else { "FAIL" }
            $issues = if ($check.Issues.Count -gt 0) { $check.Issues -join "; " } else { "-" }
            [void]$sb.AppendLine("| $checkName | $($check.Level) | $checkStatus | $issues |")
        }

        [void]$sb.AppendLine("")
    }

    return $sb.ToString()
}

function Format-JsonOutput {
    param([array]$Validations)

    $output = @{
        timestamp = (Get-Date -Format 'o')
        rfc2119 = "MUST = error, SHOULD = warning"
        validations = $Validations
        summary = @{
            total = $Validations.Count
            passed = ($Validations | Where-Object { $_.MustPassed }).Count
            failed = ($Validations | Where-Object { -not $_.MustPassed }).Count
            warnings = ($Validations | Where-Object { -not $_.ShouldPassed }).Count
        }
    }

    return $output | ConvertTo-Json -Depth 10
}

#endregion

#region Main Execution

try {
    Write-ColorOutput "=== Session Protocol Validation ===" $ColorCyan
    Write-ColorOutput "Path: $Path" $ColorMagenta
    Write-ColorOutput ""

    $validations = @()

    if ($SessionPath) {
        # Single session validation
        $fullPath = if ([System.IO.Path]::IsPathRooted($SessionPath)) {
            $SessionPath
        } else {
            Join-Path $Path $SessionPath
        }

        $validation = Invoke-SessionValidation -SessionFile $fullPath -BasePath $Path
        $validations += $validation
    } elseif ($All) {
        # All sessions
        $sessions = Get-SessionLogs -BasePath $Path
        Write-ColorOutput "Found $($sessions.Count) session log(s)" $ColorMagenta
        Write-ColorOutput ""

        foreach ($session in $sessions) {
            $validation = Invoke-SessionValidation -SessionFile $session.FullName -BasePath $Path
            $validations += $validation
        }
    } else {
        # Recent sessions (default)
        $sessions = Get-SessionLogs -BasePath $Path -Days $Recent
        Write-ColorOutput "Found $($sessions.Count) session log(s) from last $Recent days" $ColorMagenta
        Write-ColorOutput ""

        foreach ($session in $sessions) {
            $validation = Invoke-SessionValidation -SessionFile $session.FullName -BasePath $Path
            $validations += $validation
        }
    }

    # Output results
    $failCount = 0
    switch ($Format) {
        "console" {
            $failCount = Format-ConsoleOutput -Validations $validations
        }
        "markdown" {
            $md = Format-MarkdownOutput -Validations $validations
            Write-Output $md
            $failCount = ($validations | Where-Object { -not $_.MustPassed }).Count
        }
        "json" {
            $json = Format-JsonOutput -Validations $validations
            Write-Output $json
            $failCount = ($validations | Where-Object { -not $_.MustPassed }).Count
        }
    }

    if ($CI) {
        if ($failCount -gt 0) {
            exit 1
        }
        # Explicit exit 0 to prevent $LASTEXITCODE pollution from external commands like git
        exit 0
    }
} catch {
    # Enhanced error context for debugging (HIGH #4 from Round 4 review)
    $errorContext = @(
        "Validation failed with error: $($_.Exception.GetType().FullName)",
        "Message: $($_.Exception.Message)",
        "Parameter Set: $($PSCmdlet.ParameterSetName)",
        "Session Path: $(if ($SessionPath) { $SessionPath } else { 'N/A' })",
        "Validations Completed: $($validations.Count)"
    )

    # Add current session file context if available from exception data
    if ($_.Exception.TargetSite -and $_.Exception.TargetSite.Name) {
        $errorContext += "Failed in: $($_.Exception.TargetSite.Name)"
    }

    # Add script line number if available
    if ($_.InvocationInfo.ScriptLineNumber) {
        $errorContext += "Script Line: $($_.InvocationInfo.ScriptLineNumber)"
    }

    $fullErrorMessage = $errorContext -join "`n  "
    Write-Error $fullErrorMessage

    if ($CI) {
        exit 1
    }
    throw
}

#endregion
