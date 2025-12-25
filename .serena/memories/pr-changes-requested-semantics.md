# CHANGES_REQUESTED Semantics for Bot-Authored PRs

## Critical Understanding

**CHANGES_REQUESTED is NOT a "blocked" state for bot-authored PRs.**

When a reviewer requests changes on a PR:
- The **PR author** is expected to address the feedback
- For **human-authored PRs**: The human author must act → blocked for automation
- For **bot-authored PRs**: The bot/agent must address feedback → NOT blocked

## The Mistake to Avoid

```powershell
# WRONG: Treating all CHANGES_REQUESTED as blocked
if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') {
    Write-Log "Blocked - needs human"
    continue  # SKIP - WRONG for bot PRs!
}
```

## Correct Logic

```powershell
# RIGHT: Distinguish by author type
if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') {
    $isBot = $pr.author.login -match '\[bot\]$' -or 
             $pr.author.login -in @('copilot-swe-agent', 'github-actions')
    
    if ($isBot) {
        # Bot authored → agent should address feedback
        Write-Log "Bot PR needs to address reviewer feedback"
        # Continue processing, invoke pr-comment-responder
    } else {
        # Human authored → truly blocked
        Write-Log "Human PR blocked - needs author action"
        continue
    }
}
```

## Review Decision States

| State | Human-Authored PR | Bot-Authored PR |
|-------|-------------------|-----------------|
| `APPROVED` | Ready to merge | Ready to merge |
| `CHANGES_REQUESTED` | Blocked, needs human | **Agent should address** |
| `REVIEW_REQUIRED` | Awaiting review | Awaiting review |
| `null` | No reviews yet | No reviews yet |

## Why This Matters

PRs like #247, #246, #235 were incorrectly marked "blocked" when:
- They were authored by bots (copilot-swe-agent, rjmurillo-bot)
- Human reviewers (rjmurillo, gemini) requested changes
- The agent running PR maintenance IS the bot identity
- The agent SHOULD address the feedback, not skip it

## Identifying Bot Authors

Common bot author patterns:
- `*[bot]` suffix (e.g., `copilot[bot]`, `github-actions[bot]`)
- `copilot-swe-agent`
- `rjmurillo-bot`
- `dependabot[bot]`
- `renovate[bot]`

## Integration with PR Maintenance

When processing a bot-authored PR with CHANGES_REQUESTED:

1. Fetch review comments via `Get-PRReviewComments.ps1`
2. Invoke `pr-comment-responder` skill to address feedback
3. Push fixes and respond to reviewers
4. Re-request review if needed

## Evidence

Session: 2025-12-24 - User correction during PR #395 retrospective:

> "CHANGES_REQUESTED means a reviewer (rjmurillo) has requested changes from 
> the PR author (Copilot). These PRs are actually waiting for you to do 
> something and signal back to the reviewer, not for you to ignore."

## Related

- `pr-comment-responder` skill for handling review feedback
- `scripts/Invoke-PRMaintenance.ps1` for PR processing logic
- Issue #400 for visibility improvements
