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
        Returns array of hashtables with Req, Step, Status ('x' or ' '), Evidence, and Raw properties.
    #>
    param(
        [Parameter(Mandatory)]
        [string[]]$TableLines
    )

    $rows = New-Object System.Collections.Generic.List[hashtable]

    foreach ($line in $TableLines) {
        # Skip separator and header rows
        # Note: Separator regex is permissive to handle varied markdown table formats
        # Matches: lines containing ONLY pipes (|), dashes (-), and/or whitespace
        # WARNING: Accepts malformed separators like '---' (no pipes) or '|||' (no dashes)
        # Trade-off: Simplicity over strictness. False positives are harmless (row gets skipped)
        $isSeparator = $line -match '^\s*[|\s-]+\s*$'
        $isHeader = $line -match '^\s*\|\s*Req\s*\|'

        if ($isSeparator) { continue }
        if ($isHeader) { continue }

        # Split into 4 columns, trim outer pipes
        $parts = ($line.Trim() -replace '^\|', '' -replace '\|$', '').Split('|') |
            ForEach-Object { $_.Trim() }

        if ($parts.Count -lt 4) { continue }

        # Parse columns
        $req = ($parts[0] -replace '\*', '').Trim().ToUpperInvariant()
        $step = $parts[1].Trim()
        $statusRaw = $parts[2].Trim()
        $evidence = $parts[3].Trim()

        # Normalize status to 'x' or ' '
        $status = ' '
        if ($statusRaw -match '\[\s*[xX]\s*\]') {
            $status = 'x'
        }

        $rows.Add(@{
            Req = $req
            Step = $step
            Status = $status
            Evidence = $evidence
            Raw = $line
        })
    }

    # Return as array. Comma operator prevents unwrapping when function returns single-element array.
    # PowerShell unwraps single-element arrays on function return: return @('item') becomes return 'item'
    # The comma operator forces array preservation: return ,@('item') keeps array type
    return ,$rows.ToArray()
}

