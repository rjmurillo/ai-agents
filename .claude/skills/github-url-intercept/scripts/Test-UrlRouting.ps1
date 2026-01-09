<#
.SYNOPSIS
    Get the recommended routing for a GitHub URL.

.DESCRIPTION
    Parses a GitHub URL and returns the recommended command to fetch its
    content via API instead of HTML. Routes to github skill scripts when
    available, falls back to gh api for other resource types.

.PARAMETER Url
    The GitHub URL to route. Supports:
    - Pull requests: /pull/{n}, /pull/{n}#discussion_r{id}
    - Issues: /issues/{n}, /issues/{n}#issuecomment-{id}
    - Files: /blob/{ref}/{path}, /tree/{ref}/{path}
    - Commits: /commit/{sha}
    - Comparisons: /compare/{base}...{head}

.EXAMPLE
    .\Test-UrlRouting.ps1 -Url "https://github.com/owner/repo/pull/123"

.EXAMPLE
    .\Test-UrlRouting.ps1 -Url "https://github.com/owner/repo/blob/main/src/app.py"

.OUTPUTS
    JSON object with:
    - Success: Boolean indicating if URL was valid
    - ParsedUrl: Structured URL components
    - RecommendedRoute: Command to execute and reasoning

.NOTES
    Exit Codes:
      0 = Success
      1 = Invalid URL format
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Url
)

# URL type enum
enum UrlType {
    Pull
    Issue
    Blob
    Tree
    Commit
    Compare
    Unknown
}

# Route method enum
enum RouteMethod {
    Script    # Primary: github skill PowerShell script
    GhApi     # Fallback: gh api command
}

# Script routes (primary routing)
$ScriptRoutes = @{
    [UrlType]::Pull = @{
        Script = 'Get-PRContext.ps1'
        Path = '.claude/skills/github/scripts/pr/Get-PRContext.ps1'
    }
    [UrlType]::Issue = @{
        Script = 'Get-IssueContext.ps1'
        Path = '.claude/skills/github/scripts/issue/Get-IssueContext.ps1'
    }
}

function ConvertFrom-GitHubUrl {
    <#
    .SYNOPSIS
        Convert a GitHub URL into structured components.

    .DESCRIPTION
        Parses a GitHub URL and extracts owner, repo, resource type, and
        optional fragment identifiers (for specific comments/reviews).

    .PARAMETER Url
        The GitHub URL to parse.

    .OUTPUTS
        PSCustomObject with Owner, Repo, UrlType, ResourceId, Ref, Path,
        FragmentType, and FragmentId. Returns $null if invalid.
    #>
    param(
        [Parameter(Mandatory)]
        [string]$Url
    )

    $pattern = '^https?://github\.com/([^/]+)/([^/]+)/?(.*)$'
    if ($Url -notmatch $pattern) {
        return $null
    }

    $owner = $Matches[1]
    $repo = $Matches[2]
    $rest = $Matches[3]

    # Check for fragments
    $fragmentType = $null
    $fragmentId = $null

    if ($Url -match '#pullrequestreview-(\d+)') {
        $fragmentType = 'pullrequestreview'
        $fragmentId = $Matches[1]
        $rest = ($rest -split '#')[0]
    }
    elseif ($Url -match '#discussion_r(\d+)') {
        $fragmentType = 'discussion_r'
        $fragmentId = $Matches[1]
        $rest = ($rest -split '#')[0]
    }
    elseif ($Url -match '#issuecomment-(\d+)') {
        $fragmentType = 'issuecomment'
        $fragmentId = $Matches[1]
        $rest = ($rest -split '#')[0]
    }

    # Parse the path
    $urlType = [UrlType]::Unknown
    $resourceId = $null
    $ref = $null
    $path = $null

    if ($rest -match '^pull/(\d+)') {
        $urlType = [UrlType]::Pull
        $resourceId = $Matches[1]
    }
    elseif ($rest -match '^issues/(\d+)') {
        $urlType = [UrlType]::Issue
        $resourceId = $Matches[1]
    }
    elseif ($rest -match '^blob/([^/]+)/(.+)$') {
        $urlType = [UrlType]::Blob
        $ref = $Matches[1]
        $path = $Matches[2]
    }
    elseif ($rest -match '^tree/([^/]+)/(.*)$') {
        $urlType = [UrlType]::Tree
        $ref = $Matches[1]
        $path = $Matches[2]
    }
    elseif ($rest -match '^commit/([a-f0-9]+)') {
        $urlType = [UrlType]::Commit
        $resourceId = $Matches[1]
    }
    elseif ($rest -match '^compare/(.+)$') {
        $urlType = [UrlType]::Compare
        $resourceId = $Matches[1]
    }

    return [PSCustomObject]@{
        Owner        = $owner
        Repo         = $repo
        UrlType      = $urlType
        ResourceId   = $resourceId
        Ref          = $ref
        Path         = $path
        FragmentType = $fragmentType
        FragmentId   = $fragmentId
    }
}

