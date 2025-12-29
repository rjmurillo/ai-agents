<#
.SYNOPSIS
    Shared helper functions for GitHub CLI operations.

.DESCRIPTION
    Common utilities used across GitHub skill scripts:
    - Repository inference from git remote
    - GitHub CLI authentication check
    - Error handling with exit codes
    - Common formatting functions

.NOTES
    Import this module in scripts with:
    Import-Module (Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1") -Force

TABLE OF CONTENTS
=================
Input Validation (line ~30)
  - Test-GitHubNameValid     Validate owner/repo names (CWE-78 prevention)
  - Test-SafeFilePath        Prevent path traversal (CWE-22 prevention)
  - Assert-ValidBodyFile     Validate BodyFile parameter

Repository (line ~145)
  - Get-RepoInfo             Infer owner/repo from git remote
  - Resolve-RepoParams       Resolve or error on owner/repo

Authentication (line ~225)
  - Test-GhAuthenticated     Check gh CLI auth status
  - Assert-GhAuthenticated   Exit if not authenticated

Error Handling (line ~260)
  - Write-ErrorAndExit       Context-aware error handling (script vs module)

API Helpers (line ~320)
  - Invoke-GhApiPaginated    Fetch all pages from API

Issue Comments (line ~380)
  - Get-IssueComments        Fetch all comments for an issue
  - Update-IssueComment      Update an existing comment
  - New-IssueComment         Create a new issue comment

Trusted Sources (line ~600)
  - Get-TrustedSourceComments Filter comments by trusted users

Bot Configuration (line ~670)
  - Get-BotAuthors            Centralized bot author list

Rate Limit (line ~740)
  - Test-WorkflowRateLimit    Check API rate limits before workflow execution

Formatting (line ~840)
  - Get-PriorityEmoji        P0-P3 to emoji mapping
  - Get-ReactionEmoji        Reaction type to emoji
#>

#region Input Validation Functions

function Test-GitHubNameValid {
    <#
    .SYNOPSIS
        Validates GitHub owner or repository names.

    .DESCRIPTION
        Ensures names conform to GitHub's naming rules to prevent command injection (CWE-78).
        - Owner: alphanumeric and hyphens, 1-39 chars, cannot start/end with hyphen
        - Repo: alphanumeric, hyphens, underscores, periods, 1-100 chars

    .PARAMETER Name
        The name to validate.

    .PARAMETER Type
        The type of name: "Owner" or "Repo".

    .OUTPUTS
        Boolean indicating if the name is valid.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [ValidateSet("Owner", "Repo")]
        [string]$Type
    )

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return $false
    }

    $pattern = switch ($Type) {
        "Owner" { '^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$' }
        "Repo"  { '^[a-zA-Z0-9._-]{1,100}$' }
    }

    return $Name -match $pattern
}

function Test-SafeFilePath {
    <#
    .SYNOPSIS
        Validates that a file path does not traverse outside allowed boundaries.

    .DESCRIPTION
        Prevents path traversal attacks (CWE-22) by ensuring resolved path stays
        within the allowed base directory. Rejects paths with traversal attempts.

    .PARAMETER Path
        The file path to validate.

    .PARAMETER AllowedBase
        The base directory paths must stay within. Defaults to current directory.

    .OUTPUTS
        Boolean indicating if the path is safe.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter()]
        [string]$AllowedBase = (Get-Location).Path
    )

    # Reject obvious traversal attempts early
    if ($Path -match '\.\.[/\\]') {
        return $false
    }

    try {
        $resolvedPath = [System.IO.Path]::GetFullPath($Path)
        $resolvedBase = [System.IO.Path]::GetFullPath($AllowedBase)

        # Ensure resolved path starts with the allowed base
        return $resolvedPath.StartsWith($resolvedBase, [System.StringComparison]::OrdinalIgnoreCase)
    }
    catch {
        return $false
    }
}

