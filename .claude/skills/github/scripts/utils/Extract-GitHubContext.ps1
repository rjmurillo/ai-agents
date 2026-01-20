<#
.SYNOPSIS
    Extracts GitHub context (PR numbers, issue numbers, owner, repo) from text and URLs.

.DESCRIPTION
    Parses user prompts to extract GitHub context without requiring explicit parameters.
    Supports:
    - Text patterns: "PR 806", "#806", "pull request 123", "issue #45"
    - GitHub URLs: github.com/owner/repo/pull/123, github.com/owner/repo/issues/456

    Designed for autonomous agent execution where context should be inferred,
    not prompted for.

.PARAMETER Text
    The text to parse for GitHub context (e.g., user prompt).

.PARAMETER RequirePR
    If specified, throws an error when no PR number can be extracted.
    Use for autonomous execution where missing context should fail fast.

.PARAMETER RequireIssue
    If specified, throws an error when no issue number can be extracted.

.OUTPUTS
    PSCustomObject with extracted context:
    - PRNumbers: Array of PR numbers found
    - IssueNumbers: Array of issue numbers found
    - Owner: Repository owner (from URL, if found)
    - Repo: Repository name (from URL, if found)
    - URLs: Array of parsed URL objects

.EXAMPLE
    $ctx = .\Extract-GitHubContext.ps1 -Text "Review PR 806 comments"
    $ctx.PRNumbers  # @(806)

.EXAMPLE
    $ctx = .\Extract-GitHubContext.ps1 -Text "Check https://github.com/owner/repo/pull/123"
    $ctx.PRNumbers  # @(123)
    $ctx.Owner      # "owner"
    $ctx.Repo       # "repo"

.EXAMPLE
    # Fail-fast mode for autonomous execution
    .\Extract-GitHubContext.ps1 -Text "Review the comments" -RequirePR
    # Throws: "Cannot extract PR number from prompt. Provide explicit PR number or URL."

.NOTES
    Part of Phase 1 solution for Issue #829: Context Inference Gap.

    Exit Codes:
    - 0: Success
    - 1: Required context not found (when -RequirePR or -RequireIssue specified)

    Extraction Priority:
    1. GitHub URLs (most specific, includes owner/repo)
    2. "PR #N" / "pull request N" patterns
    3. "#N" patterns (ambiguous, could be PR or issue)
    4. "issue #N" patterns
#>

[CmdletBinding()]
[OutputType([PSCustomObject])]
param(
    [Parameter(Mandatory, ValueFromPipeline)]
    [string]$Text,

    [Parameter()]
    [switch]$RequirePR,

    [Parameter()]
    [switch]$RequireIssue
)

