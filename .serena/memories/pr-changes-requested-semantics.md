# CHANGES_REQUESTED Semantics for Bot-Authored PRs

## Critical Understanding

**CHANGES_REQUESTED handling depends on both author type AND bot category.**

When a reviewer requests changes:
1. **Who authored the PR** (human vs bot)
2. **What type of bot** (if bot-authored)

## Bot Categories

| Category | Examples | How to Address Feedback |
|----------|----------|------------------------|
| **human** | rjmurillo, johndoe | Blocked - human must act |
| **agent-controlled** | rjmurillo-bot, github-actions[bot] | `/pr-review` via pr-comment-responder |
| **mention-triggered** | copilot-swe-agent, copilot[bot] | Add comment with `@copilot` |
| **command-triggered** | dependabot[bot], renovate[bot] | Use `@dependabot rebase`, etc. |
| **unknown-bot** | other [bot] accounts | Manual review required |

## Bot-Specific Pattern References (DRY)

For detailed behavior patterns of each bot, see:

| Bot | Memory | Key Insight |
|-----|--------|-------------|
| cursor[bot] | `cursor-bot-review-patterns` | 100% actionable, trust immediately |
| Copilot | `copilot-pr-review` | 21% signal, high false positive rate |
| Copilot | `copilot-follow-up-pr` | Creates sub-PRs after replies |
| CodeRabbit | `coderabbit-config-strategy` | 66% noise, use path_instructions |
| dependabot | (standard GitHub docs) | `@dependabot rebase`, `@dependabot recreate` |
| renovate | (standard Renovate docs) | `@renovate rebase`, `@renovate recreate` |

## Implementation

See `Get-BotAuthorInfo` in `scripts/Invoke-PRMaintenance.ps1`:

```powershell
$botInfo = Get-BotAuthorInfo -AuthorLogin $pr.author.login
# Returns: IsBot, Category, Action, Mention
```

## Maintenance Tasks Always Run

CHANGES_REQUESTED status only affects who can ADDRESS feedback.

| Task | Runs? | Why |
|------|-------|-----|
| Resolve merge conflicts | Always | Keeps PR mergeable |
| Acknowledge bot comments | Always | Shows engagement |
| Check similar PRs | Always | Informational |
| Address reviewer feedback | Depends | Bot category determines action |

## Anti-Patterns

```powershell
# WRONG: Skip all processing
if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') { continue }

# WRONG: Treat all bots the same
if ($isBotAuthor) { Invoke-PRCommentResponder }  # copilot needs @mention!
```

## Related

- `pr-comment-responder` skill agent
- `pr-review-acknowledgment` for eyes reaction protocol
- `scripts/Invoke-PRMaintenance.ps1` for full logic