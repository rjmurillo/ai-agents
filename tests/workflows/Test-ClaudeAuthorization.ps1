<#
.SYNOPSIS
    Tests whether a GitHub event is authorized to invoke Claude Code.

.DESCRIPTION
    Validates GitHub webhook events against authorization rules:
    - Checks for @claude mention in event body/title
    - Validates author association (MEMBER, OWNER, COLLABORATOR)
    - Allows specific bot accounts (dependabot, renovate, github-actions)

    Provides audit logging to GitHub Actions summary for security compliance.

    Per ADR-006, this script extracts complex conditional logic from workflow YAML
    to enable testing, debugging, and proper error handling.

.PARAMETER EventName
    GitHub event name (issue_comment, pull_request_review_comment, pull_request_review, issues)

.PARAMETER Actor
    GitHub actor triggering the event (e.g., username or bot name)

.PARAMETER AuthorAssociation
    Author's association with the repository (MEMBER, OWNER, COLLABORATOR, etc.)

.PARAMETER CommentBody
    Body text of a comment (for issue_comment and pull_request_review_comment events)

.PARAMETER ReviewBody
    Body text of a review (for pull_request_review events)

.PARAMETER IssueBody
    Body text of an issue (for issues events)

.PARAMETER IssueTitle
    Title of an issue (for issues events)

.OUTPUTS
    System.String
    Returns "true" if authorized, "false" if not authorized

.EXAMPLE
    Test-ClaudeAuthorization.ps1 -EventName "issue_comment" -Actor "octocat" -AuthorAssociation "MEMBER" -CommentBody "Hey @claude, can you help?"

    Returns "true" because MEMBER is authorized and @claude is mentioned

.EXAMPLE
    Test-ClaudeAuthorization.ps1 -EventName "issues" -Actor "external-user" -AuthorAssociation "CONTRIBUTOR" -IssueBody "Feature request"

    Returns "false" because no @claude mention

