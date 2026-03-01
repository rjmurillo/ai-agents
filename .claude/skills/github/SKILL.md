---
name: github
version: 3.1.0
model: claude-opus-4-5
description: Execute GitHub operations (PRs, issues, milestones, labels, comments, merges)
  using Python scripts with structured output and error handling. Use when working
  with pull requests, issues, review comments, CI checks, or milestones instead of raw gh.
license: MIT
metadata:
  domains:
    - github
    - pr
    - issue
    - labels
    - milestones
    - comments
    - reactions
  type: integration
  complexity: intermediate
  generator:
    keep_headings:
      - Decision Tree
      - Script Reference
      - Output Format
      - See Also
---
# GitHub Skill

Use these scripts instead of raw `gh` commands for consistent error handling and structured output.

---

## Triggers

| Phrase | Operation |
|--------|-----------|
| `create a PR` | new_pr.py |
| `respond to review comments on PR #123` | post_pr_comment_reply.py |
| `check CI status for PR #123` | get_pr_checks.py |
| `close issue #123` | Close-Issue operations |
| `add label to issue #123` | Set-IssueLabels.ps1 |

---

## Decision Tree

```text
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

Need GitHub data?
├─ PR info/diff → get_pr_context.py
├─ CI check status → get_pr_checks.py
├─ Review threads → get_pr_review_threads.py
├─ Unresolved threads → get_unresolved_review_threads.py
├─ Unaddressed bot comments → get_unaddressed_comments.py
├─ PR merged check → test_pr_merged.py
├─ List PRs (filtered) → get_pull_requests.py
├─ CI failure logs → get_pr_check_logs.py
├─ Review comments → get_pr_review_comments.py
├─ Unique reviewers → get_pr_reviewers.py
├─ Copilot follow-up PRs → detect_copilot_follow_up_pr.py
├─ Issue info → Get-IssueContext.ps1 (legacy)
├─ Merge readiness check → test_pr_merge_ready.py
├─ Latest milestone → Get-LatestSemanticMilestone.ps1 (legacy)
└─ Need to take action?
   ├─ Reply to review → post_pr_comment_reply.py
   ├─ Reply to thread (GraphQL) → add_pr_review_thread_reply.py
   ├─ Resolve threads → resolve_pr_review_thread.py
   ├─ Unresolve threads → unresolve_pr_review_thread.py
   ├─ Create PR → new_pr.py
   ├─ Create issue → New-Issue.ps1 (legacy)
   ├─ Comment on issue → Post-IssueComment.ps1 (legacy)
   ├─ Add reaction → Add-CommentReaction.ps1 (legacy)
   ├─ Apply labels → Set-IssueLabels.ps1 (legacy)
   ├─ Set issue milestone → Set-IssueMilestone.ps1 (legacy)
   ├─ Set PR/issue milestone (auto-detect) → Set-ItemMilestone.ps1 (legacy)
   ├─ Assign issue → Set-IssueAssignee.ps1 (legacy)
   ├─ Process AI triage → invoke_pr_comment_processing.py
   ├─ Assign Copilot → Invoke-CopilotAssignment.ps1 (legacy)
   ├─ Enable/disable auto-merge → set_pr_auto_merge.py
   ├─ Close PR → close_pr.py
   └─ Merge PR → merge_pr.py
```

---

## Script Reference

### PR Operations - Python (`scripts/pr/`)

Path resolution: `SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"`

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `get_pr_context.py` | PR metadata, diff, files | `--pull-request`, `--include-diff`, `--include-changed-files` |
| `get_pr_checks.py` | CI check status, polling | `--pull-request`, `--wait`, `--timeout-seconds`, `--required-only` |
| `get_pr_review_threads.py` | Thread-level review data | `--pull-request`, `--unresolved-only`, `--include-comments` |
| `get_unresolved_review_threads.py` | Unresolved thread IDs | `--pull-request` |
| `get_unaddressed_comments.py` | Bot comments needing attention | `--pull-request` |
| `test_pr_merged.py` | Check if PR is merged | `--pull-request` |
| `post_pr_comment_reply.py` | Thread-preserving replies | `--pull-request`, `--comment-id`, `--body` |
| `add_pr_review_thread_reply.py` | Reply to thread by ID (GraphQL) | `--thread-id`, `--body`, `--resolve` |
| `resolve_pr_review_thread.py` | Mark threads resolved | `--thread-id` or `--pull-request --all` |

