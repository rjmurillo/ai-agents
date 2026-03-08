<#
.SYNOPSIS
    Standard skill output helpers per ADR-044.

.DESCRIPTION
    Provides Write-SkillOutput, Write-SkillError, and Get-OutputFormat functions
    for consistent skill script output formatting. All skill scripts should use
    these helpers to produce either JSON or human-readable output.

.NOTES
    Related: ADR-044 (Skill Output Format Standardization)
    Related: ADR-028 (PowerShell Output Schema Consistency)
    Related: ADR-035 (Exit Code Standardization)
#>

function Get-OutputFormat {
    <#
    .SYNOPSIS
        Resolves the output format based on requested value and execution context.

    .PARAMETER Requested
        The requested format: JSON, Human, or Auto.

    .OUTPUTS
        [string] Either 'JSON' or 'Human'.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter()]
        [ValidateSet('JSON', 'Human', 'Auto')]
        [string]$Requested = 'Auto'
    )

    if ($Requested -ne 'Auto') {
        return $Requested
    }

    # CI environments always get JSON
    if ($env:CI -or $env:GITHUB_ACTIONS -or $env:TF_BUILD) {
        return 'JSON'
    }

    # Check if stdout is redirected (pipeline or file)
    try {
        if ([Console]::IsOutputRedirected) {
            return 'JSON'
        }
    }
    catch {
        # Console not available (e.g., in tests) — default to JSON
        return 'JSON'
    }

    return 'Human'
}

function Write-SkillOutput {
    <#
    .SYNOPSIS
        Emits a standardized skill output envelope.

    .PARAMETER Data
        The operation-specific result data.

    .PARAMETER OutputFormat
        Output format: JSON, Human, or Auto.

    .PARAMETER HumanSummary
        One-line summary for human-readable output.

    .PARAMETER Status
        Status indicator for human output: PASS, FAIL, WARNING, INFO.

    .PARAMETER ScriptName
        Name of the calling script (auto-detected if omitted).

    .PARAMETER Version
        Script version string.

    .EXAMPLE
        Write-SkillOutput -Data $result -HumanSummary "PR #42: All checks passing" -Status PASS
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [AllowNull()]
        [object]$Data,

        [Parameter()]
        [ValidateSet('JSON', 'Human', 'Auto')]
        [string]$OutputFormat = 'Auto',

        [Parameter()]
        [string]$HumanSummary,

        [Parameter()]
        [ValidateSet('PASS', 'FAIL', 'WARNING', 'INFO')]
        [string]$Status = 'PASS',

        [Parameter()]
        [string]$ScriptName,

        [Parameter()]
        [string]$Version = '1.0.0'
    )

    $resolvedFormat = Get-OutputFormat -Requested $OutputFormat

    if (-not $ScriptName) {
        $ScriptName = if ($MyInvocation.PSCommandPath) {
            Split-Path $MyInvocation.PSCommandPath -Leaf
        }
        else {
            'unknown'
        }
    }

    $envelope = [ordered]@{
        Success  = $true
        Data     = $Data
        Error    = $null
        Metadata = [ordered]@{
            Script    = $ScriptName
            Version   = $Version
            Timestamp = (Get-Date).ToUniversalTime().ToString('o')
        }
    }

    if ($resolvedFormat -eq 'JSON') {
        Write-Output ($envelope | ConvertTo-Json -Depth 10 -Compress)
    }
    else {
        $statusColor = switch ($Status) {
            'PASS'    { 'Green' }
            'FAIL'    { 'Red' }
            'WARNING' { 'Yellow' }
            'INFO'    { 'Cyan' }
        }
        $message = if ($HumanSummary) { $HumanSummary } else { 'Operation completed' }
        Write-Host "[$Status] $message" -ForegroundColor $statusColor
    }
}

function Write-SkillError {
    <#
    .SYNOPSIS
        Emits a standardized skill error envelope.

    .PARAMETER Message
        Human-readable error message.

    .PARAMETER ExitCode
        Exit code per ADR-035.

    .PARAMETER ErrorType
        Machine-readable error category.

    .PARAMETER OutputFormat
        Output format: JSON, Human, or Auto.

    .PARAMETER ScriptName
        Name of the calling script.

    .PARAMETER Version
        Script version string.

    .PARAMETER Extra
        Additional properties to merge into the Data field.

    .EXAMPLE
        Write-SkillError -Message "PR #999 not found" -ExitCode 2 -ErrorType NotFound
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [Parameter(Mandatory)]
        [int]$ExitCode,

        [Parameter()]
        [ValidateSet('NotFound', 'ApiError', 'AuthError', 'InvalidParams', 'Timeout', 'General')]
        [string]$ErrorType = 'General',

        [Parameter()]
        [ValidateSet('JSON', 'Human', 'Auto')]
        [string]$OutputFormat = 'Auto',

        [Parameter()]
        [string]$ScriptName,

        [Parameter()]
        [string]$Version = '1.0.0',

        [Parameter()]
        [hashtable]$Extra
    )

    $resolvedFormat = Get-OutputFormat -Requested $OutputFormat

    if (-not $ScriptName) {
        $ScriptName = if ($MyInvocation.PSCommandPath) {
            Split-Path $MyInvocation.PSCommandPath -Leaf
        }
        else {
            'unknown'
        }
    }

    $envelope = [ordered]@{
        Success  = $false
        Data     = if ($Extra) { $Extra } else { $null }
        Error    = [ordered]@{
            Message = $Message
            Code    = $ExitCode
            Type    = $ErrorType
        }
        Metadata = [ordered]@{
            Script    = $ScriptName
            Version   = $Version
            Timestamp = (Get-Date).ToUniversalTime().ToString('o')
        }
    }

    if ($resolvedFormat -eq 'JSON') {
        Write-Output ($envelope | ConvertTo-Json -Depth 10 -Compress)
    }
    else {
        Write-Host "[FAIL] $Message" -ForegroundColor Red
    }
}

function Add-OutputFormatParameter {
    <#
    .SYNOPSIS
        Helper to document OutputFormat parameter usage in scripts.
        Scripts should add the parameter directly in their param block.

    .DESCRIPTION
        This function exists only as documentation. Add this to your script param block:

        [Parameter()]
        [ValidateSet('JSON', 'Human', 'Auto')]
        [string]$OutputFormat = 'Auto'
    #>
    [CmdletBinding()]
    param()
    Write-Verbose 'Add -OutputFormat parameter to your script param block directly.'
}

Export-ModuleMember -Function @(
    'Get-OutputFormat'
    'Write-SkillOutput'
    'Write-SkillError'
    'Add-OutputFormatParameter'
)
