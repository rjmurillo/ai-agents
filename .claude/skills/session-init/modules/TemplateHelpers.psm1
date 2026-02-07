<#
.SYNOPSIS
    Template processing helpers for session log generation.

.DESCRIPTION
    Provides functions to populate session log templates with actual values
    and extract descriptive keywords from objectives. Includes placeholder
    validation before and after replacement to ensure template integrity.

.NOTES
    Designed to be self-contained and reusable across session-init workflows.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Import shared exception type (single source of truth per Issue #840)
Import-Module (Join-Path $PSScriptRoot 'CommonTypes.psm1') -Force

# Fallback: define locally if type not available (e.g., module scoping edge cases)
if (-not ([System.Management.Automation.PSTypeName]'ApplicationFailedException').Type) {
    class ApplicationFailedException : System.ApplicationException {
        ApplicationFailedException([string]$Message, [Exception]$InnerException) : base($Message, $InnerException) {}
    }
}

function New-PopulatedSessionLog {
    <#
    .SYNOPSIS
        Replace template placeholders with actual values.

    .DESCRIPTION
        Takes a session log template and replaces all placeholders with actual
        values from git state and user input. Validates that the template contains
        expected placeholders before replacement and verifies successful replacement
        afterward.

    .PARAMETER Template
        The session log template string containing placeholders to replace.

    .PARAMETER GitInfo
        Hashtable containing git repository state with keys:
        - Branch: Current branch name
        - Commit: Short commit SHA
        - Status: "clean" or "dirty"

    .PARAMETER UserInput
        Hashtable containing user-provided values with keys:
        - SessionNumber: Integer session number (e.g., 42)
        - Objective: Session objective description

    .OUTPUTS
        [string] The populated session log with all placeholders replaced.

    .NOTES
        Throws:
        - InvalidOperationException: Template missing required placeholders when
          SkipValidation is NOT specified (fail-safe default)
        - ApplicationFailedException: Unexpected errors during processing

        The SkipValidation switch controls whether missing placeholders trigger
        an exception (when false/default) or just a warning (when true). This
        enforces the skip-validation safeguard documented in SESSION-PROTOCOL.md.

        Placeholder Patterns:
        - NN: Session number (word boundary match)
        - YYYY-MM-DD: Date (replaced with current date)
        - [branch name]: Git branch
        - [SHA]: Git commit SHA
        - [What this session aims to accomplish]: Session objective
        - [clean/dirty]: Git working tree status

        Warnings are issued (but not exceptions thrown) for:
        - Missing placeholders in template (may indicate version mismatch)
        - Unreplaced placeholders after processing (validation issue)

    .EXAMPLE
        $gitInfo = @{ Branch = 'main'; Commit = 'abc1234'; Status = 'clean' }
        $userInput = @{ SessionNumber = 42; Objective = 'Implement OAuth flow' }
        $result = New-PopulatedSessionLog -Template $templateContent -GitInfo $gitInfo -UserInput $userInput
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Template,

        [Parameter(Mandatory)]
        [hashtable]$GitInfo,

        [Parameter(Mandatory)]
        [hashtable]$UserInput,

        [Parameter()]
        [switch]$SkipValidation
    )

    try {
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
            if ($SkipValidation) {
                # When SkipValidation is set, warn instead of failing
                Write-Warning ("Template missing required placeholders: $($missingPlaceholders -join ', '). " +
                    "This indicates a version mismatch with SESSION-PROTOCOL.md. " +
                    "Proceeding anyway due to -SkipValidation flag.")
            } else {
                # Default: Fail immediately to prevent creating invalid session logs
                throw [System.InvalidOperationException]::new(
                    "Template missing required placeholders: $($missingPlaceholders -join ', ')`n`n" +
                    "This indicates a version mismatch with SESSION-PROTOCOL.md. " +
                    "Session log cannot be created. Update template or fix protocol file."
                )
            }
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
            if ($SkipValidation) {
                # When SkipValidation is set, warn instead of failing
                Write-Warning "Some placeholders were not replaced: $($unreplacedPlaceholders -join ', ')"
                Write-Warning "Session log may be invalid. Verify content manually."
            } else {
                # Default: Fail immediately to prevent creating invalid session logs
                throw [System.InvalidOperationException]::new(
                    "Placeholders were not replaced: $($unreplacedPlaceholders -join ', ')`n`n" +
                    "This indicates a validation failure. Session log cannot be created."
                )
            }
        }

        return $populated
    } catch [System.InvalidOperationException] {
        # Expected validation failures - rethrow without wrapping
        throw
    } catch {
        # Wrap unexpected errors in ApplicationFailedException with diagnostic details
        $diagnosticMessage = @"
UNEXPECTED ERROR in New-PopulatedSessionLog
Exception Type: $($_.Exception.GetType().FullName)
Message: $($_.Exception.Message)
Stack Trace: $($_.ScriptStackTrace)

This is a bug. Please report this error with the above details.
"@
        
        $ex = [ApplicationFailedException]::new($diagnosticMessage, $_.Exception)
        throw $ex
    }
}

function Get-DescriptiveKeywords {
    <#
    .SYNOPSIS
        Extract descriptive keywords from session objective for filename.

    .DESCRIPTION
        Extracts up to 5 most relevant keywords from objective using NLP heuristics:
        - Remove common stop words (the, a, an, to, for, with, etc.)
        - Keep domain-specific verbs (implement, debug, fix, refactor, etc.)
        - Convert to kebab-case (lowercase, hyphen-separated)
        - Limit to 5 keywords maximum

    .PARAMETER Objective
        The session objective description to extract keywords from.

    .OUTPUTS
        [string] Kebab-case string of up to 5 keywords, or empty string if no
        keywords can be extracted.

    .NOTES
        This function intentionally has no explicit error handling because:
        - Operates only on in-memory strings (no I/O)
        - Uses only safe PowerShell string operators
        - Returns empty string on unexpected input (handled gracefully by caller)
        - Cannot throw exceptions under normal PowerShell operation

        Keyword Selection:
        - Words must be at least 3 characters
        - Stop words are filtered out
        - First 5 qualifying words are selected (most relevant are usually first)
        - Technical terms like "api", "sql", "git" are preserved

    .EXAMPLE
        Get-DescriptiveKeywords -Objective "Debug recurring session validation failures"
        # Returns: "debug-recurring-session-validation-failures"

    .EXAMPLE
        Get-DescriptiveKeywords -Objective "Implement OAuth 2.0 authentication flow"
        # Returns: "implement-oauth-authentication-flow"

    .EXAMPLE
        Get-DescriptiveKeywords -Objective "Fix test coverage gaps in UserService"
        # Returns: "fix-test-coverage-gaps-userservice"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Objective
    )

    # Handle empty/null input gracefully
    if ([string]::IsNullOrWhiteSpace($Objective)) {
        return ''
    }

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
    $result = ($keywords -join '-')
    
    # Clean up any leading/trailing/consecutive hyphens
    $result = $result -replace '^-+', '' -replace '-+$', '' -replace '-{2,}', '-'
    
    return $result
}

Export-ModuleMember -Function New-PopulatedSessionLog, Get-DescriptiveKeywords
