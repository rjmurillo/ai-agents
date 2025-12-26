# Bot Author Feedback Protocol

## Overview

This document describes how the PR maintenance system handles CHANGES_REQUESTED feedback and when rjmurillo-bot takes action.

## Prerequisites

Before performing any work, rjmurillo-bot MUST:

1. Read `.agents/AGENTS.md`
2. Follow `.agents/SESSION-PROTOCOL.md`

## Decision Flow

```mermaid
flowchart TD
    A[PR with CHANGES_REQUESTED] --> B{Is rjmurillo-bot<br/>the PR author?}

    B -->|Yes| C[Add to ActionRequired]
    C --> D["/pr-review via pr-comment-responder"]

    B -->|No| E{Is rjmurillo-bot<br/>added as reviewer?}

    E -->|Yes| C

    E -->|No| F{Is @rjmurillo-bot<br/>mentioned in comments?}

    F -->|Yes| G[Process ONLY mentioned comments]
    G --> H[Add eyes reaction to those comments]
    H --> D

    F -->|No| I{Human-authored PR?}

    I -->|Yes| J[Add to Blocked list]
    J --> K[No actions available for bot]

    I -->|No| L[Other bot - manual review]

    D --> M[Maintenance Tasks]
    M --> N[Resolve merge conflicts only]
```

## rjmurillo-bot Activation Triggers

rjmurillo-bot takes action in these scenarios:

| Trigger | Condition | Action |
|---------|-----------|--------|
| **PR Author** | PR opened by rjmurillo-bot | Add to ActionRequired, run /pr-review |
| **Reviewer** | rjmurillo-bot added as reviewer | Add to ActionRequired, run /pr-review |
| **Mention** | @rjmurillo-bot in comment | Process ONLY that comment |

### Blocked List

A PR is added to the Blocked list ONLY when:

- Human authored the PR, AND
- No action is directed toward @rjmurillo-bot (explicitly or implicitly)

## Comment Acknowledgment (Eyes Reaction)

The eyes reaction is a social indicator of engagement. Use it ONLY when rjmurillo-bot will take action on the item.

**When to add eyes reaction:**

- rjmurillo-bot is the PR author
- rjmurillo-bot is assigned as reviewer
- @rjmurillo-bot is explicitly mentioned in the comment

**When NOT to add eyes reaction:**

- Human-authored PR with no mention of rjmurillo-bot
- Comments on PRs where bot has no action to take

## Maintenance Tasks

Maintenance tasks are limited to **merge conflict resolution only**.

### Resolving Merge Conflicts

Before resolving conflicts, gather context:

```bash
# Get last 10 commits into main for context
git log --oneline -10 origin/main

# Additional context from open Issues and PRs as needed
gh issue list --state open --limit 10
gh pr list --state open --limit 10
```

Note: PR numbers are included in the git log for reference (e.g., `abc1234 fix: something (#123)`).

## State Machine

```mermaid
stateDiagram-v2
    [*] --> CheckAuthor: PR with CHANGES_REQUESTED

    CheckAuthor --> BotIsAuthor: rjmurillo-bot authored PR
    CheckAuthor --> CheckReviewer: Not bot-authored

    BotIsAuthor --> ActionRequired: Add to ActionRequired
    ActionRequired --> ProcessAll: /pr-review all comments

    CheckReviewer --> BotIsReviewer: rjmurillo-bot is reviewer
    CheckReviewer --> CheckMention: Not a reviewer

    BotIsReviewer --> ActionRequired

    CheckMention --> MentionFound: @rjmurillo-bot mentioned
    CheckMention --> NoMention: No mention

    MentionFound --> ProcessMentioned: Process ONLY mentioned comments
    ProcessMentioned --> AckMentioned: Eyes reaction on those

    NoMention --> HumanPR: Human authored
    NoMention --> OtherBot: Other bot authored

    HumanPR --> Blocked: No bot action available
    OtherBot --> ManualReview: Requires manual review

    ProcessAll --> Maintenance
    AckMentioned --> Maintenance
    Maintenance --> ResolveConflicts: Only merge conflicts
    ResolveConflicts --> [*]
```

## Bot Categories

| Category | Examples | When rjmurillo-bot Acts |
|----------|----------|------------------------|
| **agent-controlled** | rjmurillo-bot | Author or reviewer of PR |
| **mention-triggered** | copilot-swe-agent | When @copilot mentioned (supplements agent-controlled) |
| **command-triggered** | dependabot[bot] | Uses @dependabot commands |
| **non-responsive** | github-actions[bot] | Cannot respond to mentions |
| **human** | rjmurillo | Only if @rjmurillo-bot mentioned |

## Anti-Patterns

```powershell
# WRONG: Add eyes to all comments
foreach ($comment in $allComments) { Add-Reaction -eyes }  # Only when taking action!

# WRONG: Process all comments when only mentioned
if ($mentionedOnce) { ProcessAllComments() }  # Only process where mentioned!

# WRONG: Include comment acknowledgment in maintenance
$maintenanceTasks = @('conflicts', 'comments')  # Only conflicts!

# WRONG: Skip session protocol
ProcessPR()  # Must read AGENTS.md and follow SESSION-PROTOCOL.md first!
```

## Related Documents

- `.agents/AGENTS.md` - Agent system instructions
- `.agents/SESSION-PROTOCOL.md` - Required session initialization
- Memory: `pr-changes-requested-semantics` - Quick reference
- Script: `scripts/Invoke-PRMaintenance.ps1` - Implementation