function Assert-ValidBodyFile {
    <#
    .SYNOPSIS
        Validates a BodyFile parameter for safe file access.

    .DESCRIPTION
        Checks that the file exists and is within allowed boundaries.
        Exits with error if validation fails.

    .PARAMETER BodyFile
        The file path to validate.

    .PARAMETER AllowedBase
        Optional base directory restriction. If not provided, only checks existence.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$BodyFile,

        [Parameter()]
        [string]$AllowedBase
    )

    if (-not (Test-Path $BodyFile)) {
        Write-ErrorAndExit "Body file not found: $BodyFile" 2
    }

    if ($AllowedBase -and -not (Test-SafeFilePath -Path $BodyFile -AllowedBase $AllowedBase)) {
        Write-ErrorAndExit "Body file path traversal not allowed: $BodyFile" 1
    }
}

#endregion

#region Repository Functions

function Get-RepoInfo {
    <#
    .SYNOPSIS
        Infers repository owner and name from git remote.

    .DESCRIPTION
        Parses the git remote origin URL to extract GitHub owner and repo.
        Supports both HTTPS and SSH URLs.

    .OUTPUTS
        Hashtable with Owner and Repo keys, or $null if not found.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param()

    try {
        $remoteUrl = git remote get-url origin 2>$null
        if ($remoteUrl -match 'github\.com[:/]([^/]+)/([^/.]+)') {
            return @{
                Owner = $Matches[1]
                Repo  = $Matches[2] -replace '\.git$', ''
            }
        }
    }
    catch { }
    return $null
}

function Resolve-RepoParams {
    <#
    .SYNOPSIS
        Resolves Owner and Repo parameters, inferring if not provided.

    .DESCRIPTION
        Returns resolved Owner and Repo, or exits with error if cannot be determined.

    .PARAMETER Owner
        Repository owner (optional if in git repo).

    .PARAMETER Repo
        Repository name (optional if in git repo).

    .OUTPUTS
        Hashtable with Owner and Repo keys.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param(
        [string]$Owner,
        [string]$Repo
    )

    if (-not $Owner -or -not $Repo) {
        $repoInfo = Get-RepoInfo
        if ($repoInfo) {
            if (-not $Owner) { $Owner = $repoInfo.Owner }
            if (-not $Repo) { $Repo = $repoInfo.Repo }
        }
        else {
            Write-ErrorAndExit "Could not infer repository info. Please provide -Owner and -Repo parameters." 1
        }
    }

    # Validate names to prevent command injection (CWE-78)
    if (-not (Test-GitHubNameValid -Name $Owner -Type "Owner")) {
        Write-ErrorAndExit "Invalid GitHub owner name: $Owner" 1
    }
    if (-not (Test-GitHubNameValid -Name $Repo -Type "Repo")) {
        Write-ErrorAndExit "Invalid GitHub repository name: $Repo" 1
    }

    return @{
        Owner = $Owner
        Repo  = $Repo
    }
}

#endregion

#region Authentication Functions

