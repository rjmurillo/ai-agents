---
type: design
id: DESIGN-001
title: PR Comment Processing Architecture
status: implemented
priority: P0
related:
  - REQ-001
  - REQ-002
  - TASK-001
  - TASK-002
  - TASK-003
adr: null
created: 2025-12-30
updated: 2025-12-30
author: spec-generator
tags:
  - pr-review
  - architecture
  - github-skill
---

# DESIGN-001: PR Comment Processing Architecture

## Requirements Addressed

- REQ-001: PR Comment Acknowledgment and Resolution
- REQ-002: PR Comment Triage by Actionability

## Design Overview

The pr-comment-responder agent acts as a thin coordination layer that retrieves PR context, triages comments by signal quality, and delegates to the orchestrator for analysis and implementation. It does not contain custom routing logic; instead, it passes classified context to the orchestrator which determines the workflow path (Quick Fix, Standard, or Strategic).

## Component Architecture

### Component 1: Context Gatherer

**Purpose**: Retrieve complete PR context efficiently using GitHub skill

**Responsibilities**:

- Invoke Get-PRContext.ps1 for PR metadata
- Invoke Get-PRReviewComments.ps1 -IncludeIssueComments for all comments
- Invoke Get-PRReviewers.ps1 for reviewer list
- Parse and normalize comment data

**Interfaces**:

```powershell
# Input: PR number
# Output: Structured PR context object

$context = Get-PRContext -PullRequest $prNumber
$comments = Get-PRReviewComments -PullRequest $prNumber -IncludeIssueComments
$reviewers = Get-PRReviewers -PullRequest $prNumber
```

### Component 2: Signal Analyzer

**Purpose**: Retrieve and apply reviewer signal quality from memory

**Responsibilities**:

- Read pr-comment-responder-skills memory
- Map reviewers to signal quality tiers (High >80%, Medium 30-80%, Low <30%)
- Assign priority: P0 (cursor[bot]), P1 (humans), P2 (other bots)
- Identify security-domain comments for priority override

**Interfaces**:

```text
Input: List of comments with reviewer attribution
Output: Comments sorted by priority with signal metadata
```

### Component 3: Comment Classifier

**Purpose**: Classify each comment into workflow path

**Responsibilities**:

- Determine classification: Quick Fix, Standard, or Strategic
- Apply triage heuristics:
  - Bug reports, type errors: Quick Fix (~90% actionable)
  - Missing coverage, investigation needed: Standard (~70% actionable)
  - Scope questions, architecture concerns: Strategic
  - Summaries, duplicates: Skip (0% actionable)

**Interfaces**:

```text
Input: Comment content and metadata
Output: Classification label and rationale
```

### Component 4: Orchestrator Delegate

**Purpose**: Hand off classified comments to orchestrator

**Responsibilities**:

- Package context for orchestrator consumption
- Delegate analysis and implementation
- Receive orchestrator output
- Track resolution status

**Interfaces**:

```text
Task(subagent_type="orchestrator", prompt="Process PR comment: [context]")
```

### Component 5: Resolution Tracker

**Purpose**: Track and report comment resolution status

**Responsibilities**:

- Maintain status for each comment: [DONE], [WIP], [WONTFIX], [DUPLICATE]
- Update session log with resolution summary
- Post acknowledgment/reply if required

**Interfaces**:

```powershell
# Post reply to comment thread
Post-PRCommentReply -PullRequest $prNumber -Body "..." -InReplyTo $commentId

# Add reaction for acknowledgment
Add-CommentReaction -PullRequest $prNumber -CommentId $commentId -Reaction "+1"
```

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| GitHub operations | PowerShell scripts in .claude/skills/github/ | Tested, validated, follows ADR-005 |
| Memory system | Serena + cloudmcp-manager | Cross-session context persistence |
| Delegation | Task tool to orchestrator | Orchestrator owns routing logic |

## Security Considerations

- Security-domain comments take priority over all others
- No hardcoded tokens; use gh CLI authenticated session
- Input validation on PR numbers and comment IDs

## Testing Strategy

- Unit tests for classification logic (Pester)
- Integration tests with mock PR data
- Signal quality tracking validation

## Open Questions

None currently. Design validated through implementation.

## Traceability

```text
REQ-001 ─┬→ DESIGN-001 → TASK-001 (Context gathering scripts)
REQ-002 ─┘             → TASK-002 (Signal analysis)
                       → TASK-003 (Classification logic)
```
