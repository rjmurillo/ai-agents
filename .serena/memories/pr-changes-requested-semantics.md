# CHANGES_REQUESTED Semantics for Bot-Authored PRs

## Critical Understanding

rjmurillo-bot takes action based on **activation triggers**, not just PR authorship.

## Prerequisites

Before any work, rjmurillo-bot MUST:
1. Read `.agents/AGENTS.md`
2. Follow `.agents/SESSION-PROTOCOL.md`

## rjmurillo-bot Activation Triggers

| Trigger | Action |
|---------|--------|
| **PR Author** | rjmurillo-bot authored PR → ActionRequired → /pr-review all comments |
| **Reviewer** | rjmurillo-bot added as reviewer → ActionRequired → /pr-review all comments |
| **Mention** | @rjmurillo-bot in comment → Process ONLY that comment |

## Blocked List

A PR is added to Blocked ONLY when:
- Human authored the PR, AND
- No action is directed toward @rjmurillo-bot (explicitly or implicitly)

## Bot Categories

| Category | Examples | When rjmurillo-bot Acts |
|----------|----------|------------------------|
| **agent-controlled** | rjmurillo-bot | Author or reviewer of PR |
| **mention-triggered** | copilot-swe-agent | Supplements agent-controlled via @copilot |
| **command-triggered** | dependabot[bot] | Uses @dependabot commands |
| **non-responsive** | github-actions[bot] | Cannot respond to mentions |
| **human** | rjmurillo | Only if @rjmurillo-bot mentioned |

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

## Maintenance Tasks

Maintenance is limited to **merge conflict resolution only**.

### Resolving Merge Conflicts

Before resolving, gather context:
```bash
git log --oneline -10 origin/main  # Last 10 commits for context
```

Additional context from open Issues/PRs as needed. PR numbers appear in git log.

## Eyes Reaction (Comment Acknowledgment)

Eyes reaction = social indicator of engagement. Use ONLY when taking action:

| Scenario | Add Eyes? |
|----------|-----------|
| rjmurillo-bot is PR author | Yes |
| rjmurillo-bot is reviewer | Yes |
| @rjmurillo-bot mentioned | Yes (on that comment) |
| Human PR, no mention | No |

## Anti-Patterns

```powershell
# WRONG: Skip all processing
if ($pr.reviewDecision -eq 'CHANGES_REQUESTED') { continue }

# WRONG: Treat all bots the same
if ($isBotAuthor) { Invoke-PRCommentResponder }  # copilot needs @mention!
```

## Documentation

**Full protocol documentation with state diagrams**: `.agents/architecture/bot-author-feedback-protocol.md`

## Related

- `pr-comment-responder` skill agent
- `pr-review-acknowledgment` for eyes reaction protocol
- `scripts/Invoke-PRMaintenance.ps1` for full logic