function Test-GhAuthenticated {
    <#
    .SYNOPSIS
        Checks if GitHub CLI is installed and authenticated.

    .OUTPUTS
        Boolean indicating authentication status.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param()

    try {
        $null = gh auth status 2>&1
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Assert-GhAuthenticated {
    <#
    .SYNOPSIS
        Ensures GitHub CLI is authenticated, exits if not.
    #>
    [CmdletBinding()]
    param()

    if (-not (Test-GhAuthenticated)) {
        Write-ErrorAndExit "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first." 4
    }
}

#endregion

#region Error Handling Functions

function Write-ErrorAndExit {
    <#
    .SYNOPSIS
        Writes an error and exits with the specified code (or throws in module context).

    .DESCRIPTION
        Context-aware error handling:
        - When called from a script: exits with the specified code (for CLI compatibility)
        - When called from a module/interactive: throws an exception (for proper error propagation)

        This design prevents the module from terminating the PowerShell session when used
        in module context while maintaining backward compatibility with script usage.

    .PARAMETER Message
        Error message to display.

    .PARAMETER ExitCode
        Exit code to return (used in script context, embedded in exception in module context).

    .NOTES
        Part of PR #60 Phase 1 remediation - GAP-QUAL-001 fix.
        Modules should not use `exit` as it terminates the session.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    # Determine execution context
    # $MyInvocation.ScriptName is empty when called interactively or from a module function
    # but contains the script path when called from a .ps1 script
    $callerInfo = (Get-PSCallStack)[1]
    $isScriptContext = $callerInfo.ScriptName -and ($callerInfo.ScriptName -match '\.ps1$')

    if ($isScriptContext) {
        # Called from a script - use exit for proper CLI integration
        Write-Error $Message
        exit $ExitCode
    }
    else {
        # Called from module/interactive - throw for proper error propagation
        # Include exit code in exception for callers that need it
        $exception = [System.Management.Automation.RuntimeException]::new(
            "$Message (Exit code: $ExitCode)"
        )
        $exception.Data['ExitCode'] = $ExitCode
        throw $exception
    }
}

#endregion

#region API Helper Functions

function Invoke-GhApiPaginated {
    <#
    .SYNOPSIS
        Calls GitHub API with pagination support.

    .DESCRIPTION
        Fetches all pages of results from a paginated API endpoint.

    .PARAMETER Endpoint
        The API endpoint (e.g., "repos/owner/repo/pulls/1/comments").

    .PARAMETER PageSize
        Number of items per page (default: 100, max: 100).

    .OUTPUTS
        Array of all items across all pages.
    #>
    [CmdletBinding()]
    [OutputType([array])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Endpoint,

        [Parameter()]
        [ValidateRange(1, 100)]
        [int]$PageSize = 100
    )

    $allItems = [System.Collections.Generic.List[object]]::new()
    $page = 1

    do {
        Write-Verbose "Fetching page $page from $Endpoint"

        $separator = if ($Endpoint -match '\?') { '&' } else { '?' }
        $url = "$Endpoint${separator}per_page=$PageSize&page=$page"

        $response = gh api $url 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "API request failed: $response"
            break
        }

        $items = $response | ConvertFrom-Json

        if ($null -eq $items -or $items.Count -eq 0) {
            break
        }

        foreach ($item in $items) {
            $allItems.Add($item)
        }

        $page++
    } while ($items.Count -eq $PageSize)

    return @($allItems)
}

#endregion

#region Formatting Functions

function Get-PriorityEmoji {
    <#
    .SYNOPSIS
        Returns the emoji for a priority level.

    .PARAMETER Priority
        Priority level (P0, P1, P2, P3).

    .OUTPUTS
        Emoji string.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Priority
    )

    switch ($Priority) {
        "P0" { return "🔥" }  # Fire = critical/urgent
        "P1" { return "❗" }  # Exclamation = important
        "P2" { return "➖" }  # Dash = normal/medium
        "P3" { return "⬇️" }  # Down arrow = low
        default { return "❔" }  # Unknown
    }
}

function Get-ReactionEmoji {
    <#
    .SYNOPSIS
        Returns the emoji for a GitHub reaction type.

    .PARAMETER Reaction
        Reaction type (+1, -1, laugh, confused, heart, hooray, rocket, eyes).

    .OUTPUTS
        Emoji string.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Reaction
    )

    switch ($Reaction) {
        "+1" { return "👍" }
        "-1" { return "👎" }
        "laugh" { return "😄" }
        "confused" { return "😕" }
        "heart" { return "❤️" }
        "hooray" { return "🎉" }
        "rocket" { return "🚀" }
        "eyes" { return "👀" }
        default { return $Reaction }
    }
}

#endregion

#region Issue Comment Functions

function Get-IssueComments {
    <#
    .SYNOPSIS
        Fetches all comments for a GitHub issue with pagination support.

    .PARAMETER Owner
        Repository owner.

    .PARAMETER Repo
        Repository name.

    .PARAMETER IssueNumber
        The issue number.

    .OUTPUTS
        Array of comment objects.
    #>
    [CmdletBinding()]
    [OutputType([array])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$IssueNumber
    )

    return Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$IssueNumber/comments"
}

