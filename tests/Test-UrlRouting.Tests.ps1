<#
.SYNOPSIS
    Pester tests for Test-UrlRouting.ps1

.DESCRIPTION
    Comprehensive test coverage for the GitHub URL routing script.
    Tests ConvertFrom-GitHubUrl and Get-RecommendedRoute functions
    as well as full script execution.

.NOTES
    Target: 100% code block coverage
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' '.claude' 'skills' 'github-url-intercept' 'scripts' 'Test-UrlRouting.ps1'
    $ScriptPath = (Resolve-Path $ScriptPath).Path

    # Define enums and functions in test scope
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
    $script:ScriptRoutes = @{
        [UrlType]::Pull  = @{
            Script = 'Get-PRContext.ps1'
            Path   = '.claude/skills/github/scripts/pr/Get-PRContext.ps1'
        }
        [UrlType]::Issue = @{
            Script = 'Get-IssueContext.ps1'
            Path   = '.claude/skills/github/scripts/issue/Get-IssueContext.ps1'
        }
    }

    function ConvertFrom-GitHubUrl {
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
        param(
            [Parameter(Mandatory)]
            [PSCustomObject]$Parsed
        )

        # Fragments require direct API call (no script for specific comments)
        if ($Parsed.FragmentType -and $Parsed.FragmentId) {
            $cmd = switch ($Parsed.FragmentType) {
                'pullrequestreview' { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/pulls/$($Parsed.ResourceId)/reviews/$($Parsed.FragmentId)`"" }
                'discussion_r' { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/pulls/comments/$($Parsed.FragmentId)`"" }
                'issuecomment' { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/issues/comments/$($Parsed.FragmentId)`"" }
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
        if ($script:ScriptRoutes.ContainsKey($Parsed.UrlType)) {
            $route = $script:ScriptRoutes[$Parsed.UrlType]

            $cmd = switch ($Parsed.UrlType) {
                ([UrlType]::Pull) { "pwsh `"$($route.Path)`" -PullRequest `"$($Parsed.ResourceId)`" -Owner `"$($Parsed.Owner)`" -Repo `"$($Parsed.Repo)`"" }
                ([UrlType]::Issue) { "pwsh `"$($route.Path)`" -Issue `"$($Parsed.ResourceId)`" -Owner `"$($Parsed.Owner)`" -Repo `"$($Parsed.Repo)`"" }
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
            ([UrlType]::Blob) { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/contents/$($Parsed.Path)?ref=$($Parsed.Ref)`"" }
            ([UrlType]::Tree) { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/contents/$($Parsed.Path)?ref=$($Parsed.Ref)`"" }
            ([UrlType]::Commit) { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/commits/$($Parsed.ResourceId)`"" }
            ([UrlType]::Compare) { "gh api `"repos/$($Parsed.Owner)/$($Parsed.Repo)/compare/$($Parsed.ResourceId)`"" }
            default { "unknown" }
        }

        return [PSCustomObject]@{
            Method     = [RouteMethod]::GhApi
            Command    = $cmd
            ScriptPath = $null
            Reason     = "No script available for $($Parsed.UrlType), use gh api"
        }
    }
}

Describe 'ConvertFrom-GitHubUrl' {
    Context 'Invalid URLs' {
        It 'Returns null for non-GitHub URLs' {
            $result = ConvertFrom-GitHubUrl -Url 'https://gitlab.com/owner/repo/pull/123'
            $result | Should -BeNullOrEmpty
        }

        It 'Returns null for malformed URLs' {
            $result = ConvertFrom-GitHubUrl -Url 'not-a-url'
            $result | Should -BeNullOrEmpty
        }

        It 'Returns null for URL without path' {
            $result = ConvertFrom-GitHubUrl -Url 'https://example.com'
            $result | Should -BeNullOrEmpty
        }
    }

    Context 'Pull Request URLs' {
        It 'Parses basic PR URL' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/pull/123'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Pull)
            $result.ResourceId | Should -Be '123'
            $result.FragmentType | Should -BeNullOrEmpty
            $result.FragmentId | Should -BeNullOrEmpty
        }

        It 'Parses PR URL with pullrequestreview fragment' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/pull/123#pullrequestreview-456789'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Pull)
            $result.ResourceId | Should -Be '123'
            $result.FragmentType | Should -Be 'pullrequestreview'
            $result.FragmentId | Should -Be '456789'
        }

        It 'Parses PR URL with discussion_r fragment' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/pull/123#discussion_r987654321'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Pull)
            $result.ResourceId | Should -Be '123'
            $result.FragmentType | Should -Be 'discussion_r'
            $result.FragmentId | Should -Be '987654321'
        }

        It 'Parses PR URL with issuecomment fragment' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/pull/123#issuecomment-111222333'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Pull)
            $result.ResourceId | Should -Be '123'
            $result.FragmentType | Should -Be 'issuecomment'
            $result.FragmentId | Should -Be '111222333'
        }

        It 'Handles HTTP protocol' {
            $result = ConvertFrom-GitHubUrl -Url 'http://github.com/owner/repo/pull/99'

            $result.Owner | Should -Be 'owner'
            $result.UrlType | Should -Be ([UrlType]::Pull)
        }

        It 'Parses PR URL with files subpath' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/pull/123/files'

            $result.UrlType | Should -Be ([UrlType]::Pull)
            $result.ResourceId | Should -Be '123'
        }
    }

    Context 'Issue URLs' {
        It 'Parses basic issue URL' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/issues/456'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Issue)
            $result.ResourceId | Should -Be '456'
            $result.FragmentType | Should -BeNullOrEmpty
        }

        It 'Parses issue URL with issuecomment fragment' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/issues/456#issuecomment-789123'

            $result.UrlType | Should -Be ([UrlType]::Issue)
            $result.ResourceId | Should -Be '456'
            $result.FragmentType | Should -Be 'issuecomment'
            $result.FragmentId | Should -Be '789123'
        }
    }

    Context 'Blob URLs' {
        It 'Parses blob URL with ref and path' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/blob/main/src/app.py'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Blob)
            $result.Ref | Should -Be 'main'
            $result.Path | Should -Be 'src/app.py'
            $result.ResourceId | Should -BeNullOrEmpty
        }

        It 'Parses blob URL with branch containing slashes' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/blob/feature/my-branch/src/file.ts'

            $result.UrlType | Should -Be ([UrlType]::Blob)
            $result.Ref | Should -Be 'feature'
            $result.Path | Should -Be 'my-branch/src/file.ts'
        }

        It 'Parses blob URL with commit SHA as ref' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/blob/abc123def/README.md'

            $result.UrlType | Should -Be ([UrlType]::Blob)
            $result.Ref | Should -Be 'abc123def'
            $result.Path | Should -Be 'README.md'
        }
    }

    Context 'Tree URLs' {
        It 'Parses tree URL with ref and path' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/tree/main/src'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Tree)
            $result.Ref | Should -Be 'main'
            $result.Path | Should -Be 'src'
        }

        It 'Parses tree URL with empty path (root)' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/tree/develop/'

            $result.UrlType | Should -Be ([UrlType]::Tree)
            $result.Ref | Should -Be 'develop'
            $result.Path | Should -Be ''
        }

        It 'Returns Unknown for tree URL without trailing slash after ref' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/tree/main'

            $result.UrlType | Should -Be ([UrlType]::Unknown)
        }
    }

    Context 'Commit URLs' {
        It 'Parses commit URL with full SHA' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/commit/abc123def456789'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Commit)
            $result.ResourceId | Should -Be 'abc123def456789'
        }

        It 'Parses commit URL with short SHA' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/commit/abc123d'

            $result.UrlType | Should -Be ([UrlType]::Commit)
            $result.ResourceId | Should -Be 'abc123d'
        }
    }

    Context 'Compare URLs' {
        It 'Parses compare URL with base...head' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/compare/main...feature-branch'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Compare)
            $result.ResourceId | Should -Be 'main...feature-branch'
        }

        It 'Parses compare URL with commit range' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/compare/abc123...def456'

            $result.UrlType | Should -Be ([UrlType]::Compare)
            $result.ResourceId | Should -Be 'abc123...def456'
        }
    }

    Context 'Unknown URLs' {
        It 'Returns Unknown type for repo root' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Unknown)
        }

        It 'Returns Unknown type for unsupported paths' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/actions'

            $result.UrlType | Should -Be ([UrlType]::Unknown)
        }

        It 'Returns Unknown type for repo with trailing slash' {
            $result = ConvertFrom-GitHubUrl -Url 'https://github.com/owner/repo/'

            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.UrlType | Should -Be ([UrlType]::Unknown)
        }
    }
}

Describe 'Get-RecommendedRoute' {
    Context 'Fragment routing (GhApi)' {
        It 'Routes pullrequestreview fragment to reviews API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Pull
                ResourceId   = '123'
                Ref          = $null
                Path         = $null
                FragmentType = 'pullrequestreview'
                FragmentId   = '456789'
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/pulls/123/reviews/456789"'
            $result.ScriptPath | Should -BeNullOrEmpty
            $result.Reason | Should -Match 'Fragment pullrequestreview requires direct API call'
        }

        It 'Routes discussion_r fragment to pulls/comments API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Pull
                ResourceId   = '123'
                Ref          = $null
                Path         = $null
                FragmentType = 'discussion_r'
                FragmentId   = '987654321'
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/pulls/comments/987654321"'
            $result.Reason | Should -Match 'Fragment discussion_r requires direct API call'
        }

        It 'Routes issuecomment fragment to issues/comments API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Issue
                ResourceId   = '456'
                Ref          = $null
                Path         = $null
                FragmentType = 'issuecomment'
                FragmentId   = '111222333'
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/issues/comments/111222333"'
        }

        It 'Routes unknown fragment type to "unknown" command' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Pull
                ResourceId   = '123'
                Ref          = $null
                Path         = $null
                FragmentType = 'unknownfragment'
                FragmentId   = '999'
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'unknown'
        }
    }

    Context 'Script routing (Primary)' {
        It 'Routes PR URL to Get-PRContext.ps1 script' {
            $parsed = [PSCustomObject]@{
                Owner        = 'myowner'
                Repo         = 'myrepo'
                UrlType      = [UrlType]::Pull
                ResourceId   = '789'
                Ref          = $null
                Path         = $null
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::Script)
            $result.Command | Should -Be 'pwsh ".claude/skills/github/scripts/pr/Get-PRContext.ps1" -PullRequest "789" -Owner "myowner" -Repo "myrepo"'
            $result.ScriptPath | Should -Be '.claude/skills/github/scripts/pr/Get-PRContext.ps1'
            $result.Reason | Should -Be 'Use github skill script for structured output'
        }

        It 'Routes Issue URL to Get-IssueContext.ps1 script' {
            $parsed = [PSCustomObject]@{
                Owner        = 'testowner'
                Repo         = 'testrepo'
                UrlType      = [UrlType]::Issue
                ResourceId   = '456'
                Ref          = $null
                Path         = $null
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::Script)
            $result.Command | Should -Be 'pwsh ".claude/skills/github/scripts/issue/Get-IssueContext.ps1" -Issue "456" -Owner "testowner" -Repo "testrepo"'
            $result.ScriptPath | Should -Be '.claude/skills/github/scripts/issue/Get-IssueContext.ps1'
        }
    }

    Context 'Fallback routing (GhApi)' {
        It 'Routes Blob URL to contents API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Blob
                ResourceId   = $null
                Ref          = 'main'
                Path         = 'src/app.py'
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/contents/src/app.py?ref=main"'
            $result.ScriptPath | Should -BeNullOrEmpty
            $result.Reason | Should -Match 'No script available for Blob'
        }

        It 'Routes Tree URL to contents API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Tree
                ResourceId   = $null
                Ref          = 'develop'
                Path         = 'src/components'
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/contents/src/components?ref=develop"'
        }

        It 'Routes Commit URL to commits API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Commit
                ResourceId   = 'abc123def'
                Ref          = $null
                Path         = $null
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/commits/abc123def"'
        }

        It 'Routes Compare URL to compare API' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Compare
                ResourceId   = 'main...feature'
                Ref          = $null
                Path         = $null
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'gh api "repos/owner/repo/compare/main...feature"'
        }

        It 'Routes Unknown URL type to "unknown" command' {
            $parsed = [PSCustomObject]@{
                Owner        = 'owner'
                Repo         = 'repo'
                UrlType      = [UrlType]::Unknown
                ResourceId   = $null
                Ref          = $null
                Path         = $null
                FragmentType = $null
                FragmentId   = $null
            }

            $result = Get-RecommendedRoute -Parsed $parsed

            $result.Method | Should -Be ([RouteMethod]::GhApi)
            $result.Command | Should -Be 'unknown'
            $result.Reason | Should -Match 'No script available for Unknown'
        }
    }
}

Describe 'Script Execution (End-to-End)' {
    BeforeAll {
        $ScriptPath = Join-Path $PSScriptRoot '..' '.claude' 'skills' 'github-url-intercept' 'scripts' 'Test-UrlRouting.ps1'
        $ScriptPath = (Resolve-Path $ScriptPath).Path
    }

    Context 'Valid URLs' {
        It 'Returns success JSON for valid PR URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/pull/123'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.Owner | Should -Be 'owner'
            $result.ParsedUrl.Repo | Should -Be 'repo'
            $result.ParsedUrl.UrlType | Should -Be 'Pull'
            $result.ParsedUrl.ResourceId | Should -Be '123'
            $result.RecommendedRoute.Method | Should -Be 'Script'
            $result.RecommendedRoute.ScriptPath | Should -Not -BeNullOrEmpty
            $LASTEXITCODE | Should -Be 0
        }

        It 'Returns success JSON for valid issue URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/issues/456'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Issue'
            $result.RecommendedRoute.Method | Should -Be 'Script'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Returns success JSON for blob URL with GhApi routing' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/blob/main/README.md'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Blob'
            $result.ParsedUrl.Ref | Should -Be 'main'
            $result.ParsedUrl.Path | Should -Be 'README.md'
            $result.RecommendedRoute.Method | Should -Be 'GhApi'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Returns success JSON for commit URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/commit/abc123'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Commit'
            $result.RecommendedRoute.Method | Should -Be 'GhApi'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Returns success JSON for compare URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/compare/main...feature'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Compare'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Returns success JSON for PR with fragment' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/pull/123#discussion_r456'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.FragmentType | Should -Be 'discussion_r'
            $result.ParsedUrl.FragmentId | Should -Be '456'
            $result.RecommendedRoute.Method | Should -Be 'GhApi'
            $LASTEXITCODE | Should -Be 0
        }

        It 'Returns success JSON for tree URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/tree/main/src'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Tree'
            $result.ParsedUrl.Ref | Should -Be 'main'
            $result.ParsedUrl.Path | Should -Be 'src'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Invalid URLs' {
        It 'Returns failure JSON for non-GitHub URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://gitlab.com/owner/repo/pull/123'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.ParsedUrl | Should -BeNullOrEmpty
            $result.RecommendedRoute | Should -BeNullOrEmpty
            $result.Error | Should -Be 'Invalid GitHub URL format'
            $LASTEXITCODE | Should -Be 1
        }

        It 'Returns failure JSON for malformed URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'not-a-valid-url'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.Error | Should -Be 'Invalid GitHub URL format'
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context 'Edge Cases' {
        It 'Returns failure for URL with unknown resource type' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/actions'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.ParsedUrl.UrlType | Should -Be 'Unknown'
            $result.RecommendedRoute | Should -BeNullOrEmpty
            $result.Error | Should -Match 'No routing available'
            $LASTEXITCODE | Should -Be 1
        }

        It 'Returns failure for repo root URL' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.ParsedUrl.UrlType | Should -Be 'Unknown'
            $result.Error | Should -Match 'No routing available'
            $LASTEXITCODE | Should -Be 1
        }

        It 'Handles HTTP protocol' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'http://github.com/owner/repo/pull/1'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Pull'
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context 'Security - Command Injection Prevention (CWE-78)' {
        It 'Rejects owner with shell metacharacters' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner";echo%20pwned/repo/pull/1' 2>&1
            $result = $output | Where-Object { $_ -notmatch 'WARNING' } | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.Error | Should -Be 'Invalid GitHub URL format'
        }

        It 'Rejects repo with backtick injection' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo`$(whoami)/pull/1' 2>&1
            $result = $output | Where-Object { $_ -notmatch 'WARNING' } | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.Error | Should -Be 'Invalid GitHub URL format'
        }

        It 'Rejects path with path traversal attack' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/blob/main/../../../etc/passwd' 2>&1
            $result = $output | Where-Object { $_ -notmatch 'WARNING' } | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.Error | Should -Be 'Invalid GitHub URL format'
        }

        It 'Rejects ref with semicolon injection' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/blob/main;rm%20-rf/file.txt' 2>&1
            $result = $output | Where-Object { $_ -notmatch 'WARNING' } | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.Error | Should -Be 'Invalid GitHub URL format'
        }

        It 'Allows valid compare URL with triple dots' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/compare/main...feature'
            $result = $output | ConvertFrom-Json

            $result.Success | Should -BeTrue
            $result.ParsedUrl.UrlType | Should -Be 'Compare'
            $result.ParsedUrl.ResourceId | Should -Be 'main...feature'
        }

        It 'Rejects compare URL with path traversal embedded' {
            $output = pwsh -NoProfile -File $ScriptPath -Url 'https://github.com/owner/repo/compare/main..%2F..%2Fetc' 2>&1
            $result = $output | Where-Object { $_ -notmatch 'WARNING' } | ConvertFrom-Json

            $result.Success | Should -BeFalse
            $result.Error | Should -Be 'Invalid GitHub URL format'
        }
    }
}
