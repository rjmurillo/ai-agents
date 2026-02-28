---
name: github
version: 4.0.0
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
| `respond to review comments` | post_pr_comment_reply.py |
| `check CI status` | get_pr_checks.py / get_pr_check_logs.py |
| `close issue` | close_pr.py / set_issue_labels.py |
| `add label to issue` | set_issue_labels.py |
| `list actionable items` | get_actionable_items.py |
| `check notifications` | get_actionable_items.py |

---

## Decision Tree

```text
Need GitHub data?
├─ List PRs (filtered) → get_pull_requests.py
├─ PR info/diff → get_pr_context.py
├─ CI check status → get_pr_checks.py
├─ CI failure logs → get_pr_check_logs.py
├─ Review comments → get_pr_review_comments.py
├─ Review threads → get_pr_review_threads.py
├─ Unique reviewers → get_pr_reviewers.py
├─ Unaddressed bot comments → get_unaddressed_comments.py
├─ PR merged check → test_pr_merged.py
├─ Copilot follow-up PRs → detect_copilot_followup_pr.py
├─ Issue info → get_issue_context.py
├─ Merge readiness check → test_pr_merge_ready.py
├─ Latest milestone → get_latest_semantic_milestone.py
├─ Actionable backlog → get_actionable_items.py
└─ Need to take action?
   ├─ Create issue → new_issue.py
   ├─ Create PR → new_pr.py
   ├─ Reply to review → post_pr_comment_reply.py
   ├─ Reply to thread (GraphQL) → add_pr_review_thread_reply.py
   ├─ Comment on issue → post_issue_comment.py
   ├─ Add reaction → add_comment_reaction.py
   ├─ Apply labels → set_issue_labels.py
   ├─ Set issue milestone → set_issue_milestone.py
   ├─ Set PR/issue milestone (auto-detect) → set_item_milestone.py
   ├─ Assign issue → set_issue_assignee.py
   ├─ Resolve threads → resolve_pr_review_thread.py
   ├─ Unresolve threads → unresolve_pr_review_thread.py
   ├─ Process AI triage → invoke_pr_comment_processing.py
   ├─ Assign Copilot → invoke_copilot_assignment.py
   ├─ Enable/disable auto-merge → set_pr_auto_merge.py
   ├─ Close PR → close_pr.py
   └─ Merge PR → merge_pr.py
```

---

## Scripts

### PR Operations (`scripts/pr/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `get_pull_requests.py` | List PRs with filters | `--state`, `--label`, `--author`, `--base`, `--head`, `--search`, `--limit` |
| `get_pr_context.py` | PR metadata, diff, files | `--pull-request`, `--include-changed-files`, `--include-diff` |
| `get_pr_checks.py` | CI check status, polling | `--pull-request`, `--wait`, `--timeout-seconds`, `--required-only`, `--output-format {json,text}` |
| `get_pr_check_logs.py` | Fetch logs from failing CI checks | `--pull-request`, `--max-lines`, `--context-lines` |
| `get_pr_review_comments.py` | Paginated review comments with stale detection | `--pull-request`, `--include-issue-comments`, `--detect-stale`, `--exclude-stale`, `--only-stale` |
| `get_pr_review_threads.py` | Thread-level review data | `--pull-request`, `--unresolved-only` |
| `get_pr_reviewers.py` | Enumerate unique reviewers | `--pull-request`, `--exclude-bots` |
| `get_unaddressed_comments.py` | Bot comments needing attention | `--pull-request` |
| `get_unresolved_review_threads.py` | Unresolved thread IDs | `--pull-request` |
| `test_pr_merged.py` | Check if PR is merged | `--pull-request` |
| `detect_copilot_followup_pr.py` | Detect Copilot follow-up PRs | `--pr-number`, `--owner`, `--repo` |
| `post_pr_comment_reply.py` | Thread-preserving replies | `--pull-request`, `--comment-id`, `--body` |
| `add_pr_review_thread_reply.py` | Reply to thread by ID (GraphQL) | `--thread-id`, `--body`, `--resolve` |
| `resolve_pr_review_thread.py` | Mark threads resolved | `--thread-id` or `--pull-request --all` |
| `unresolve_pr_review_thread.py` | Mark threads unresolved | `--thread-id` or `--pull-request --all` |
| `get_thread_by_id.py` | Get single thread by ID | `--thread-id` |
| `get_thread_conversation_history.py` | Full thread comment history | `--thread-id`, `--include-minimized` |
| `test_pr_merge_ready.py` | Check merge readiness | `--pull-request`, `--ignore-ci`, `--ignore-threads` |
| `set_pr_auto_merge.py` | Enable/disable auto-merge | `--pull-request`, `--enable`/`--disable`, `--merge-method` |
| `invoke_pr_comment_processing.py` | Process AI triage output | `--pr-number`, `--verdict`, `--findings-json` |
| `new_pr.py` | Create PR with validation | `--title`, `--body`, `--base` |
| `close_pr.py` | Close PR with comment | `--pull-request`, `--comment` |
| `merge_pr.py` | Merge with strategy | `--pull-request`, `--strategy`, `--delete-branch`, `--auto` |