process {
    # Initialize result object
    $result = [PSCustomObject]@{
        PRNumbers    = [System.Collections.Generic.List[int]]::new()
        IssueNumbers = [System.Collections.Generic.List[int]]::new()
        Owner        = $null
        Repo         = $null
        URLs         = [System.Collections.Generic.List[PSCustomObject]]::new()
        RawMatches   = [System.Collections.Generic.List[string]]::new()
    }

    #region URL Extraction

    # Pattern: github.com/owner/repo/pull/N or github.com/owner/repo/issues/N
    $urlPattern = 'github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?)/([a-zA-Z0-9._-]{1,100})/(pull|issues)/(\d+)'
    $urlMatches = [regex]::Matches($Text, $urlPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)

    foreach ($match in $urlMatches) {
        $owner = $match.Groups[1].Value
        $repo = $match.Groups[2].Value
        $type = $match.Groups[3].Value.ToLower()
        $number = [int]$match.Groups[4].Value

        # Store first owner/repo found (priority to URL-based context)
        if (-not $result.Owner) {
            $result.Owner = $owner
            $result.Repo = $repo
        }

        $urlObj = [PSCustomObject]@{
            Type   = if ($type -eq 'pull') { 'PR' } else { 'Issue' }
            Number = $number
            Owner  = $owner
            Repo   = $repo
            URL    = $match.Value
        }
        $result.URLs.Add($urlObj)
        $result.RawMatches.Add($match.Value)

        # Add to appropriate list
        if ($type -eq 'pull') {
            if ($number -notin $result.PRNumbers) {
                $result.PRNumbers.Add($number)
            }
        }
        else {
            if ($number -notin $result.IssueNumbers) {
                $result.IssueNumbers.Add($number)
            }
        }
    }

    #endregion

    #region Text Pattern Extraction

    # Pattern 1: "PR N", "PR #N", "PR#N" (case-insensitive)
    $prPattern = '\bPR\s*#?(\d+)\b'
    $prMatches = [regex]::Matches($Text, $prPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    foreach ($match in $prMatches) {
        $number = [int]$match.Groups[1].Value
        if ($number -notin $result.PRNumbers) {
            $result.PRNumbers.Add($number)
            $result.RawMatches.Add($match.Value)
        }
    }

    # Pattern 2: "pull request N", "pull request #N" (case-insensitive)
    $pullRequestPattern = '\bpull\s+request\s*#?(\d+)\b'
    $pullRequestMatches = [regex]::Matches($Text, $pullRequestPattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    foreach ($match in $pullRequestMatches) {
        $number = [int]$match.Groups[1].Value
        if ($number -notin $result.PRNumbers) {
            $result.PRNumbers.Add($number)
            $result.RawMatches.Add($match.Value)
        }
    }

    # Pattern 3: "issue N", "issue #N", "issues N" (case-insensitive, singular/plural)
    $issuePattern = '\bissues?\s*#?(\d+)\b'
    $issueMatches = [regex]::Matches($Text, $issuePattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    foreach ($match in $issueMatches) {
        $number = [int]$match.Groups[1].Value
        if ($number -notin $result.IssueNumbers) {
            $result.IssueNumbers.Add($number)
            $result.RawMatches.Add($match.Value)
        }
    }

    # Pattern 4: Standalone "#N" (ambiguous - only if no specific context)
    # Only extract if not already captured by URL or explicit patterns
    # Exclude matches that are part of larger patterns (e.g., inside URLs)
    $hashPattern = '(?<!\/)#(\d+)\b'
    $hashMatches = [regex]::Matches($Text, $hashPattern)
    foreach ($match in $hashMatches) {
        $number = [int]$match.Groups[1].Value
        $matchPos = $match.Index

        # Skip if this position is within a URL (already captured)
        $inUrl = $false
        foreach ($urlMatch in $urlMatches) {
            if ($matchPos -ge $urlMatch.Index -and $matchPos -lt ($urlMatch.Index + $urlMatch.Length)) {
                $inUrl = $true
                break
            }
        }

        if (-not $inUrl) {
            # Standalone # numbers are ambiguous, add to PRNumbers by default
            # (more common use case in PR review context)
            if ($number -notin $result.PRNumbers -and $number -notin $result.IssueNumbers) {
                $result.PRNumbers.Add($number)
                $result.RawMatches.Add($match.Value)
            }
        }
    }

    #endregion

    #region Validation for Autonomous Execution

    if ($RequirePR -and $result.PRNumbers.Count -eq 0) {
        $errorMsg = "Cannot extract PR number from prompt. Provide explicit PR number or URL."
        throw [System.Management.Automation.PSInvalidOperationException]::new($errorMsg)
    }

    if ($RequireIssue -and $result.IssueNumbers.Count -eq 0) {
        $errorMsg = "Cannot extract issue number from prompt. Provide explicit issue number or URL."
        throw [System.Management.Automation.PSInvalidOperationException]::new($errorMsg)
    }

    #endregion

    # Convert lists to arrays for output
    $result.PRNumbers = @($result.PRNumbers)
    $result.IssueNumbers = @($result.IssueNumbers)
    $result.URLs = @($result.URLs)
    $result.RawMatches = @($result.RawMatches)

    Write-Output $result
}
