---
name: github-mcp
description: >
  High-performance GitHub operations using the official GitHub MCP server.
  Provides 5-20ms overhead vs 183ms for PowerShell scripts.
  Use for Claude Code and VS Code Agents.
license: MIT
allowed-tools:
  - mcp__github__*
metadata:
  domains:
    - github
    - pr
    - issue
    - repository
    - actions
    - code-security
  type: integration
  complexity: beginner
  platforms:
    - claude-code
    - vscode-agents
---

# GitHub MCP Skill

High-performance GitHub operations via the official MCP server. Use this skill for Claude Code and VS Code instead of raw `gh` commands.

---

## Prerequisites

The GitHub MCP server must be configured in your MCP settings. See [installation guide](references/installation.md).

---

## Triggers

| Phrase | Tool |
|--------|------|
| `get PR #123` | `mcp__github__pull_request_read` |
| `list issues for milestone` | `mcp__github__list_issues` |
| `create issue` | `mcp__github__issue_write` |
| `merge this PR` | `mcp__github__merge_pull_request` |

---

## Decision Tree

```text
Need GitHub data?
├─ Current user info → GetMe
├─ Repository search → SearchRepositories
├─ File contents → GetFileContents
├─ Code search → SearchCode
├─ Commit history → ListCommits, GetCommit
├─ Branches/Tags → ListBranches, ListTags
├─ Releases → ListReleases, GetLatestRelease
│
├─ Issues
│  ├─ Read issue → IssueRead
│  ├─ Search issues → SearchIssues
│  ├─ List issues → ListIssues
│  ├─ Create/Update → IssueWrite
│  └─ Add comment → AddIssueComment
│
├─ Pull Requests
│  ├─ Read PR → PullRequestRead
│  ├─ List PRs → ListPullRequests
│  ├─ Search PRs → SearchPullRequests
│  ├─ Create PR → CreatePullRequest
│  ├─ Update PR → UpdatePullRequest
│  ├─ Merge PR → MergePullRequest
│  ├─ Update branch → UpdatePullRequestBranch
│  ├─ Write review → PullRequestReviewWrite
│  └─ Reply to comment → AddReplyToPullRequestComment
│
├─ Actions/CI
│  ├─ List workflows → actions_list
│  ├─ Get workflow/run/job → actions_get
│  ├─ Trigger workflow → actions_run_trigger
│  └─ Get job logs → get_job_logs
│
├─ Security
│  ├─ Code scanning alerts → list_code_scanning_alerts, get_code_scanning_alert
│  └─ Dependabot alerts → list_dependabot_alerts, get_dependabot_alert
│
└─ Other
   ├─ Discussions → list_discussions, create_discussion
   ├─ Gists → list_gists, create_gist
   └─ Teams → GetTeams, GetTeamMembers
```

---

## Tool Reference

### Context (`context` toolset)

| Tool | Purpose | Parameters |
|------|---------|------------|
| `GetMe` | Current authenticated user | None |
| `GetTeams` | List teams | `org` |
| `GetTeamMembers` | Team membership | `org`, `team_slug` |

### Repository Operations (`repos` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `SearchRepositories` | Find repositories | `query` |
| `GetFileContents` | Read file content | `owner`, `repo`, `path`, `branch` |
| `ListCommits` | Commit history | `owner`, `repo`, `sha`, `page` |
| `SearchCode` | Code search | `query` |
| `GetCommit` | Single commit details | `owner`, `repo`, `sha` |
| `ListBranches` | Repository branches | `owner`, `repo` |
| `ListTags` | Repository tags | `owner`, `repo` |
| `GetTag` | Tag details | `owner`, `repo`, `tag` |
| `ListReleases` | All releases | `owner`, `repo` |
| `GetLatestRelease` | Latest release | `owner`, `repo` |
| `GetReleaseByTag` | Release by tag | `owner`, `repo`, `tag` |
| `CreateOrUpdateFile` | Write file | `owner`, `repo`, `path`, `content`, `message`, `branch` |
| `CreateRepository` | New repository | `name`, `description`, `private` |
| `ForkRepository` | Fork repo | `owner`, `repo` |
| `CreateBranch` | New branch | `owner`, `repo`, `branch`, `from_branch` |
| `PushFiles` | Push multiple files | `owner`, `repo`, `branch`, `files`, `message` |
| `DeleteFile` | Remove file | `owner`, `repo`, `path`, `message`, `branch`, `sha` |
| `ListStarredRepositories` | User's stars | None |
| `StarRepository` | Star repo | `owner`, `repo` |
| `UnstarRepository` | Unstar repo | `owner`, `repo` |