function ConvertTo-NormalizedStep {
    <#
    .SYNOPSIS
        Converts step text to normalized form by collapsing whitespace and removing markdown.
    #>
    param(
        [Parameter(Mandatory)]
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

    # Extract memory names (kebab-case identifiers)
    $memoryPattern = '[a-z][a-z0-9]*(?:-[a-z0-9]+)+'
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
        [string[]]$Files
    )

    if (-not $Files -or $Files.Count -eq 0) {
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

function Test-SessionLogExists {
    <#
    .SYNOPSIS
        Validates that session log file exists and has correct naming pattern.
    #>
    param([string]$FilePath)

    $result = @{
        Passed = $true
        Issues = @()
        Warnings = @()
        Level = 'MUST'
    }

    if (-not (Test-Path $FilePath)) {
        $result.Passed = $false
        $result.Issues += "Session log file does not exist: $FilePath"
        return $result
    }

    $fileName = Split-Path -Leaf $FilePath
    # Pattern: YYYY-MM-DD-session-N.md or YYYY-MM-DD-session-N-description.md (N = any number of digits)
    if ($fileName -notmatch '^\d{4}-\d{2}-\d{2}-session-\d+(-.+)?\.md$') {
        $result.Passed = $false
        $result.Issues += "Session log naming violation: $fileName (expected: YYYY-MM-DD-session-N.md or YYYY-MM-DD-session-N-description.md)"
    }

    return $result
}

function Test-ProtocolComplianceSection {
    <#
    .SYNOPSIS
        Validates that session log contains Protocol Compliance section.
    #>
    param([string]$Content)

    $result = @{
        Passed = $true
        Issues = @()
        Warnings = @()
        Level = 'MUST'
    }

    if ($Content -notmatch '(?i)##\s*Protocol\s+Compliance') {
        $result.Passed = $false
        $result.Issues += "Missing 'Protocol Compliance' section"
        return $result
    }

    # Check for start checklist
    if ($Content -notmatch '(?i)Session\s+Start.*COMPLETE\s+ALL|Start.*before.*work') {
        $result.Issues += "Missing Session Start checklist header"
    }

    # Check for end checklist
    if ($Content -notmatch '(?i)Session\s+End.*COMPLETE\s+ALL|End.*before.*closing') {
        $result.Issues += "Missing Session End checklist header"
    }

    if ($result.Issues.Count -gt 0) {
        $result.Passed = $false
    }

    return $result
}

function Test-MustRequirements {
    <#
    .SYNOPSIS
        Validates that all MUST requirements in the session log are checked.
    #>
    param([string]$Content)

    $result = @{
        Passed = $true
        Issues = @()
        Level = 'MUST'
        Details = @{
            TotalMust = 0
            CompletedMust = 0
            IncompleteMust = @()
        }
    }

    # Find all MUST requirement rows in tables
    # Pattern: | MUST | description | [x] or [ ] |
    # Also matches: | **MUST** | description | [x] or [ ] |
    $mustMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\*?\*?\s*\|([^|]+)\|\s*\[([x ])\]')

    foreach ($match in $mustMatches) {
        $result.Details.TotalMust++
        $description = $match.Groups[1].Value.Trim()
        $isComplete = $match.Groups[2].Value -eq 'x'

        if ($isComplete) {
            $result.Details.CompletedMust++
        } else {
            $result.Details.IncompleteMust += $description
        }
    }

    # FALLBACK: If primary pattern found nothing, try alternate 4-column table pattern
    # Both regexes match same table structure: | MUST | description | [x] | evidence |
    # Primary captures description (Groups[1]); fallback only captures status (Groups[1])
    # CRITICAL: Only run fallback when primary found ZERO matches to prevent double-counting
    # If primary succeeded, fallback would re-match same rows, causing duplicate processing
    if ($mustMatches.Count -eq 0) {
        $tableMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\*?\*?\s*\|[^|]+\|\s*\[([x ])\]\s*\|')
        foreach ($match in $tableMatches) {
            $result.Details.TotalMust++
            $isComplete = $match.Groups[1].Value -eq 'x'
            if (-not $isComplete) {
                $result.Details.IncompleteMust += "(table row)"
            } else {
                $result.Details.CompletedMust++
            }
        }
    }

    if ($result.Details.IncompleteMust.Count -gt 0) {
        $result.Passed = $false
        $result.Issues += "Incomplete MUST requirements: $($result.Details.IncompleteMust.Count) of $($result.Details.TotalMust)"
        foreach ($incomplete in $result.Details.IncompleteMust) {
            $result.Issues += "  - $incomplete"
        }
    }

    return $result
}

function Test-MustNotRequirements {
    <#
    .SYNOPSIS
        Validates that MUST NOT requirements are verified (checked).

    .DESCRIPTION
        MUST NOT requirements represent prohibited actions per SESSION-PROTOCOL.md.
        Checkbox semantics for MUST NOT:
        - [x] = Verified compliance (confirmed did NOT perform prohibited action)
        - [ ] = Not verified (unknown if prohibited action was performed)

        Examples: "MUST NOT Update HANDOFF.md", "MUST NOT Skip validation"

    .PARAMETER Content
        Session log content to validate

    .OUTPUTS
        [PSCustomObject] with Passed, Issues, and Details properties
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$Content
    )

    $result = [PSCustomObject]@{
        Passed = $true
        Issues = @()
        Details = [PSCustomObject]@{
            TotalMustNot = 0
            Violations = @()  # MUST NOT requirements that are unchecked (not verified)
            Compliant = 0      # MUST NOT requirements that are checked (verified compliance)
        }
    }

    # Find all MUST NOT requirement rows in tables
    # Pattern: | MUST NOT | description | [x] or [ ] |
    # Also matches: | **MUST NOT** | description | [x] or [ ] |
    # Note: Uses negative lookahead (?!.*NOT) to avoid matching "MUST NOT" in MUST regex
    $mustNotMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\s+NOT\*?\*?\s*\|([^|]+)\|\s*\[([x ])\]')

    foreach ($match in $mustNotMatches) {
        $result.Details.TotalMustNot++
        $description = $match.Groups[1].Value.Trim()
        $isChecked = $match.Groups[2].Value -eq 'x'

        if ($isChecked) {
            # Checked MUST NOT = Verified compliance (confirmed did NOT do prohibited action)
            $result.Details.Compliant++
        } else {
            # Unchecked MUST NOT = Not verified (unknown if violated)
            $result.Details.Violations += $description
        }
    }

    # FALLBACK: If primary pattern found nothing, try alternate 4-column table pattern
    # Pattern: | MUST NOT | description | [x] or [ ] | evidence |
    # Double-count prevention: Only process fallback when primary regex found ZERO matches
    if ($mustNotMatches.Count -eq 0) {
        $tableMatches = [regex]::Matches($Content, '\|\s*\*?\*?MUST\s+NOT\*?\*?\s*\|[^|]+\|\s*\[([x ])\]\s*\|')
        foreach ($match in $tableMatches) {
            $result.Details.TotalMustNot++
            $isChecked = $match.Groups[1].Value -eq 'x'
            if ($isChecked) {
                # Checked MUST NOT = Verified compliance
                $result.Details.Compliant++
            } else {
                # Unchecked MUST NOT = Not verified
                $result.Details.Violations += "(table row)"
            }
        }
    }

    # Fail validation if any MUST NOT requirements are not verified (unchecked)
    if ($result.Details.Violations.Count -gt 0) {
        $result.Passed = $false
        $result.Issues += "Unverified MUST NOT requirements: $($result.Details.Violations.Count) of $($result.Details.TotalMustNot) not verified"
        foreach ($unverified in $result.Details.Violations) {
            $result.Issues += "  - NOT VERIFIED: $unverified"
        }
    }

    return $result
}

function Test-HandoffUpdated {
    <#
    .SYNOPSIS
        Checks whether HANDOFF.md was modified during the session (violation of SESSION-PROTOCOL.md).
        Per protocol: "MUST NOT update HANDOFF.md". Session context goes to log and Serena memory.

    .NOTES
        Prefers git diff for reliable detection. Falls back to filesystem timestamps in non-git environments.
        In shallow clones where git diff fails, validation fails rather than using unreliable timestamps.
    #>
    param(
        [string]$SessionPath,
        [string]$BasePath
    )

    $result = @{
        Passed = $true
        Issues = @()
        Warnings = @()
        Level = 'MUST'
    }

    $handoffPath = Join-Path $BasePath ".agents/HANDOFF.md"

    if (-not (Test-Path $handoffPath)) {
        # HANDOFF.md existence is not required by current protocol
        return $result
    }

    # Check if HANDOFF.md was modified in current branch
    # Strategy: Use git diff if available, fall back to filesystem timestamp
    Push-Location $BasePath
    try {
        $useGitDiff = $false
        $gitDiffWorked = $false

        # Check if we're in a git repository
        $gitCheck = git rev-parse --git-dir 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Verbose "Not a git repository or git command failed: $gitCheck"
        } else {
            # Check if origin/main exists (may not in shallow checkout)
            $originCheck = git rev-parse --verify origin/main 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Verbose "Remote origin/main not found: $originCheck. May be shallow clone or detached state."
            } else {
                $useGitDiff = $true
            }
        }

        if ($useGitDiff) {
            # Use git diff for reliable detection
            $gitDiff = git diff --name-only origin/main...HEAD 2>&1
            if ($LASTEXITCODE -ne 0) {
                $warningMsg = "Git diff failed: $gitDiff. Falling back to timestamp comparison (less reliable in CI)."
                Write-Warning $warningMsg
                $result.Warnings += $warningMsg
            } else {
                $gitDiffWorked = $true
                $handoffModified = $gitDiff -contains ".agents/HANDOFF.md"

                if ($handoffModified) {
                    $result.Passed = $false
                    $result.Issues += "HANDOFF.md was modified in this branch (detected via git diff). Per SESSION-PROTOCOL.md, agents MUST NOT update HANDOFF.md. Use session log and Serena memory instead."
                }
            }
        }

        # Fall back to filesystem timestamp if git diff not available
        # (used for test environments, non-git directories)
        # IMPORTANT: In shallow checkouts, fail validation explicitly rather than using timestamps
        # Timestamp comparison is unreliable in shallow clones where all files have checkout timestamp
        $gitDirCheck = git rev-parse --git-dir 2>&1
        $isGitRepo = $LASTEXITCODE -eq 0

        if (-not $isGitRepo -and $gitDirCheck) {
            Write-Verbose "Git repository check failed: $gitDirCheck. Treating as non-git directory."
        }

        $isGitRepoWithoutOrigin = $isGitRepo -and -not $useGitDiff

        if ($isGitRepoWithoutOrigin) {
            # Shallow checkout detected - cannot reliably validate
            $result.Passed = $false
            $result.Issues += "Cannot validate HANDOFF.md modification in shallow git checkout. Git diff requires origin/main reference. Ensure full clone or fetch origin/main before validation."
            return $result
        }

        if (-not $gitDiffWorked) {
            # Not a git repo - use timestamp fallback with warning
            $warningMsg = "HANDOFF.md validation using filesystem timestamp (git not available). Results may be unreliable in CI environments."
            Write-Warning $warningMsg
            $result.Warnings += $warningMsg
            $sessionFileName = Split-Path -Leaf $SessionPath
            if ($sessionFileName -match '^(\d{4}-\d{2}-\d{2})') {
                try {
                    $sessionDate = [DateTime]::ParseExact($Matches[1], 'yyyy-MM-dd', $null)

                    try {
                        $handoffItem = Get-Item -LiteralPath $handoffPath -ErrorAction Stop
                        $handoffModifiedDate = $handoffItem.LastWriteTime.Date

                        if ($handoffModifiedDate -ge $sessionDate) {
                            $result.Passed = $false
                            $result.Issues += "HANDOFF.md was modified ($($handoffModifiedDate.ToString('yyyy-MM-dd'))) on or after session date ($($sessionDate.ToString('yyyy-MM-dd'))). Per SESSION-PROTOCOL.md, agents MUST NOT update HANDOFF.md. Use session log and Serena memory instead."
                        }
                    } catch [System.UnauthorizedAccessException] {
                        $result.Passed = $false
                        $errorMsg = "Permission denied reading HANDOFF.md metadata. Cannot verify modification timestamp. Check file permissions and retry validation."
                        $result.Issues += $errorMsg
                        Write-Error $errorMsg
                        return $result
                    } catch [System.IO.FileNotFoundException] {
                        $result.Passed = $false
                        $errorMsg = "HANDOFF.md was deleted during validation (race condition detected between existence check and metadata read). File system may be unstable. Retry validation. If issue persists, check for concurrent processes or file system issues."
                        $result.Issues += $errorMsg
                        Write-Error $errorMsg
                        return $result
                    } catch [System.IO.PathTooLongException] {
                        $result.Passed = $false
                        $result.Issues += "HANDOFF.md path exceeds maximum length. This indicates a project structure issue. Move project to shorter path."
                        Write-Error "HANDOFF.md path too long. Move project to shorter path."
                        return $result
                    } catch [System.IO.IOException] {
                        $result.Passed = $false
                        $result.Issues += "I/O error reading HANDOFF.md: $($_.Exception.Message). Check disk health, file locks, and retry."
                        Write-Error "I/O error reading HANDOFF.md: $($_.Exception.Message)"
                        return $result
                    } catch {
                        $result.Passed = $false
                        $result.Issues += "Unexpected error reading HANDOFF.md: $($_.Exception.GetType().Name) - $($_.Exception.Message). Contact support if issue persists."
                        Write-Error "Unexpected error reading HANDOFF.md: $($_.Exception.GetType().Name) - $($_.Exception.Message)"
                        return $result
                    }
                } catch [System.FormatException] {
                    # Date parsing failed - check if git validation already succeeded
                    if ($gitDiffWorked) {
                        # Git validation succeeded, but filename is still malformed - warn user
                        $warningMsg = "Session log filename has invalid date format: '$($Matches[1])'. Expected format: YYYY-MM-DD (e.g., 2026-01-05). Git validation succeeded but filename should be corrected to match naming convention."
                        Write-Warning $warningMsg
                        $result.Warnings += $warningMsg
                        return $result
                    }

                    # No git validation available and date parsing failed
                    $result.Passed = $false
                    $errorMsg = "Session log filename contains invalid date format: '$($Matches[1])'. Expected format: YYYY-MM-DD. Cannot validate HANDOFF.md modification without git diff or valid timestamp."
                    $result.Issues += $errorMsg
                    Write-Error $errorMsg
                    return $result
                } catch {
                    # Unexpected error during date parsing - check if git validation already succeeded
                    if ($gitDiffWorked) {
                        # Git validation already completed successfully, date parsing failure is non-blocking
                        Write-Verbose "Date parsing error but git validation already completed. Error: $($_.Exception.Message)"
                        return $result
                    }

                    # No git validation available and unexpected error occurred
                    $result.Passed = $false
                    $errorMsg = "Unexpected error parsing session date: $($_.Exception.GetType().Name) - $($_.Exception.Message). Cannot validate HANDOFF.md modification without git diff or valid timestamp."
                    $result.Issues += $errorMsg
                    Write-Error $errorMsg
                    return $result
                }
            }
        }
    }
    finally {
        Pop-Location
    }

    return $result
}