### PR Operations - Additional Python (`scripts/pr/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `get_pull_requests.py` | List PRs with filters | `--state`, `--label`, `--author`, `--base`, `--head`, `--limit` |
| `get_pr_check_logs.py` | Fetch logs from failing CI checks | `--pull-request`, `--max-lines`, `--context-lines` |
| `get_pr_review_comments.py` | Review comments with domain classification | `--pull-request`, `--include-issue-comments`, `--only-unaddressed` |
| `get_pr_reviewers.py` | Enumerate unique reviewers | `--pull-request`, `--exclude-bots` |
| `detect_copilot_follow_up_pr.py` | Detect Copilot follow-up PRs | `--pr-number` |
| `test_pr_merge_ready.py` | Check merge readiness | `--pull-request`, `--ignore-ci`, `--ignore-threads` |
| `set_pr_auto_merge.py` | Enable/disable auto-merge | `--pull-request`, `--enable`/`--disable`, `--merge-method` |
| `new_pr.py` | Create PR with validation | `--title`, `--body`, `--base` |
| `close_pr.py` | Close PR with comment | `--pull-request`, `--comment` |
| `merge_pr.py` | Merge with strategy | `--pull-request`, `--strategy`, `--delete-branch`, `--auto` |
| `get_thread_by_id.py` | Get thread by GraphQL ID | `--thread-id` |
| `get_thread_conversation_history.py` | Full thread conversation | `--thread-id`, `--include-minimized` |
| `invoke_pr_comment_processing.py` | Process AI triage results | `--pr-number`, `--verdict`, `--findings-json` |
| `unresolve_pr_review_thread.py` | Unresolve review threads | `--thread-id` or `--pull-request --all` |

### Issue Operations (`scripts/issue/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-IssueContext.ps1` | Issue metadata | `-Issue` |
| `New-Issue.ps1` | Create new issue | `-Title`, `-Body`, `-Labels` |
| `Set-IssueLabels.ps1` | Apply labels (auto-create) | `-Issue`, `-Labels`, `-Priority` |
| `Set-IssueMilestone.ps1` | Assign milestone | `-Issue`, `-Milestone` |
| `Post-IssueComment.ps1` | Comments with idempotency | `-Issue`, `-Body`, `-Marker` |
| `Invoke-CopilotAssignment.ps1` | Synthesize context for Copilot | `-IssueNumber`, `-WhatIf` |
| `Set-IssueAssignee.ps1` | Assign users to issues | `-Issue`, `-Assignees` |

### Milestone Operations (`scripts/milestone/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Get-LatestSemanticMilestone.ps1` | Detect latest semantic version milestone | `-Owner`, `-Repo` |
| `Set-ItemMilestone.ps1` | Assign milestone to PR/issue (auto-detect) | `-ItemType`, `-ItemNumber`, `-MilestoneTitle` |

### Reactions (`scripts/reactions/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `Add-CommentReaction.ps1` | Add emoji reactions (batch support) | `-CommentId[]`, `-Reaction`, `-CommentType` |

---

## Output Format

All scripts output structured JSON with `Success` boolean:

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"
result=$(python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request 50)
echo "$result" | jq '.Success'
```

---

## Process

This skill provides scripts for GitHub operations. Use scripts directly or compose them into workflows.

**Basic Usage:**

1. Identify the operation needed using the Decision Tree
2. Find the corresponding script in the Script Reference
3. Call the script with required parameters
4. Parse the JSON output and check `Success` field

**Example Flow:**

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Get PR context
python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request 123

# Check CI status
python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request 123

# Post comment if needed
python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" --pull-request 123 --body "CI failures detected"
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Raw `gh pr view` commands | No structured output | Use `get_pr_context.py` |
| Raw `gh api` for comments | Doesn't preserve threading | Use `post_pr_comment_reply.py` |
| Replying to thread expecting auto-resolve | Replies DON'T auto-resolve threads | Use `resolve_pr_review_thread.py` after reply |
| Hardcoding owner/repo | Breaks in forks | Let scripts infer from `git remote` |
| Ignoring exit codes | Missing error handling | Check `$?` exit code |
| CWD-relative script paths | Breaks in plugin contexts | Use `$CLAUDE_PLUGIN_ROOT` for path resolution |

---

## See Also

| Document | Content |
|----------|---------|
| [examples.md](references/examples.md) | Complete script examples |
| [patterns.md](references/patterns.md) | Reusable workflow patterns |
| [copilot-prompts.md](references/copilot-prompts.md) | Creating @copilot directives |
| [copilot-synthesis-guide.md](references/copilot-synthesis-guide.md) | Copilot context synthesis |
| [api-reference.md](references/api-reference.md) | Exit codes, API endpoints, troubleshooting |
| `lib/github_core/` | Shared Python library (api.py, validation.py) |

---

## Verification

Before completing a GitHub operation:

- [ ] Correct script selected from Decision Tree
- [ ] Required parameters provided (PR/issue number)
- [ ] Response JSON parsed successfully
- [ ] `Success: true` in response
- [ ] State change verified (for mutating operations)