### Issues (`issues` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `IssueRead` | Get issue details | `owner`, `repo`, `issue_number` |
| `SearchIssues` | Search issues | `query` |
| `ListIssues` | List issues | `owner`, `repo`, `state`, `labels`, `assignee` |
| `ListIssueTypes` | Available issue types | `owner`, `repo` |
| `IssueWrite` | Create/update issue | `owner`, `repo`, `title`, `body`, `labels` |
| `AddIssueComment` | Comment on issue | `owner`, `repo`, `issue_number`, `body` |
| `AssignCopilotToIssue` | Assign Copilot | `owner`, `repo`, `issue_number` |
| `SubIssueWrite` | Manage sub-issues | `owner`, `repo`, `issue_number`, `sub_issue_id` |

### Pull Requests (`pull_requests` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `PullRequestRead` | Get PR details | `owner`, `repo`, `pull_number` |
| `ListPullRequests` | List PRs | `owner`, `repo`, `state`, `head`, `base` |
| `SearchPullRequests` | Search PRs | `query` |
| `MergePullRequest` | Merge PR | `owner`, `repo`, `pull_number`, `merge_method` |
| `UpdatePullRequestBranch` | Update from base | `owner`, `repo`, `pull_number` |
| `CreatePullRequest` | Create PR | `owner`, `repo`, `title`, `body`, `head`, `base` |
| `UpdatePullRequest` | Update PR | `owner`, `repo`, `pull_number`, `title`, `body` |
| `RequestCopilotReview` | Request Copilot review | `owner`, `repo`, `pull_number` |
| `PullRequestReviewWrite` | Submit review | `owner`, `repo`, `pull_number`, `event`, `body` |
| `AddCommentToPendingReview` | Add review comment | `owner`, `repo`, `pull_number`, `path`, `body` |
| `AddReplyToPullRequestComment` | Reply to comment | `owner`, `repo`, `pull_number`, `comment_id`, `body` |

### Actions (`actions` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `actions_list` | List workflows | `owner`, `repo` |
| `actions_get` | Get workflow/run/job | `owner`, `repo`, `workflow_id` or `run_id` or `job_id` |
| `actions_run_trigger` | Trigger workflow | `owner`, `repo`, `workflow_id`, `ref`, `inputs` |
| `get_job_logs` | Job logs | `owner`, `repo`, `job_id` |

### Code Security (`code_security` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_code_scanning_alerts` | List alerts | `owner`, `repo`, `state` |
| `get_code_scanning_alert` | Alert details | `owner`, `repo`, `alert_number` |

### Dependabot (`dependabot` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_dependabot_alerts` | List alerts | `owner`, `repo`, `state` |
| `get_dependabot_alert` | Alert details | `owner`, `repo`, `alert_number` |

### Discussions (`discussions` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_discussions` | List discussions | `owner`, `repo` |
| `get_discussion` | Discussion details | `owner`, `repo`, `discussion_number` |
| `create_discussion` | Create discussion | `owner`, `repo`, `title`, `body`, `category_id` |
| `update_discussion` | Update discussion | `owner`, `repo`, `discussion_number`, `title`, `body` |
| `delete_discussion` | Delete discussion | `owner`, `repo`, `discussion_number` |
| `add_discussion_comment` | Add comment | `owner`, `repo`, `discussion_number`, `body` |
| `update_discussion_comment` | Update comment | `owner`, `repo`, `comment_id`, `body` |
| `delete_discussion_comment` | Delete comment | `owner`, `repo`, `comment_id` |

### Gists (`gists` toolset)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_gists` | List gists | None |
| `get_gist` | Gist details | `gist_id` |
| `create_gist` | Create gist | `description`, `files`, `public` |
| `update_gist` | Update gist | `gist_id`, `description`, `files` |
| `delete_gist` | Delete gist | `gist_id` |

---

## Performance

| Implementation | Overhead | 50 Operations |
|----------------|----------|---------------|
| PowerShell scripts | 183ms | 9.2s |
| MCP server | 5-20ms | 0.25-1s |
| **Improvement** | **89-97%** | **87-96%** |

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Raw `gh pr view` | Slower, no structured output | Use `PullRequestRead` |
| PowerShell scripts (in Claude Code) | 183ms overhead | Use MCP tools |
| Hardcoding owner/repo | Breaks in forks | Infer from git remote |
| Ignoring tool errors | Silent failures | Check response status |

---

## Platform Routing

This skill is for **Claude Code** and **VS Code Agents** only.

For **Copilot CLI** (no MCP support), use the `github` skill with PowerShell/bash scripts.

| Platform | Recommended Skill |
|----------|-------------------|
| Claude Code | `github-mcp` (this skill) |
| VS Code Agents | `github-mcp` (this skill) |
| Copilot CLI | `github` (PowerShell scripts) |

---

## Verification

Before completing a GitHub MCP operation:

- [ ] MCP server configured (`mcp__github__*` tools available)
- [ ] Required parameters provided (owner, repo, etc.)
- [ ] Tool response indicates success
- [ ] State change verified (for mutating operations)

---

## References

- [Installation Guide](references/installation.md) - MCP server setup
- [Dual-Path Strategy](/.agents/architecture/dual-path-strategy.md) - Why both skills exist
- [GitHub MCP Server](https://github.com/github/github-mcp-server) - Official repository
