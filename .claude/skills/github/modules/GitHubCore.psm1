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
    Import-Module (Join-Path $PSScriptRoot ".." "modules" "GitHubCore.psm1") -Force

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

API Helpers (line ~365)
  - Invoke-GhApiPaginated    Fetch all pages from API
  - Invoke-GhGraphQL         Execute GraphQL queries/mutations
  - Get-AllPRsWithComments   Fetch PRs with review comments via GraphQL

Issue Comments (line ~380)
  - Get-IssueComments        Fetch all comments for an issue
  - Update-IssueComment      Update an existing comment
  - New-IssueComment         Create a new issue comment

Trusted Sources (line ~600)
  - Get-TrustedSourceComments Filter comments by trusted users

Bot Configuration (line ~680)
  - Get-BotAuthorsConfig      Load bot authors from .github/bot-authors.yml
  - Get-BotAuthors            Centralized bot author list

PR Review (line ~997)
  - Get-UnresolvedReviewThreads Get unresolved PR review threads

Rate Limit (line ~1102)
  - Test-WorkflowRateLimit    Check API rate limits before workflow execution

Formatting (line ~1200)
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
            $errorMsg = "GitHub API request failed for endpoint '$Endpoint' (page $page): $response"
            if ($page -eq 1) {
                # First page failure is fatal - no partial data to return
                Write-ErrorAndExit $errorMsg 3
            } else {
                # Mid-pagination failure - return partial results
                Write-Warning "$errorMsg. Returning partial results from $($allItems.Count) items."
                break
            }
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

function Invoke-GhGraphQL {
    <#
    .SYNOPSIS
        Executes a GitHub GraphQL query or mutation.

    .DESCRIPTION
        Wrapper around gh api graphql that provides consistent error handling
        and response parsing. Supports query variables for safe parameterization.

    .PARAMETER Query
        The GraphQL query or mutation string.

    .PARAMETER Variables
        Hashtable of variables to pass to the query.
        String values use -f, Integer values use -F.

    .OUTPUTS
        Parsed JSON response data, or throws on error.

    .EXAMPLE
        $result = Invoke-GhGraphQL -Query 'query { viewer { login } }'
        $result.viewer.login

    .EXAMPLE
        $query = 'query($owner: String!, $repo: String!) { repository(owner: $owner, name: $repo) { name } }'
        $vars = @{ owner = "rjmurillo"; repo = "ai-agents" }
        $result = Invoke-GhGraphQL -Query $query -Variables $vars

    .NOTES
        Uses GraphQL variables to prevent injection attacks (ADR-015 compliant).
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Query,

        [Parameter()]
        [hashtable]$Variables = @{}
    )

    # Build gh api graphql command arguments
    $ghArgs = @('api', 'graphql', '-f', "query=$Query")

    # Add variables with appropriate flag based on type
    foreach ($key in $Variables.Keys) {
        $value = $Variables[$key]
        if ($value -is [int] -or $value -is [long] -or $value -is [bool]) {
            # Use -F for non-string values
            $ghArgs += @('-F', "${key}=$value")
        }
        else {
            # Use -f for string values
            $ghArgs += @('-f', "${key}=$value")
        }
    }

    Write-Verbose "Executing GraphQL query with $($Variables.Count) variables"

    $result = & gh @ghArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        # Extract error message for better diagnostics
        $errorMsg = $result -join ' '
        if ($errorMsg -match '"message"\s*:\s*"([^"]+)"') {
            $errorMsg = $Matches[1]
        }
        throw "GraphQL request failed: $errorMsg"
    }

    try {
        $parsed = $result | ConvertFrom-Json
    }
    catch {
        throw "Failed to parse GraphQL response: $result"
    }

    # Check for GraphQL-level errors
    if ($parsed.errors) {
        $errorMessages = $parsed.errors | ForEach-Object { $_.message }
        throw "GraphQL errors: $($errorMessages -join '; ')"
    }

    return $parsed.data
}