function Get-RecommendedRoute {
    <#
    .SYNOPSIS
        Get the recommended routing command for a parsed URL.

    .DESCRIPTION
        Determines the optimal command for a parsed GitHub URL.
        Prioritizes github skill scripts for PRs and issues,
        falls back to gh api for fragments and other resource types.

    .PARAMETER Parsed
        PSCustomObject from ConvertFrom-GitHubUrl.

    .OUTPUTS
        PSCustomObject with Method, Command, ScriptPath, and Reason.
    #>
    param(
        [Parameter(Mandatory)]
        [PSCustomObject]$Parsed
    )

    # Fragments require direct API call (no script for specific comments)
    if ($Parsed.FragmentType -and $Parsed.FragmentId) {
        $cmd = switch ($Parsed.FragmentType) {
            'pullrequestreview' { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/pulls/$($Parsed.ResourceId)/reviews/$($Parsed.FragmentId)" }
            'discussion_r' { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/pulls/comments/$($Parsed.FragmentId)" }
            'issuecomment' { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/issues/comments/$($Parsed.FragmentId)" }
            default { "unknown" }
        }

        return [PSCustomObject]@{
            Method     = [RouteMethod]::GhApi
            Command    = $cmd
            ScriptPath = $null
            Reason     = "Fragment $($Parsed.FragmentType) requires direct API call"
        }
    }

    # Use scripts for PRs and issues (primary)
    if ($ScriptRoutes.ContainsKey($Parsed.UrlType)) {
        $route = $ScriptRoutes[$Parsed.UrlType]

        $cmd = switch ($Parsed.UrlType) {
            ([UrlType]::Pull) { "pwsh $($route.Path) -PullRequest $($Parsed.ResourceId) -Owner $($Parsed.Owner) -Repo $($Parsed.Repo)" }
            ([UrlType]::Issue) { "pwsh $($route.Path) -Issue $($Parsed.ResourceId) -Owner $($Parsed.Owner) -Repo $($Parsed.Repo)" }
        }

        return [PSCustomObject]@{
            Method     = [RouteMethod]::Script
            Command    = $cmd
            ScriptPath = $route.Path
            Reason     = "Use github skill script for structured output"
        }
    }

    # Fallback to gh api for blob/tree/commit/compare
    $cmd = switch ($Parsed.UrlType) {
        ([UrlType]::Blob) { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/contents/$($Parsed.Path)?ref=$($Parsed.Ref)" }
        ([UrlType]::Tree) { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/contents/$($Parsed.Path)?ref=$($Parsed.Ref)" }
        ([UrlType]::Commit) { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/commits/$($Parsed.ResourceId)" }
        ([UrlType]::Compare) { "gh api repos/$($Parsed.Owner)/$($Parsed.Repo)/compare/$($Parsed.ResourceId)" }
        default { "unknown" }
    }

    return [PSCustomObject]@{
        Method     = [RouteMethod]::GhApi
        Command    = $cmd
        ScriptPath = $null
        Reason     = "No script available for $($Parsed.UrlType), use gh api"
    }
}

# Main execution
$parsed = ConvertFrom-GitHubUrl -Url $Url

if (-not $parsed) {
    [PSCustomObject]@{
        Success          = $false
        ParsedUrl        = $null
        RecommendedRoute = $null
        Error            = "Invalid GitHub URL format"
    } | ConvertTo-Json -Depth 5
    exit 1
}

$recommended = Get-RecommendedRoute -Parsed $parsed

[PSCustomObject]@{
    Success          = $true
    ParsedUrl        = [PSCustomObject]@{
        Owner        = $parsed.Owner
        Repo         = $parsed.Repo
        UrlType      = $parsed.UrlType.ToString()
        ResourceId   = $parsed.ResourceId
        Ref          = $parsed.Ref
        Path         = $parsed.Path
        FragmentType = $parsed.FragmentType
        FragmentId   = $parsed.FragmentId
    }
    RecommendedRoute = [PSCustomObject]@{
        Method     = $recommended.Method.ToString()
        Command    = $recommended.Command
        ScriptPath = $recommended.ScriptPath
        Reason     = $recommended.Reason
    }
} | ConvertTo-Json -Depth 5

exit 0
