---
name: pr-comment-responder
version: 1.0.0
description: PR review coordinator who gathers comment context, acknowledges every
  piece of feedback, and ensures all reviewer comments are addressed systematically.
  Triages by actionability, tracks thread conversations, and maps each comment to
  resolution status. Use when handling PR feedback, review threads, or bot comments.
license: MIT
model: claude-sonnet-4-5
metadata:
  argument-hint: Specify the PR number or review comments to address
---
# PR Comment Responder

Coordinates PR review responses through context gathering, comment tracking, and orchestrator delegation.

## Triggers

| Phrase | Action |
|--------|--------|
| `respond to PR comments` | Full workflow |
| `address review feedback on PR #123` | Full workflow |
| `handle PR review comments` | Full workflow |
| `fix PR review issues` | Full workflow |
| `reply to reviewer on PR #123` | Target specific PR |

## Quick Reference

### Context Inference (Phase -1)

**ALWAYS extract PR context from prompt first. Never prompt for information already provided.**

```powershell
# Extract PR number and owner/repo from user prompt
$context = pwsh .claude/skills/github/scripts/utils/Extract-GitHubContext.ps1 -Text "[prompt]" -RequirePR
```

Supported patterns:

- Text: `PR 806`, `PR #806`, `pull request 123`, `#806`
- URLs: `github.com/owner/repo/pull/123`

See [references/workflow.md](references/workflow.md) Phase -1 for full details.

### Tools

| Operation | Script |
|-----------|--------|
| **Context extraction** | `Extract-GitHubContext.ps1` |
| PR metadata | `Get-PRContext.ps1` |
| Comments | `Get-PRReviewComments.ps1 -IncludeIssueComments` |
| Domain classification | `Get-PRReviewComments.ps1 -GroupByDomain` |
| Reviewers | `Get-PRReviewers.ps1` |
| Reply | `Post-PRCommentReply.ps1` |
| Reaction | `Add-CommentReaction.ps1` |
| Resolve thread | `Resolve-PRReviewThread.ps1` |

### Reviewer Priority

| Priority | Reviewer | Signal |
|----------|----------|--------|
| P0 | cursor[bot] | 100% actionable |
| P1 | Human reviewers | High |
| P2 | coderabbitai[bot] | ~50% |
| P2 | Copilot | ~44% |

### Domain-Based Priority

Comments are classified into domains for priority-based triage:

| Priority | Domain | Keywords | Use Case |
|----------|--------|----------|----------|
| P0 | Security | CWE-*, vulnerability, injection, XSS, SQL, CSRF, auth, secrets, credentials, TOCTOU, symlink, traversal | Process FIRST - security-critical issues |
| P1 | Bug | error, crash, exception, fail, null, undefined, race condition, deadlock, memory leak | Address functional issues |
| P2 | Style | formatting, naming, indentation, whitespace, convention, prefer, consider, suggest | Apply improvements when time permits |
| P3 | Summary | Bot-generated summaries (## Summary, ### Overview) | Informational only |

**Domain-First Processing Workflow:**

```powershell
# Get comments grouped by domain
$comments = Get-PRReviewComments.ps1 -PullRequest 908 -GroupByDomain -IncludeIssueComments

# Process security FIRST (CWE, vulnerabilities, injection)
foreach ($comment in $comments.Security) {
    # Handle security-critical issues immediately
    # Route to security agent if needed
}

# Then bugs (errors, crashes, null references)
foreach ($comment in $comments.Bug) {
    # Address functional issues
}

# Then style (formatting, naming, conventions)
foreach ($comment in $comments.Style) {
    # Apply style improvements
}

# Finally general comments (everything else)
foreach ($comment in $comments.General) {
    # Process general feedback
}

# Skip summary comments (bot-generated noise)
# $comments.Summary contains informational summaries only
```

**Benefits:**

- Security issues processed before style suggestions
- Reduces noise from bot-generated summaries
- Enables metrics tracking (security vs style comment distribution)

## When to Use

Use this skill when:

- A PR has unaddressed review comments from humans or bots
- You need to systematically triage and respond to all review feedback
- CI review bots (CodeRabbit, Copilot, cursor) left comments requiring action

Use direct `Post-PRCommentReply.ps1` instead when:

- Replying to a single known comment (no triage needed)
- You already know the exact response to post

## Process

### Phase 1: Context and Gather

1. Extract PR number from prompt (BLOCKING) using `Extract-GitHubContext.ps1`
2. Load `pr-comment-responder-skills` memory
3. Gather PR metadata, reviewers, all comments (use `-GroupByDomain` for priority triage)
4. Batch eyes reactions on all comments

### Phase 2: Triage and Delegate

1. Generate comment map: `.agents/pr-comments/PR-[N]/comments.md`
2. Delegate each comment to orchestrator (process security domain first)
3. Implement changes via orchestrator delegation

### Phase 3: Verify

1. All comments resolved (COMPLETE or WONTFIX)
2. No new comments after 45s wait
3. CI checks passing, all threads resolved, commits pushed

See [references/workflow.md](references/workflow.md) for full phase details.

## Verification

- [ ] All comments resolved (COMPLETE or WONTFIX)
- [ ] No new comments after 45s wait
- [ ] CI checks passing
- [ ] All threads resolved
- [ ] Commits pushed

See [references/gates.md](references/gates.md) for gate implementation.

### Response Templates

See [references/templates.md](references/templates.md) for:

- Won't Fix responses
- Clarification requests
- Resolution replies

### Bot Handling

See [references/bots.md](references/bots.md) for:

- Copilot follow-up PR handling
- CodeRabbit commands
- cursor[bot] patterns

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Replying to bot summaries as actionable comments | Wastes time on informational noise | Skip Summary domain comments |
| Processing style before security | Misses critical issues | Process domains in P0-P3 priority order |
| Using raw `gh` commands | Bypasses tested skill scripts | Use `Post-PRCommentReply.ps1` and other skill scripts |
| Prompting user for PR number already in prompt | Redundant and frustrating | Use `Extract-GitHubContext.ps1` to parse from input |

## Extension Points

- Add new domain classifiers in `Get-PRReviewComments.ps1 -GroupByDomain`
- Add reviewer priority entries for new bot integrations
- Add response templates in `references/templates.md`
