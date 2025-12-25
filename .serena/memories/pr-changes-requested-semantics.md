# CHANGES_REQUESTED Semantics for Bot-Authored PRs

## Critical Understanding

**CHANGES_REQUESTED handling depends on both author type AND bot category.**

When a reviewer requests changes on a PR, the action depends on:
1. **Who authored the PR** (human vs bot)
2. **What type of bot** (if bot-authored)

## Bot Categories

| Category | Examples | How to Address Feedback |
|----------|----------|------------------------|
| **human** | rjmurillo, johndoe | Blocked - human must act |
| **agent-controlled** | rjmurillo-bot, my-project-bot | `/pr-review` via pr-comment-responder |
| **mention-triggered** | copilot-swe-agent, copilot[bot] | Add comment with `@copilot` |
| **command-triggered** | dependabot[bot], renovate[bot] | Use `@dependabot rebase`, etc. |
| **unknown-bot** | other [bot] accounts | Manual review required |

## The Mistake to Avoid

```powershell
# WRONG: Treating all CHANGES_REQUESTED as blocked
if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') {
    Write-Log "Blocked - needs human"
    continue  # SKIP - WRONG for bot PRs!
}

# ALSO WRONG: Treating all bot PRs the same
if ($isBotAuthor) {
    # Invoke pr-comment-responder for all bots
    # WRONG: copilot-swe-agent needs @copilot mention instead!
}
```

## Correct Logic

```powershell
# RIGHT: Use Get-BotAuthorInfo for nuanced handling
if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') {
    $botInfo = Get-BotAuthorInfo -AuthorLogin $pr.author.login

    if (-not $botInfo.IsBot) {
        # Human authored → truly blocked
        continue
    }

    # Bot authored → action depends on category
    switch ($botInfo.Category) {
        'agent-controlled' {
            # We can address directly via pr-comment-responder
            # Add to ActionRequired list
        }
        'mention-triggered' {
            # Needs @mention in comment (e.g., @copilot)
            # Add to ActionRequired with Mention guidance
        }
        'command-triggered' {
            # Needs specific command (e.g., @dependabot rebase)
            # Add to ActionRequired with command guidance
        }
    }
}
```

## Real Examples

| PR | Author | Category | Action |
|----|--------|----------|--------|
| #247 | copilot-swe-agent | mention-triggered | `@copilot` in comment |
| #246 | rjmurillo-bot | agent-controlled | `/pr-review 246` |
| #235 | rjmurillo-bot | agent-controlled | `/pr-review 235` |

## Why This Matters

Different bots have different trigger mechanisms:

- **copilot-swe-agent**: Will NOT act on CHANGES_REQUESTED unless explicitly 
  mentioned with `@copilot` in a comment
- **dependabot[bot]**: Responds to specific commands like `@dependabot rebase`
- **rjmurillo-bot**: The identity this agent runs as - can address directly

## Implementation

See `Get-BotAuthorInfo` in `scripts/Invoke-PRMaintenance.ps1` for the full
categorization logic.

## Evidence

Session: 2025-12-24 - User clarification on nuanced bot handling:

> "For PRs authored by copilot-swe-agent, if changes are requested, the agent 
> will not process the changes unless explicitly mentioned in the review 
> comments with @copilot to trigger action."

## Maintenance Tasks Always Run

**CRITICAL**: CHANGES_REQUESTED status only affects who can ADDRESS reviewer feedback.

Maintenance tasks run for ALL PRs regardless of:
- CHANGES_REQUESTED status
- Author type (human or bot)

| Task | Runs? | Why |
|------|-------|-----|
| Resolve merge conflicts | Always | Keeps PR mergeable |
| Acknowledge bot comments | Always | Shows engagement |
| Check similar PRs | Always | Informational |
| Address reviewer feedback | Depends | Bot category determines action |

The Blocked/ActionRequired lists are for REPORTING purposes, not for skipping work.

## Related

- `Get-BotAuthorInfo` function for bot categorization
- `pr-comment-responder` skill for agent-controlled PRs
- `scripts/Invoke-PRMaintenance.ps1` for PR processing logic