function Get-AllPRsWithComments {
    <#
    .SYNOPSIS
        Query PRs with review comments using GitHub GraphQL API with pagination.

    .DESCRIPTION
        Fetches all PRs (open and closed) from the specified time range that have
        review comments. Uses GraphQL for efficient querying with cursor-based
        pagination. PRs are ordered by updatedAt DESC, so pagination stops when
        PRs fall outside the requested time range.

        Limitations:
        - Maximum 50 pages (2500 PRs) per invocation as a safety limit.
        - Only first 50 comments per review thread are fetched.

    .PARAMETER Owner
        Repository owner.

    .PARAMETER Repo
        Repository name.

    .PARAMETER Since
        Only include PRs updated since this date.

    .PARAMETER MaxPages
        Maximum number of pagination pages. Default: 50.

    .OUTPUTS
        Array of PR objects with review thread data. Each PR includes:
        number, title, state, author, createdAt, updatedAt, mergedAt, closedAt,
        and reviewThreads with comments.
    #>
    [CmdletBinding()]
    [OutputType([array])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [datetime]$Since,

        [Parameter()]
        [ValidateRange(1, [int]::MaxValue)]
        [int]$MaxPages = 50
    )

    $allPRs = [System.Collections.ArrayList]::new()
    $cursor = $null
    $hasNextPage = $true
    $pageCount = 0

    Write-Verbose "Fetching PRs updated since $($Since.ToString('yyyy-MM-dd'))..."

    $query = @'
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}, after: $cursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        state
        author { login }
        createdAt
        updatedAt
        mergedAt
        closedAt
        reviewThreads(first: 100) {
          nodes {
            isResolved
            isOutdated
            comments(first: 50) {
              nodes {
                id
                body
                author { login }
                createdAt
                path
              }
            }
          }
        }
      }
    }
  }
}
'@

    while ($hasNextPage -and $pageCount -lt $MaxPages) {
        $pageCount++

        $variables = @{
            owner = $Owner
            repo  = $Repo
        }
        if ($cursor) {
            $variables.cursor = $cursor
        }

        $result = Invoke-GhGraphQL -Query $query -Variables $variables
        $prData = $result.repository.pullRequests

        foreach ($pr in $prData.nodes) {
            # Check if PR was updated within our time range
            $updatedAt = [datetime]::Parse($pr.updatedAt)
            if ($updatedAt -lt $Since) {
                # PRs are ordered by updatedAt DESC, so we can stop here
                $hasNextPage = $false
                break
            }

            # Only include PRs that have review comments
            $hasComments = $pr.reviewThreads.nodes | Where-Object { $_.comments.nodes.Count -gt 0 }
            if ($hasComments) {
                $null = $allPRs.Add($pr)
            }
        }

        # Check pagination
        if ($hasNextPage) {
            $hasNextPage = $prData.pageInfo.hasNextPage
            $cursor = $prData.pageInfo.endCursor
        }

        Write-Verbose "Page $pageCount processed, total PRs with comments: $($allPRs.Count)"
    }

    if ($pageCount -ge $MaxPages) {
        Write-Warning "Reached maximum page limit ($MaxPages)"
    }

    Write-Verbose "Found $($allPRs.Count) PRs with review comments"
    return , $allPRs.ToArray()
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

    .NOTES
        Exit codes:
        - 3: Generic API error
        - 4: Permission denied (403) - includes actionable guidance
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
            $errorString = $result -join ' '

            # Detect 403 permission errors (case-insensitive matching)
            # Exit code 4 = Auth error (per ADR-035: includes not-authenticated AND permission-denied)
            # Pattern uses negative lookarounds (?<!\d)403(?!\d) to prevent false positives (e.g., ID403)
            if ($errorString -imatch '((?<!\d)403(?!\d)|\bforbidden\b|Resource not accessible by integration)') {
                $guidance = @"
PERMISSION DENIED (403): Cannot update comment $CommentId in $Owner/$Repo.

LIKELY CAUSES:
- GitHub Apps: Missing "issues": "write" permission in app manifest
- Workflow GITHUB_TOKEN: Add 'permissions: issues: write' to workflow YAML
- Fine-grained PAT: Enable 'Issues' repository permission (Read and Write)
- Classic PAT: Requires 'repo' scope for private repos or 'public_repo' for public repos
- Not the comment author: Only the comment author or repo admin can edit comments

RAW ERROR: $errorString
"@
                Write-ErrorAndExit $guidance 4
            }

            # Generic API error
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

# Script-level cache for bot authors config
$script:BotAuthorsCache = $null
$script:BotAuthorsCachePath = $null

