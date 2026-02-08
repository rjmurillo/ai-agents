<#
.SYNOPSIS
    Shared investigation-only allowlist for ADR-034 QA exemption.

.DESCRIPTION
    Single source of truth for investigation artifact path patterns.
    Consumers: Validate-SessionJson.ps1, session skill, session-qa-eligibility skill.

.NOTES
    See: ADR-034 Investigation Session QA Exemption
    Issue #732: Added adr-review skill outputs
    Issue #840: Consolidated from 3 divergent copies
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-InvestigationAllowlist {
    <#
    .SYNOPSIS
        Returns the canonical investigation-only allowlist patterns.

    .OUTPUTS
        [string[]] Regex patterns anchored to start of path.
    #>
    [CmdletBinding()]
    param()

    return @(
        '^\.agents/sessions/'
        '^\.agents/analysis/'
        '^\.agents/retrospective/'
        '^\.serena/memories($|/)'
        '^\.agents/security/'
        '^\.agents/memory/'
        # adr-review skill outputs (QA-equivalent critique artifacts)
        '^\.agents/architecture/REVIEW-'
        '^\.agents/critique/'
        '^\.agents/memory/episodes/'
    )
}

function Get-InvestigationAllowlistDisplay {
    <#
    .SYNOPSIS
        Returns human-readable allowed paths for error messages.

    .OUTPUTS
        [string[]] Display-friendly path prefixes.
    #>
    [CmdletBinding()]
    param()

    return @(
        '.agents/sessions/'
        '.agents/analysis/'
        '.agents/retrospective/'
        '.serena/memories/'
        '.agents/security/'
        '.agents/memory/'
        '.agents/architecture/REVIEW-*'
        '.agents/critique/'
        '.agents/memory/episodes/'
    )
}

function Test-FileMatchesAllowlist {
    <#
    .SYNOPSIS
        Tests whether a file path matches the investigation allowlist.

    .PARAMETER FilePath
        The file path to test (relative to repo root).

    .OUTPUTS
        [bool] True if the file matches any allowlist pattern.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$FilePath
    )

    $normalizedPath = $FilePath -replace '\\', '/'
    $patterns = Get-InvestigationAllowlist

    foreach ($pattern in $patterns) {
        if ($normalizedPath -match $pattern) {
            return $true
        }
    }

    return $false
}

Export-ModuleMember -Function Get-InvestigationAllowlist, Get-InvestigationAllowlistDisplay, Test-FileMatchesAllowlist