function Update-IssueComment {
    <#
    .SYNOPSIS
        Updates an existing GitHub issue comment.

    .PARAMETER Owner
        Repository owner.

    .PARAMETER Repo
        Repository name.

    .PARAMETER CommentId
        The comment ID to update.

    .PARAMETER Body
        The new comment body.

    .OUTPUTS
        Updated comment object.
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [long]$CommentId,

        [Parameter(Mandatory)]
        [string]$Body
    )

    # Use JSON payload via --input to handle large/complex bodies correctly
    $payload = @{ body = $Body } | ConvertTo-Json -Compress
    $tempFile = New-TemporaryFile

    try {
        Set-Content -Path $tempFile.FullName -Value $payload -Encoding utf8

        $result = gh api "repos/$Owner/$Repo/issues/comments/$CommentId" -X PATCH --input $tempFile.FullName 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-ErrorAndExit "Failed to update comment: $result" 3
        }

        return $result | ConvertFrom-Json
    }
    finally {
        if (Test-Path -LiteralPath $tempFile.FullName) {
            Remove-Item -LiteralPath $tempFile.FullName -ErrorAction SilentlyContinue
        }
    }
}

function New-IssueComment {
    <#
    .SYNOPSIS
        Creates a new GitHub issue comment.

    .PARAMETER Owner
        Repository owner.

    .PARAMETER Repo
        Repository name.

    .PARAMETER IssueNumber
        The issue number.

    .PARAMETER Body
        The comment body.

    .OUTPUTS
        Created comment object.
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$IssueNumber,

        [Parameter(Mandatory)]
        [string]$Body
    )

    # Use JSON payload via --input to handle large/complex bodies correctly
    $payload = @{ body = $Body } | ConvertTo-Json -Compress
    $tempFile = New-TemporaryFile

    try {
        Set-Content -Path $tempFile.FullName -Value $payload -Encoding utf8

        $result = gh api "repos/$Owner/$Repo/issues/$IssueNumber/comments" -X POST --input $tempFile.FullName 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-ErrorAndExit "Failed to post comment: $result" 3
        }

        return $result | ConvertFrom-Json
    }
    finally {
        if (Test-Path -LiteralPath $tempFile.FullName) {
            Remove-Item -LiteralPath $tempFile.FullName -ErrorAction SilentlyContinue
        }
    }
}

#endregion

#region Trusted Source Functions

function Get-TrustedSourceComments {
    <#
    .SYNOPSIS
        Filters comments to those from trusted sources.

    .DESCRIPTION
        Useful for extracting reliable information from maintainers and trusted AI agents.
        See pr-comment-responder for usage context.

    .PARAMETER Comments
        Array of comment objects with user.login property.

    .PARAMETER TrustedUsers
        Array of trusted usernames to filter by.

    .OUTPUTS
        Filtered array of comments from trusted sources.
    #>
    [CmdletBinding()]
    [OutputType([array])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [array]$Comments,

        [Parameter(Mandatory)]
        [string[]]$TrustedUsers
    )

    if ($Comments.Count -eq 0) {
        return @()
    }

    return $Comments | Where-Object {
        $TrustedUsers -contains $_.user.login
    }
}

#endregion

#region Bot Configuration Functions

function Get-BotAuthors {
    <#
    .SYNOPSIS
        Returns the centralized list of known bot authors.

    .DESCRIPTION
        Single source of truth for bot author identification across the repository.
        Used by workflows, scripts, and agents to distinguish bot vs. human activity.

    .PARAMETER Category
        Optional. Filter by category: 'reviewer', 'automation', 'repository', 'all' (default).

    .OUTPUTS
        String array of bot author login names.

    .EXAMPLE
        $bots = Get-BotAuthors
        if ($comment.user.login -in $bots) { Write-Host "Bot comment" }

    .NOTES
        See #282 for centralization rationale.
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param(
        [Parameter()]
        [ValidateSet('reviewer', 'automation', 'repository', 'all')]
        [string]$Category = 'all'
    )

    $bots = @{
        reviewer = @(
            'coderabbitai[bot]'
            'github-copilot[bot]'
            'gemini-code-assist[bot]'
            'cursor[bot]'
        )
        automation = @(
            'github-actions[bot]'
            'dependabot[bot]'
        )
        repository = @(
            'rjmurillo-bot'
            'copilot-swe-agent[bot]'
        )
    }

    if ($Category -eq 'all') {
        return $bots.Values | ForEach-Object { $_ } | Sort-Object -Unique
    }

    return $bots[$Category]
}