### Issue Operations (`scripts/issue/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `get_issue_context.py` | Issue metadata | `--issue` |
| `new_issue.py` | Create new issue | `--title`, `--body`, `--labels` |
| `set_issue_labels.py` | Apply labels (auto-create) | `--issue`, `--labels`, `--priority` |
| `set_issue_milestone.py` | Assign milestone | `--issue`, `--milestone` |
| `post_issue_comment.py` | Comments with idempotency | `--issue`, `--body`, `--marker` |
| `invoke_copilot_assignment.py` | Synthesize context for Copilot | `--issue-number`, `--what-if` |
| `set_issue_assignee.py` | Assign users to issues | `--issue`, `--assignees` |

### Milestone Operations (`scripts/milestone/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `get_latest_semantic_milestone.py` | Detect latest semantic version milestone | `--owner`, `--repo` |
| `set_item_milestone.py` | Assign milestone to PR/issue (auto-detect) | `--item-type`, `--item-number`, `--milestone-title` |

### Reactions (`scripts/reactions/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `add_comment_reaction.py` | Add emoji reactions (batch support) | `--comment-ids`, `--reaction`, `--comment-type` |

### Notifications (`scripts/notifications/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `get_actionable_items.py` | List actionable backlog (reviews, authored PRs, assigned issues) | `--owner`, `--repo`, `--limit` |

### Utilities (`scripts/utils/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `extract_github_context.py` | Extract issue/PR references from text | `--text`, `--require-pr`, `--require-issue` |

### Workflow Testing (`scripts/`)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `test_workflow_locally.py` | Test GitHub Actions locally with act | `--workflow`, `--event`, `--job`, `--dry-run` |

---

## Output Format

All scripts output structured JSON:

```bash
result=$(python3 .claude/skills/github/scripts/pr/get_pr_context.py --pull-request 50)
echo "$result" | jq '.Title'
```

Exit codes follow ADR-035: 0=success, 1=logic error, 2=config error, 3=external failure, 4=auth error.

---

## Process

This skill provides a toolkit of Python scripts for GitHub operations. Use scripts directly or compose them into workflows.

**Basic Usage:**

1. Identify the operation needed using the Decision Tree
2. Find the corresponding script in the Script Reference
3. Call the script with required parameters
4. Parse the JSON output

**Example Flow:**

```bash
# Get PR context
python3 .claude/skills/github/scripts/pr/get_pr_context.py --pull-request 123

# Check CI status
python3 .claude/skills/github/scripts/pr/get_pr_checks.py --pull-request 123

# Add comment if needed
python3 .claude/skills/github/scripts/pr/post_pr_comment_reply.py --pull-request 123 --body "CI failures detected"
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Raw `gh pr view` commands | No structured output | Use `get_pr_context.py` |
| Raw `gh api` for comments | Doesn't preserve threading | Use `post_pr_comment_reply.py` |
| Replying to thread expecting auto-resolve | Replies DON'T auto-resolve threads | Use `resolve_pr_review_thread.py` after reply |
| Inline issue creation | Missing validation | Use `new_issue.py` |
| Multiple individual reactions | 88% slower | Use batch mode in `add_comment_reaction.py` |
| Hardcoding owner/repo | Breaks in forks | Let scripts infer from `git remote` |
| Ignoring exit codes | Missing error handling | Check exit codes per ADR-035 |
| Skipping idempotency markers | Duplicate comments | Use `--marker` parameter |
| Raw `gh notify` or notifications API | 403 with app tokens | Use `get_actionable_items.py` |

---

## See Also

| Document | Content |
|----------|---------|
| [examples.md](references/examples.md) | Complete script examples |
| [patterns.md](references/patterns.md) | Reusable workflow patterns |
| [copilot-prompts.md](references/copilot-prompts.md) | Creating @copilot directives |
| [copilot-synthesis-guide.md](references/copilot-synthesis-guide.md) | Copilot context synthesis |
| [api-reference.md](references/api-reference.md) | Exit codes, API endpoints, troubleshooting |
| `scripts/github_core/` | Shared Python helper functions |

---

## Verification

Before completing a GitHub operation:

- [ ] Correct script selected from Decision Tree
- [ ] Required parameters provided (PR/issue number)
- [ ] Response JSON parsed successfully
- [ ] Exit code is 0 (success)
- [ ] State change verified (for mutating operations)