.NOTES
    This script logs all authorization attempts to GitHub Actions summary for audit trail.

    Exit Codes:
    - 0: Success (authorization result in stdout: "true" or "false")
    - 1: Script error (regex matching failure, audit log failure)
    - 2: Double fault (authorization check failed AND audit logging failed)

    Error Handling:
    - All errors are logged to stderr with context information
    - Empty bodies are allowed - they naturally deny authorization (no @claude mention)
    - Oversized bodies (>1MB) deny authorization, not script error
    - Regex matching errors are caught and logged
    - Audit logging failures cause script error (exit code 1)

    Audit Logging:
    - Writes to GITHUB_STEP_SUMMARY when available (blocking - required)
    - Includes timestamp, event details, decision, and reasoning
    - Error scenarios also logged to audit trail
    - Double fault scenario (authorization + logging failure) exits with code 2

    Security:
    - Validates input length to prevent regex DoS (1MB max)
    - Case-sensitive @claude matching with negative lookahead pattern
    - Oversized bodies logged and denied (fail-safe approach)
    - Bot allowlist synchronized with .github/workflows/claude.yml

    Diagnostics:
    - Authorization details logged to stdout for workflow visibility
    - Error details include event context for troubleshooting
    - Audit trail available in GitHub Actions summary tab
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('issue_comment', 'pull_request_review_comment', 'pull_request_review', 'issues')]
    [string]$EventName,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Actor,

    [Parameter()]
    [string]$AuthorAssociation = '',

    [Parameter()]
    [string]$CommentBody = '',

    [Parameter()]
    [string]$ReviewBody = '',

    [Parameter()]
    [string]$IssueBody = '',

    [Parameter()]
    [string]$IssueTitle = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    # Authorization configuration (single source of truth)
    $allowedAssociations = @('MEMBER', 'OWNER', 'COLLABORATOR')
    $allowedBots = @(
        # Dependency management bots
        'dependabot[bot]'
        'renovate[bot]'

        # GitHub automation
        'github-actions[bot]'

        # AI coding assistant bots (permitted to mention @claude)
        'copilot[bot]'
        'coderabbitai[bot]'
        'cursor[bot]'
        'gemini-ai[bot]'
        'claude-ai[bot]'
        'amazonq[bot]'
        'tabnine[bot]'
    )

    # Extract body content based on event type
    # Note: Empty bodies are allowed - they will naturally deny authorization (no @claude mention)
    $body = switch ($EventName) {
        'issue_comment' { $CommentBody }
        'pull_request_review_comment' { $CommentBody }
        'pull_request_review' { $ReviewBody }
        'issues' { "$IssueBody $IssueTitle" }
    }

    # Check for @claude mention (required for all events)
    # Uses case-sensitive negative lookahead to ensure @claude not followed by a word character
    # Prevents false positives like @claudette, @claude123, @claude_bot
    # Validate input length to prevent regex DoS
    $maxBodyLength = 1MB
    if ($body.Length -gt $maxBodyLength) {
        # Oversized bodies are treated as authorization denials, not script errors
        # This logs the suspicious payload and denies the request gracefully
        Write-Verbose "Authorization Denied: Event body exceeds maximum safe length ($maxBodyLength bytes, received $($body.Length) bytes)"
        Write-Verbose "This may indicate a malformed webhook or potential attack"

        # Log to audit trail (blocking - required for security compliance)
        if ($env:GITHUB_STEP_SUMMARY) {
            try {
                $oversizeLog = @"
## Authorization Denied: Event Body Too Large

**Maximum Allowed**: $maxBodyLength bytes (1 MB)
**Received**: $($body.Length) bytes
**Event Type**: $EventName
**Actor**: $Actor
**Timestamp**: $(Get-Date -Format 'o')

This may indicate a malformed webhook payload or a potential attack. Legitimate GitHub webhooks should not exceed 1MB.
"@
                Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $oversizeLog -ErrorAction Stop
            }
            catch {
                Write-Error "CRITICAL: Failed to write oversize body audit log to GitHub Actions summary: $_. Authorization cannot proceed without audit trail." -ErrorId 'AuditLogFailed'
                exit 1
            }
        }

        # Deny authorization (not a script error)
        Write-Output "false"
        exit 0
    }

    # Use case-sensitive match with negative lookahead to ensure word boundary
    # Pattern: @claude not followed by a word character (prevents @claudette, @claude123, @claude_bot, etc.)
    # Case-sensitive to prevent @Claude, @CLAUDE from triggering (security requirement)
    try {
        $hasMention = -not [string]::IsNullOrWhiteSpace($body) -and $body -cmatch '@claude(?!\w)'
    }
    catch {
        Write-Error "Failed to check for @claude mention: $_" -ErrorId 'RegexMatchFailed'
        exit 1
    }

    # Log authorization attempt for audit trail
    Write-Verbose "Authorization Check Details:"
    Write-Verbose "  Event: $EventName"
    Write-Verbose "  Actor: $Actor"
    Write-Verbose "  Author Association: $AuthorAssociation"
    Write-Verbose "  Has @claude Mention: $hasMention"

    # Determine authorization
    $isAuthorized = $false
    $authReason = ''

    if (-not $hasMention) {
        $authReason = "No @claude mention found in event body/title"
        Write-Verbose "Result: Not authorized - $authReason"
    }
    elseif ($allowedBots -contains $Actor) {
        $isAuthorized = $true
        $authReason = "Authorized via bot allowlist: $Actor"
        Write-Verbose "Result: Authorized - $authReason"
    }
    elseif ($allowedAssociations -contains $AuthorAssociation) {
        $isAuthorized = $true
        $authReason = "Authorized via author association: $AuthorAssociation"
        Write-Verbose "Result: Authorized - $authReason"
    }
    else {
        $authReason = "Access denied: Actor=$Actor is not in bot allowlist, Association=$AuthorAssociation is not in allowed list"
        Write-Verbose "Result: Not authorized - $authReason"
    }

    # Write audit log to GitHub Actions summary (if running in GitHub Actions)
    if ($env:GITHUB_STEP_SUMMARY) {
        try {
            $timestamp = Get-Date -Format 'o'
            $summary = @"
## Claude Authorization Check

| Property | Value |
|----------|-------|
| **Event Type** | $EventName |
| **Actor** | $Actor |
| **Author Association** | $AuthorAssociation |
| **Has @claude Mention** | $hasMention |
| **Authorized** | $isAuthorized |
| **Reason** | $authReason |
| **Timestamp** | $timestamp |

### Authorization Rules

**Allowed Author Associations**: $($allowedAssociations -join ', ')
**Allowed Bots**: $($allowedBots -join ', ')

### Security Note

GitHub may deprecate `author_association` from webhook payloads in the future.
This implementation will need to be updated when that deprecation takes effect.

"@
            Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $summary -ErrorAction Stop
        }
        catch {
            Write-Error "CRITICAL: Failed to write audit log to GitHub Actions summary: $_. Authorization cannot proceed without audit trail." -ErrorId 'AuditLogFailed'
            exit 1
        }
    }

    # Return result (true/false as lowercase string for GitHub Actions)
    Write-Output $isAuthorized.ToString().ToLower()
    exit 0
}
catch {
    $errorDetails = @{
        Message = $_.Exception.Message
        EventName = $EventName
        Actor = $Actor
        AuthorAssociation = $AuthorAssociation
        StackTrace = $_.ScriptStackTrace
    }

    Write-Error "Authorization check failed: $($errorDetails | ConvertTo-Json -Compress)" -ErrorId 'AuthorizationCheckFailed'
    Write-Verbose "Error Details: Event=$EventName, Actor=$Actor, Association=$AuthorAssociation"

    # Log error to summary if available
    if ($env:GITHUB_STEP_SUMMARY) {
        try {
            $errorSummary = @"
## Claude Authorization Check - ERROR

**Error**: $($_.Exception.Message)
**Event**: $EventName
**Actor**: $Actor
**Association**: $AuthorAssociation
**Timestamp**: $(Get-Date -Format 'o')

Authorization check failed. Review workflow logs for details.
"@
            Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $errorSummary -ErrorAction Stop
        }
        catch {
            Write-Error "DOUBLE FAULT: Authorization check failed AND audit logging failed: $_" -ErrorId 'AuditLogDoubleFault'
            Write-Error "Original error: $($_.Exception.Message)"
            # Defensive: Ensure we output denial and exit with distinct code for double faults
            Write-Output "false"
            exit 2
        }
    }

    exit 1
}