function Get-BotAuthorsConfig {
    <#
    .SYNOPSIS
        Loads and caches bot authors configuration from .github/bot-authors.yml.

    .DESCRIPTION
        Reads the bot authors YAML configuration file and parses it into a hashtable.
        Results are cached at the script level for performance.

    .PARAMETER ConfigPath
        Optional. Path to the config file. Defaults to .github/bot-authors.yml in repo root.

    .PARAMETER Force
        Force reload from disk, ignoring cache.

    .OUTPUTS
        Hashtable with 'reviewer', 'automation', 'repository' keys.

    .NOTES
        Uses simple YAML parsing since PowerShell doesn't have native YAML support.
        Falls back to default values if file is missing or invalid.
        See #276 for dynamic bot author list rationale.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param(
        [Parameter()]
        [string]$ConfigPath,

        [Parameter()]
        [switch]$Force
    )

    # Default config values (fallback)
    $defaultBots = @{
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

    # Determine config path
    if (-not $ConfigPath) {
        # Find repo root by looking for .git directory
        $searchPath = $PSScriptRoot
        while ($searchPath -and -not (Test-Path (Join-Path $searchPath '.git'))) {
            $searchPath = Split-Path $searchPath -Parent
        }
        if ($searchPath) {
            $ConfigPath = Join-Path $searchPath '.github' 'bot-authors.yml'
        }
    }

    # Return cached result if available and not forced
    if (-not $Force -and $script:BotAuthorsCache -and $script:BotAuthorsCachePath -eq $ConfigPath) {
        return $script:BotAuthorsCache
    }

    # Try to read config file
    if (-not $ConfigPath -or -not (Test-Path $ConfigPath)) {
        Write-Verbose "Bot authors config not found at $ConfigPath, using defaults"
        $script:BotAuthorsCache = $defaultBots
        $script:BotAuthorsCachePath = $ConfigPath
        return $defaultBots
    }

    # Validate config path to prevent path traversal (CWE-22)
    try {
        # Find repo root
        $repoRoot = $PSScriptRoot
        while ($repoRoot -and -not (Test-Path (Join-Path $repoRoot '.git'))) {
            $repoRoot = Split-Path $repoRoot -Parent
        }

        if (-not $repoRoot) {
            throw "Could not determine repository root directory"
        }

        # Resolve absolute paths for comparison
        $resolvedConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
        $resolvedRepoRoot = [System.IO.Path]::GetFullPath($repoRoot)

        # Ensure config path is within repo root (case-insensitive for Windows)
        if (-not $resolvedConfigPath.StartsWith($resolvedRepoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Config path '$ConfigPath' is outside repository root '$repoRoot'"
        }
    }
    catch {
        Write-Warning "Path validation failed: $($_.Exception.Message), using defaults"
        $script:BotAuthorsCache = $defaultBots
        $script:BotAuthorsCachePath = $ConfigPath
        return $defaultBots
    }

    try {
        $lines = Get-Content $ConfigPath -ErrorAction Stop
        $bots = @{
            reviewer = @()
            automation = @()
            repository = @()
        }

        # Simple YAML parsing for our specific format
        $currentSection = $null
        foreach ($line in $lines) {
            $line = $line.TrimEnd()

            # Skip comments and empty lines
            if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }

            # Check for section headers (reviewer:, automation:, repository:)
            if ($line -match '^(reviewer|automation|repository):\s*$') {
                $currentSection = $matches[1]
                continue
            }

            # Check for list items (  - value)
            if ($currentSection -and $line -match '^\s+-\s+(.+)$') {
                $value = $matches[1].Trim()
                $bots[$currentSection] += $value
            }
        }

        # Validate we got at least some entries
        $totalBots = $bots.Values | ForEach-Object { $_.Count } | Measure-Object -Sum | Select-Object -ExpandProperty Sum
        if ($totalBots -eq 0) {
            Write-Verbose "Bot authors config was empty, using defaults"
            $script:BotAuthorsCache = $defaultBots
            $script:BotAuthorsCachePath = $ConfigPath
            return $defaultBots
        }

        $script:BotAuthorsCache = $bots
        $script:BotAuthorsCachePath = $ConfigPath
        return $bots
    }
    catch {
        Write-Warning "Failed to parse bot authors config: $($_.Exception.Message), using defaults"
        $script:BotAuthorsCache = $defaultBots
        $script:BotAuthorsCachePath = $ConfigPath
        return $defaultBots
    }
}

function Get-BotAuthors {
    <#
    .SYNOPSIS
        Returns the centralized list of known bot authors.

    .DESCRIPTION
        Single source of truth for bot author identification across the repository.
        Used by workflows, scripts, and agents to distinguish bot vs. human activity.

        Reads from .github/bot-authors.yml config file with fallback to hardcoded defaults.

    .PARAMETER Category
        Optional. Filter by category: 'reviewer', 'automation', 'repository', 'all' (default).

    .OUTPUTS
        String array of bot author login names.

    .EXAMPLE
        $bots = Get-BotAuthors
        if ($comment.user.login -in $bots) { Write-Host "Bot comment" }

    .NOTES
        See #276 for dynamic bot author list (config-based).
        See #282 for centralization rationale.
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param(
        [Parameter()]
        [ValidateSet('reviewer', 'automation', 'repository', 'all')]
        [string]$Category = 'all'
    )

    $bots = Get-BotAuthorsConfig

    if ($Category -eq 'all') {
        return $bots.Values | ForEach-Object { $_ } | Sort-Object -Unique
    }

    return $bots[$Category]
}

