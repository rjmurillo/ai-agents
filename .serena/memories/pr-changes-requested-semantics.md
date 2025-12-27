# CHANGES_REQUESTED Semantics for Bot-Authored PRs

## Quick Reference

This memory provides a quick lookup for CHANGES_REQUESTED handling. For the complete protocol with mermaid state diagrams, see the canonical documentation.

**Canonical Documentation**: `.agents/architecture/bot-author-feedback-protocol.md`

## Prerequisites

Before any work, rjmurillo-bot MUST:

1. Read `.agents/AGENTS.md`
2. Follow `.agents/SESSION-PROTOCOL.md`

## rjmurillo-bot Activation Triggers

| Trigger | Action |
|---------|--------|
| **PR Author** | rjmurillo-bot authored PR -> ActionRequired -> /pr-review all comments |
| **Reviewer** | rjmurillo-bot added as reviewer -> ActionRequired -> /pr-review all comments |
| **Reviewer on Copilot PR** | rjmurillo-bot reviews copilot-swe-agent -> Synthesize bot feedback for @copilot |
| **Mention** | @rjmurillo-bot in comment -> Process ONLY that comment |

## Bot Categories

| Category | Examples | When rjmurillo-bot Acts |
|----------|----------|------------------------|
| **agent-controlled** | rjmurillo-bot | Author or reviewer of PR |
| **mention-triggered** | copilot-swe-agent | Supplements agent-controlled via @copilot |
| **command-triggered** | dependabot[bot] | Uses @dependabot commands |
| **non-responsive** | github-actions[bot] | Cannot respond to mentions - blocked |
| **unknown-bot** | other[bot] | Review manually |
| **human** | rjmurillo | Only if @rjmurillo-bot mentioned |

## Implementation

See `Get-BotAuthorInfo` in `scripts/Invoke-PRMaintenance.ps1`.

## Copilot Synthesis

When rjmurillo-bot is reviewer on a copilot-swe-agent PR:

1. Collect comments from other bots (coderabbitai, cursor[bot], gemini-code-assist)
2. Generate @copilot synthesis prompt with grouped feedback
3. Post comment directing @copilot to address issues
4. Add to ActionRequired with reason `COPILOT_SYNTHESIS_NEEDED`

**Authority Boundary**: Bot reviewer cannot modify mention-triggered PRs directly - must delegate via @copilot.

**Function**: `Invoke-CopilotSynthesis` in `scripts/Invoke-PRMaintenance.ps1`

## Derivative PRs

Derivative PRs are created by mention-triggered bots (e.g., copilot-swe-agent) targeting feature branches instead of main.

| Detection | Action |
|-----------|--------|
| `baseRefName != main/master` + mention-triggered author | Add to `DerivativePRs` collection |
| Parent PR found (matching `headRefName`) | Add parent to `ActionRequired` with `PENDING_DERIVATIVES` |

**Functions**: `Get-DerivativePRs`, `Get-PRsWithPendingDerivatives` in `scripts/Invoke-PRMaintenance.ps1`

**Risk**: Parent PR may merge before derivative is reviewed, orphaning the derivative.

## Related

- **Full Protocol**: `.agents/architecture/bot-author-feedback-protocol.md`
- `pr-comment-responder` skill agent
- `pr-review-acknowledgment` for eyes reaction protocol
- `copilot-follow-up-pr` for copilot derivative behavior
