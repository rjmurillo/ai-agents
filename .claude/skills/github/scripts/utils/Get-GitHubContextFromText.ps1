function Get-GitHubContextFromText {
    <#
    .SYNOPSIS
        Extract PR/issue numbers and repository context from natural language or URLs.

    .DESCRIPTION
        Parses user input to extract GitHub PR or issue numbers and repository information
        from various formats including:
        - Text patterns: "PR #123", "Issue #456", "#789"
        - Full URLs: "https://github.com/owner/repo/pull/123"
        - Relative URLs: "/pull/123", "pull/123"

        This utility supports the "Inference Before Clarification" principle, enabling
        agents to extract discoverable context before prompting users.

    .PARAMETER InputText
        The text to parse for GitHub context (e.g., user prompt, message, URL).

    .PARAMETER Type
        Optional filter to only extract specific types: 'PR', 'Issue', or 'Any' (default).

    .OUTPUTS
        PSCustomObject with properties:
        - Type: 'PR' or 'Issue' or $null if not found
        - Number: The extracted number or $null
        - Owner: Repository owner or $null
        - Repo: Repository name or $null
        - Source: Extraction method used ('TextPattern', 'FullURL', 'RelativeURL', 'HashReference', 'None')

    .EXAMPLE
        Get-GitHubContextFromText -InputText "Review PR #806 comments"
        # Returns: @{ Type='PR'; Number=806; Owner=$null; Repo=$null; Source='TextPattern' }

    .EXAMPLE
        Get-GitHubContextFromText -InputText "https://github.com/rjmurillo/ai-agents/pull/806"
        # Returns: @{ Type='PR'; Number=806; Owner='rjmurillo'; Repo='ai-agents'; Source='FullURL' }

    .EXAMPLE
        Get-GitHubContextFromText -InputText "Check issue #123" -Type Issue
        # Returns: @{ Type='Issue'; Number=123; Owner=$null; Repo=$null; Source='TextPattern' }

    .NOTES
        Security: Uses validated regex patterns to prevent injection attacks.
        Follows Skill-PowerShell-002: Always returns object, never $null.
    #>

    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param(
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [AllowEmptyString()]
        [string]$InputText,

        [Parameter(Mandatory = $false)]
        [ValidateSet('PR', 'Issue', 'Any')]
        [string]$Type = 'Any'
    )

    begin {
        # Import GitHubCore for validation functions
        $ModulePath = Join-Path -Path $PSScriptRoot -ChildPath ".." | Join-Path -ChildPath ".." | Join-Path -ChildPath "modules" | Join-Path -ChildPath "GitHubCore.psm1"
        Import-Module $ModulePath -Force
    }

    process {
        # Initialize result object (never return $null per Skill-PowerShell-002)
        $result = [PSCustomObject]@{
            Type = $null
            Number = $null
            Owner = $null
            Repo = $null
            Source = 'None'
        }

        if ([string]::IsNullOrWhiteSpace($InputText)) {
            return $result
        }

        # Priority 1: Full GitHub URL with owner/repo/type/number
        # Pattern: https://github.com/owner/repo/{pull|issues}/123
        $hasFullGitHubURL = $InputText -match 'github\.com/([^/\s]+)/([^/\s]+)/(pull|issues)/(\d+)'

        if ($hasFullGitHubURL) {
            $owner = $Matches[1]
            $repo = $Matches[2]
            $urlType = $Matches[3]
            $number = [int]$Matches[4]

            # Validate owner and repo names
            if ((Test-GitHubNameValid -Name $owner -Type Owner) -and
                (Test-GitHubNameValid -Name $repo -Type Repo)) {

                $extractedType = if ($urlType -eq 'pull') { 'PR' } else { 'Issue' }

                # Apply type filter if specified
                if ($Type -eq 'Any' -or $Type -eq $extractedType) {
                    $result.Type = $extractedType
                    $result.Number = $number
                    $result.Owner = $owner
                    $result.Repo = $repo
                    $result.Source = 'FullURL'
                    return $result
                }
            }
            # If full URL exists but validation fails, return empty (don't try other patterns)
            return $result
        }

        # Priority 2: Relative URL pattern (only if no full GitHub URL present)
        # Pattern: /pull/123 or pull/123 or /issues/456 or issues/456
        if ($InputText -match '\b(pull|issues)/(\d+)\b') {
            $urlType = if ($Matches[1] -eq 'pull') { 'PR' } else { 'Issue' }
            $number = [int]$Matches[2]

            # Apply type filter if specified
            if ($Type -eq 'Any' -or $Type -eq $urlType) {
                $result.Type = $urlType
                $result.Number = $number
                $result.Source = 'RelativeURL'
                return $result
            }
        }

        # Priority 3: Text patterns with explicit "PR" or "Issue" keywords
        # Patterns: "PR #123", "PR 123", "pull request #123", "Issue #456", "Issue 456"
        $hasExplicitKeyword = $false

        if ($InputText -match '\b(?:PR|pull\s+request)\s*#?(\d+)\b') {
            $hasExplicitKeyword = $true
            if ($Type -eq 'Any' -or $Type -eq 'PR') {
                $result.Type = 'PR'
                $result.Number = [int]$Matches[1]
                $result.Source = 'TextPattern'
                return $result
            }
        }

        if ($InputText -match '\bIssue\s*#?(\d+)\b') {
            $hasExplicitKeyword = $true
            if ($Type -eq 'Any' -or $Type -eq 'Issue') {
                $result.Type = 'Issue'
                $result.Number = [int]$Matches[1]
                $result.Source = 'TextPattern'
                return $result
            }
        }

        # Priority 4: Hash reference (ambiguous - could be PR or Issue)
        # Pattern: #123 (only if no explicit keyword was found)
        if (-not $hasExplicitKeyword -and $InputText -match '\B#(\d+)\b') {
            if ($Type -eq 'Any') {
                # Default to PR for ambiguous hash references
                $result.Type = 'PR'
                $result.Number = [int]$Matches[1]
                $result.Source = 'HashReference'
                return $result
            }
            elseif ($Type -eq 'PR' -or $Type -eq 'Issue') {
                $result.Type = $Type
                $result.Number = [int]$Matches[1]
                $result.Source = 'HashReference'
                return $result
            }
        }

        # No matches found - return empty result
        return $result
    }
}