#endregion

#region PR Review Functions

function Get-UnresolvedReviewThreads {
    <#
    .SYNOPSIS
        Retrieves review threads that remain unresolved on a pull request.

    .DESCRIPTION
        Uses GitHub GraphQL API to query review thread resolution status.
        Part of the "Acknowledged vs Resolved" lifecycle model:

        NEW -> ACKNOWLEDGED (eyes reaction) -> REPLIED -> RESOLVED (thread marked resolved)

        A comment can be acknowledged (has eyes reaction) but NOT resolved (thread still open).
        This function identifies threads in that intermediate state.

    .PARAMETER Owner
        Repository owner.

    .PARAMETER Repo
        Repository name.

    .PARAMETER PullRequest
        Pull request number.

    .OUTPUTS
        Array of thread objects where isResolved = false.
        Each object contains: id, isResolved, comments (first comment with databaseId).
        Returns empty array when all threads are resolved or on API failure.
        Never returns $null (per Skill-PowerShell-002).

    .EXAMPLE
        $threads = Get-UnresolvedReviewThreads -Owner "rjmurillo" -Repo "ai-agents" -PullRequest 365
        if ($threads.Count -gt 0) {
            Write-Host "Found $($threads.Count) unresolved threads"
        }

    .NOTES
        GraphQL query handles up to 100 threads per request.
        Pagination not implemented for edge cases with 100+ threads.
    #>
    [CmdletBinding()]
    [OutputType([array])]
    param(
        [Parameter(Mandatory)]
        [string]$Owner,

        [Parameter(Mandatory)]
        [string]$Repo,

        [Parameter(Mandatory)]
        [int]$PullRequest
    )

    # GraphQL query per FR1 specification
    # Note: first: 100 handles most PRs; pagination not implemented for edge cases with 100+ threads
    # Uses GraphQL variables for security (prevents injection via Owner/Repo/PR)
    $query = @'
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                        }
                    }
                }
            }
        }
    }
}
'@

    $result = gh api graphql -f query=$query -f owner="$Owner" -f name="$Repo" -F prNumber=$PullRequest 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to query review threads for PR #${PullRequest}: $result"
        return @()  # Return empty array on failure per FR2
    }

    try {
        $parsed = $result | ConvertFrom-Json
    }
    catch {
        Write-Warning "Failed to parse GraphQL response for PR #${PullRequest}: $result"
        return @()  # Return empty array on parse failure
    }

    $threads = $parsed.data.repository.pullRequest.reviewThreads.nodes

    if ($null -eq $threads -or $threads.Count -eq 0) {
        return @()  # No threads exist
    }

    # Filter to unresolved threads only
    $unresolved = @($threads | Where-Object { -not $_.isResolved })

    return $unresolved  # Always returns array, never $null
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
        # Check if resource exists in API response (null safety for API changes)
        $resourceData = $rateLimit.resources.$resource
        if ($null -eq $resourceData) {
            Write-Warning "Resource '$resource' not found in rate limit response"
            $allPassed = $false
            $summaryLines += "| $resource | N/A | $($ResourceThresholds[$resource]) | X MISSING |"
            continue
        }

        $remaining = $resourceData.remaining
        $limit = $resourceData.limit
        $reset = $resourceData.reset
        $threshold = $ResourceThresholds[$resource]
        $passed = $remaining -ge $threshold

        if (-not $passed) { $allPassed = $false }

        # PowerShell 5.1 compatibility: wrap if expressions in script blocks
        $status = & { if ($passed) { "OK" } else { "TOO LOW" } }
        $statusIcon = & { if ($passed) { "+" } else { "X" } }

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
Standard exit codes for GitHub skill scripts (per ADR-035):
    0 - Success (includes idempotency skip - e.g., comment already exists)
    1 - Invalid parameters / logic error
    2 - Config error (resource not found, missing dependency)
    3 - External error (GitHub API failure, network error)
    4 - Auth error (not authenticated, permission denied 403, rate limited)
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
    'Invoke-GhGraphQL'
    'Get-AllPRsWithComments'
    # Issue comments
    'Get-IssueComments'
    'Update-IssueComment'
    'New-IssueComment'
    # Trusted sources
    'Get-TrustedSourceComments'
    # Bot configuration
    'Get-BotAuthorsConfig'
    'Get-BotAuthors'
    # PR review
    'Get-UnresolvedReviewThreads'
    # Rate limit
    'Test-WorkflowRateLimit'
    # Formatting
    'Get-PriorityEmoji'
    'Get-ReactionEmoji'
)
