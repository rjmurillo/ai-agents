<#
.SYNOPSIS
    Enforces ADR-007 Memory-First Architecture and pre-PR validation on user prompts.

.DESCRIPTION
    Claude Code hook that:
    1. Checks user prompts for planning/implementation keywords and injects memory-first reminder
    2. Detects PR creation requests and injects pre-PR validation checklist
    Receives JSON input via stdin containing the prompt text.
    Part of the ADR-007 enforcement mechanism (Issue #729).

.PARAMETER InputObject
    JSON input from stdin containing the prompt text.

.NOTES
    Hook Type: UserPromptSubmit
    Exit Codes:
        0 = Success, stdout added to Claude's context
        2 = Block prompt (not used here)

.LINK
    .agents/architecture/ADR-007-memory-first-architecture.md
    .agents/SESSION-PROTOCOL.md
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromPipeline = $true)]
    [string]$InputObject
)

begin {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'
    $AllInput = [System.Collections.ArrayList]::new()
}

process {
    if ($InputObject) {
        [void]$AllInput.Add($InputObject)
    }
}

end {
    # Join all pipeline input
    $InputJson = $AllInput -join "`n"

    # Extract prompt text from JSON
    $PromptText = ''
    try {
        $InputData = $InputJson | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($InputData.prompt) {
            $PromptText = $InputData.prompt
        }
    }
    catch {
        # If JSON parsing fails, use raw input
        $PromptText = $InputJson
    }

    # Keywords that suggest planning or implementation work
    $PlanningKeywords = @(
        'plan', 'implement', 'design', 'architect', 'build',
        'create', 'refactor', 'fix', 'add', 'update',
        'feature', 'issue', 'pr'
    )

    # Check if prompt contains any planning/implementation keywords
    $MatchFound = $false
    foreach ($Keyword in $PlanningKeywords) {
        if ($PromptText -match "(?i)\b$Keyword\b") {
            $MatchFound = $true
            break
        }
    }

    if ($MatchFound) {
        @"

**ADR-007 Memory Check**: Before proceeding with this task:

- Query ``memory-index`` for task-relevant memories
- Check Forgetful for cross-project patterns if applicable
- Evidence memory retrieval in session log

"@
    }

    # PR creation keywords that trigger pre-PR validation reminder
    $PrKeywords = @(
        'create pr', 'open pr', 'submit pr', 'make pr',
        'create pull request', 'open pull request',
        'gh pr create', 'push.*pr'
    )

    # Check if prompt suggests PR creation
    $PrMatchFound = $false
    foreach ($Pattern in $PrKeywords) {
        if ($PromptText -match "(?i)$Pattern") {
            $PrMatchFound = $true
            break
        }
    }

    if ($PrMatchFound) {
        @"

**Pre-PR Validation Gate**: Before creating a PR, complete these checks:

1. **Run local tests**: ``Invoke-Pester -Path 'tests/*.Tests.ps1'``
2. **Validate script syntax**: All .ps1 files must parse without errors
3. **Check memory naming**: No ``skill-`` prefix in ``.serena/memories/`` (ADR-017)
4. **Read validation memory**: ``mcp__serena__read_memory`` with ``memory_file_name="validation-pre-pr-checklist"``

⚠️ **Do NOT run markdownlint on .ps1 files** - it corrupts PowerShell comment terminators

"@
    }

    # GitHub CLI commands that should use skills instead
    $GhCliPatterns = @(
        # PR commands - use skills from .claude/skills/github/scripts/pr/
        'gh pr create',      # Use New-PR.ps1
        'gh pr list',        # Use Get-PullRequests.ps1
        'gh pr view',        # Use Get-PRContext.ps1
        'gh pr merge',       # Use Merge-PR.ps1
        'gh pr close',       # Use Close-PR.ps1
        'gh pr checks',      # Use Get-PRChecks.ps1
        'gh pr review',      # Use Add-PRReviewThreadReply.ps1
        'gh pr comment',     # Use Post-PRCommentReply.ps1
        'gh pr diff',        # Check for skill alternative
        'gh pr ready',       # Use Test-PRMergeReady.ps1
        'gh pr status',      # Use Get-PRContext.ps1
        # Issue commands - use skills from .claude/skills/github/scripts/issue/
        'gh issue create',   # Use New-Issue.ps1
        'gh issue list',     # Check for skill
        'gh issue view',     # Use Get-IssueContext.ps1
        'gh issue close',    # Check for skill
        'gh issue comment',  # Use Post-IssueComment.ps1
        'gh issue edit',     # Use Set-IssueLabels.ps1, Set-IssueMilestone.ps1, Set-IssueAssignee.ps1
        # API commands - often have skill equivalents
        'gh api',            # Check for skill-based alternative
        # Run commands - workflow triggers
        'gh run',            # Workflow management
        'gh workflow'        # Workflow management
    )

    # Check if prompt suggests GitHub CLI usage
    $GhCliMatchFound = $false
    $MatchedCommand = ''
    foreach ($Pattern in $GhCliPatterns) {
        if ($PromptText -match "(?i)$Pattern") {
            $GhCliMatchFound = $true
            $MatchedCommand = $Pattern
            break
        }
    }

    if ($GhCliMatchFound) {
        @"

**Skill Usage Check**: Detected potential ``$MatchedCommand`` usage.

Before using raw ``gh`` CLI, read the GitHub skills documentation:

``Read .claude/skills/github/SKILL.md``

**Available skill categories**:
- PR operations: New-PR, Merge-PR, Get-PRChecks, Get-PRContext, etc.
- Issue operations: New-Issue, Post-IssueComment, Set-IssueLabels, etc.
- Reactions: Add-CommentReaction

⚠️ Using skills ensures consistent error handling and audit logging.

"@
    }

    exit 0
}
