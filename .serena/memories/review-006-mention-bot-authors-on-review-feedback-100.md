# Review: Mention Bot Authors On Review Feedback 100

## Skill-Review-006: @mention Bot Authors on Review Feedback (100%)

**Statement**: When posting review comments on bot-authored PRs, always @mention the bot so it receives notification.

**Context**: PR review of bot-authored changes (copilot-swe-agent, dependabot, etc.).

**Trigger**: Posting review comments or change requests on bot PR.

**Pattern**:

1. Identify PR author (check if bot)
2. Include @mention in review comment or follow-up
3. **IMPORTANT**: For GitHub Copilot PRs (author shows as `copilot-swe-agent`): use `@copilot` NOT `@copilot-swe-agent`
4. For dependabot: `@dependabot`

**Evidence**: PR #147 - Initial change request posted without @mention; Copilot unaware of feedback until explicitly mentioned.

**Nuance**: The PR author displays as `copilot-swe-agent` but the correct @mention is `@copilot`. This is confusing but confirmed behavior.