function Test-ShouldRequirements {
    <#
    .SYNOPSIS
        Validates SHOULD requirements (warnings only).
    #>
    param([string]$Content)

    $result = @{
        Passed = $true
        Issues = @()
        Level = 'SHOULD'
        Details = @{
            TotalShould = 0
            CompletedShould = 0
            IncompleteShould = @()
        }
    }

    # Find all SHOULD requirement rows
    $shouldMatches = [regex]::Matches($Content, '\|\s*\*?\*?SHOULD\*?\*?\s*\|([^|]+)\|\s*\[([x ])\]')

    foreach ($match in $shouldMatches) {
        $result.Details.TotalShould++
        $description = $match.Groups[1].Value.Trim()
        $isComplete = $match.Groups[2].Value -eq 'x'

        if ($isComplete) {
            $result.Details.CompletedShould++
        } else {
            $result.Details.IncompleteShould += $description
        }
    }

    # SHOULD violations are warnings, not failures
    if ($result.Details.IncompleteShould.Count -gt 0) {
        $result.Issues += "Incomplete SHOULD requirements (warnings): $($result.Details.IncompleteShould.Count) of $($result.Details.TotalShould)"
    }

    return $result
}

function Test-GitCommitEvidence {
    <#
    .SYNOPSIS
        Validates that session log contains commit evidence.
    #>
    param([string]$Content)

    $result = @{
        Passed = $true
        Issues = @()
        Warnings = @()
        Level = 'MUST'
    }

    # Look for commit SHA patterns (7+ hex characters)
    $commitPattern = '[0-9a-f]{7,40}'

    # Check for commits section or commit references
    if ($Content -match '(?i)commit.*SHA|commits.*session|Commit SHA:') {
        if ($Content -notmatch $commitPattern) {
            $result.Issues += "Commits section exists but no commit SHA found"
        }
    } else {
        # Check if commit evidence appears anywhere
        if ($Content -notmatch "(?i)commit.*$commitPattern|$commitPattern.*-\s+") {
            $result.Issues += "No commit evidence found in session log"
        }
    }

    # This is informational, not a hard failure
    # The actual commit check should be done via git log

    return $result
}