#endregion

#region Rate Limit Functions

function Test-WorkflowRateLimit {
    <#
    .SYNOPSIS
        Checks GitHub API rate limits before workflow execution.

    .DESCRIPTION
        Validates that all required API resource types have sufficient
        remaining quota. Returns structured results for workflow decisions.

    .PARAMETER ResourceThresholds
        Hashtable of resource names to minimum remaining threshold.

    .OUTPUTS
        PSCustomObject with Success, Resources, SummaryMarkdown, CoreRemaining.

    .EXAMPLE
        $result = Test-WorkflowRateLimit
        if (-not $result.Success) { Write-Error "Rate limit too low"; exit 1 }

    .NOTES
        Extracted from PRMaintenanceModule per #275.
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [hashtable]$ResourceThresholds = @{
            'core'        = 100
            'search'      = 15
            'code_search' = 5
            'graphql'     = 100
        }
    )

    $rateLimitJson = gh api rate_limit 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch rate limits: $rateLimitJson"
    }

    $rateLimit = $rateLimitJson | ConvertFrom-Json
    $resources = @{}
    $allPassed = $true
    $summaryLines = @(
        "### API Rate Limit Status",
        "",
        "| Resource | Remaining | Threshold | Status |",
        "|----------|-----------|-----------|--------|"
    )

    foreach ($resource in $ResourceThresholds.Keys) {
        $remaining = $rateLimit.resources.$resource.remaining
        $limit = $rateLimit.resources.$resource.limit
        $reset = $rateLimit.resources.$resource.reset
        $threshold = $ResourceThresholds[$resource]
        $passed = $remaining -ge $threshold

        if (-not $passed) { $allPassed = $false }

        $status = if ($passed) { "OK" } else { "TOO LOW" }
        $statusIcon = if ($passed) { "+" } else { "X" }

        $resources[$resource] = @{
            Remaining = $remaining
            Limit     = $limit
            Reset     = $reset
            Threshold = $threshold
            Passed    = $passed
        }

        $summaryLines += "| $resource | $remaining | $threshold | $statusIcon $status |"
    }

    return [PSCustomObject]@{
        Success         = $allPassed
        Resources       = $resources
        SummaryMarkdown = $summaryLines -join "`n"
        CoreRemaining   = $rateLimit.resources.core.remaining
    }
}

#endregion

#region Exit Codes

<#
Standard exit codes for GitHub skill scripts:
    0 - Success
    1 - Invalid parameters
    2 - Resource not found (PR, issue, label, milestone)
    3 - GitHub API error
    4 - gh CLI not found or not authenticated
    5 - Idempotency skip (e.g., comment already exists)
#>

#endregion

# Export functions
Export-ModuleMember -Function @(
    # Validation
    'Test-GitHubNameValid'
    'Test-SafeFilePath'
    'Assert-ValidBodyFile'
    # Repository
    'Get-RepoInfo'
    'Resolve-RepoParams'
    # Authentication
    'Test-GhAuthenticated'
    'Assert-GhAuthenticated'
    # Error handling
    'Write-ErrorAndExit'
    # API helpers
    'Invoke-GhApiPaginated'
    # Issue comments
    'Get-IssueComments'
    'Update-IssueComment'
    'New-IssueComment'
    # Trusted sources
    'Get-TrustedSourceComments'
    # Bot configuration
    'Get-BotAuthors'
    # Rate limit
    'Test-WorkflowRateLimit'
    # Formatting
    'Get-PriorityEmoji'
    'Get-ReactionEmoji'
)
