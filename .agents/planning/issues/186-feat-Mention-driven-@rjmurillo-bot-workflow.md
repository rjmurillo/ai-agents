---
number: 186
title: "feat: Mention-driven @rjmurillo-bot workflow"
state: OPEN
created_at: 12/20/2025 11:21:47
author: rjmurillo-bot
labels: ["enhancement", "github-actions"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/186
---

# feat: Mention-driven @rjmurillo-bot workflow

# Summary

A unified GitHub Actions workflow that enables @rjmurillo-bot to respond to mentions across Issues, PRs, and review comments.

## Event Coverage

| Event Source | GitHub Event | Trigger |
|-------------|--------------|---------|
| Issue/PR conversation comment | `issue_comment` | `created` |
| PR review comment (inline diff) | `pull_request_review_comment` | `created` |
| Review requested | `pull_request_target` | `review_requested` |
| PR changed (new commits) | `pull_request_target` | `synchronize` |
| PR title/body edited | `pull_request_target` | `edited`, `opened` |

## Security Model

- Use `pull_request_target` for PR events (write perms for fork PRs)
- Do NOT checkout PR code in workflow
- Pull context via GitHub API: PR title/body, changed files, diff, comments
- Add guard: if PR is from fork and commenter is not trusted, run in "read-only" mode

## Process Flow

```text
GitHub event
  |
  v
Does payload contain "@rjmurillo-bot"?
  | yes                          | no
  v                              v
Build prompt from context      If action is review_requested/synchronize
(PR metadata, diff, comment)     optionally run auto-review behavior
  |
  v
Run Claude Code / Copilot CLI
  |
  v
Post response comment to same thread
```

## Implementation Sketch

Workflow file: `.github/workflows/rjmurillo-bot.yml`

Key components:

1. **Gate step**: Detect @rjmurillo-bot mention in comment body
2. **Context builder**: Build JSON with issue/PR metadata, diff, comment
3. **Agent runner**: Invoke existing Copilot CLI or Claude Code with prompt
4. **Reply poster**: Post response back to same issue/PR thread

```yaml
on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  pull_request_target:
    types: [opened, edited, synchronize, review_requested]

permissions:
  contents: read
  issues: write
  pull-requests: write
```

## Design Decisions Needed

1. **Fork PRs**: Should bot respond on forked PRs?
   - If yes: keep `pull_request_target`, no PR code checkout
   - If no: add gate `if (pr.head.repo.fork) return false`

2. **Noise control**: Respond multiple times in same thread?
   - Suggestion: Only respond when explicitly mentioned, ignore edits unless re-mentioned

3. **Auth**: Which agent backend?
   - Copilot CLI: Needs GitHub auth context
   - Claude API: Needs `ANTHROPIC_API_KEY` secret

## Acceptance Criteria

- [ ] Workflow triggers on issue comment with @rjmurillo-bot mention
- [ ] Workflow triggers on PR conversation comment with mention
- [ ] Workflow triggers on inline review comment with mention
- [ ] Workflow triggers on PR synchronize/review_requested (optional mention gate)
- [ ] Response posted back to same thread
- [ ] Context includes: event type, sender, comment body, PR metadata, diff
- [ ] Safe for fork PRs (no code checkout)
- [ ] Concurrency group prevents duplicate runs

## Related

- Issue #147: AI Issue Triage Workflow
- Existing workflows in `.github/workflows/`