function Test-SessionLogCompleteness {
    <#
    .SYNOPSIS
        Validates that session log has all expected sections.
    #>
    param([string]$Content)

    $result = @{
        Passed = $true
        Issues = @()
        Level = 'SHOULD'
        Sections = @{
            Found = @()
            Missing = @()
        }
    }

    $expectedSections = @(
        @{ Pattern = '(?i)##\s*Session\s+Info'; Name = 'Session Info' }
        @{ Pattern = '(?i)##\s*Protocol\s+Compliance'; Name = 'Protocol Compliance' }
        @{ Pattern = '(?i)##\s*Work\s+Log|##\s*Tasks?\s+Completed'; Name = 'Work Log' }
        @{ Pattern = '(?i)##\s*Session\s+End|Session\s+End.*COMPLETE'; Name = 'Session End' }
    )

    foreach ($section in $expectedSections) {
        if ($Content -match $section.Pattern) {
            $result.Sections.Found += $section.Name
        } else {
            $result.Sections.Missing += $section.Name
            $result.Issues += "Missing section: $($section.Name)"
        }
    }

    if ($result.Sections.Missing.Count -gt 0) {
        $result.Passed = $false
    }

    return $result
}

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
        throw "Permission denied reading sessions directory: $sessionsPath. Check file permissions and retry."
    } catch [System.IO.PathTooLongException] {
        throw "Sessions directory path exceeds maximum length: $sessionsPath. Move project to shorter path."
    } catch [System.IO.DirectoryNotFoundException] {
        throw "Sessions directory not found: $sessionsPath. Verify .agents folder exists at project root."
    } catch [System.IO.IOException] {
        throw "I/O error reading sessions directory: $sessionsPath. Error: $($_.Exception.Message). Check disk health and file locks."
    } catch [System.ArgumentException] {
        throw "Invalid sessions directory path: $sessionsPath. Path contains invalid characters. Verify project location and path formatting."
    } catch {
        # Unexpected error - provide full context and suggest bug report
        $errorMsg = "Unexpected error reading sessions directory: $sessionsPath`n" +
                    "Error Type: $($_.Exception.GetType().FullName)`n" +
                    "Message: $($_.Exception.Message)`n" +
                    "Stack Trace: $($_.ScriptStackTrace)`n" +
                    "This is likely a bug. Please report this issue with the above details."
        throw $errorMsg
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
