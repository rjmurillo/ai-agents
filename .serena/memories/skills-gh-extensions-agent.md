# GitHub CLI Extensions for Agent Use

## Overview

This memory documents GitHub CLI extensions that are compatible with non-interactive agent workflows. All extensions listed here can be used programmatically via the Bash tool without requiring user interaction.

**Last Updated**: 2025-12-19
**Agent Compatibility**: All skills verified for non-interactive CLI use
**Installation Pattern**: `gh extension install <owner>/<repo>`

---

## Extension: gh-notify (meiji163/gh-notify)

### Skill-Ext-Notify-001: List Notifications (Static Mode)

**Statement**: Use `gh notify -s` for static (non-interactive) notification listing; combine with `-n`, `-f`, `-e` for filtering.

**Agent Compatibility**: YES - Use `-s` flag for static output.

**Pattern**:

```bash
# List unread notifications (static mode - REQUIRED for agents)
gh notify -s

# Limit to N notifications
gh notify -s -n 20

# Show all (read + unread)
gh notify -s -a

# Only participating/mentioned
gh notify -s -p

# Filter by regex pattern
gh notify -s -f "security"
gh notify -s -f "dependabot"

# Exclude by regex pattern
gh notify -s -e "bot"
gh notify -s -e "renovate"

# Combine filters
gh notify -s -n 50 -f "ai-agents" -e "dependabot"
```

**Output Format**:
```
●  26min ago  rjmurillo/ai-agents  PullRequest  #94  review_requested  Title here
```

**Columns**: unread_symbol, time, repo, type, number, reason, title

**Atomicity**: 95%

---

### Skill-Ext-Notify-002: Mark Notifications as Read

**Statement**: Use `gh notify -r` to mark all notifications as read in batch.

**Agent Compatibility**: YES - Non-interactive bulk operation.

**Pattern**:

```bash
# Mark ALL notifications as read
gh notify -r
```

**Use Case**: Clear notification backlog after processing.

**Atomicity**: 90%

---

### Skill-Ext-Notify-003: Subscribe/Unsubscribe to Issues

**Statement**: Use `gh notify -u URL` to toggle subscription on specific issues/PRs.

**Agent Compatibility**: YES - URL-based targeting.

**Pattern**:

```bash
# Subscribe to an issue
gh notify -u https://github.com/owner/repo/issues/123

# Unsubscribe (toggle - run again)
gh notify -u https://github.com/owner/repo/issues/123
```

**Atomicity**: 92%

---

## Extension: gh-combine-prs (rnorth/gh-combine-prs)

### Skill-Ext-Combine-001: Batch Dependabot PRs

**Statement**: Use `gh combine-prs --query` to merge multiple PRs into a single combined PR.

**Agent Compatibility**: YES - Fully flag-driven.

**Prerequisites**: Requires `jq` installed.

**Pattern**:

```bash
# Combine all Dependabot PRs
gh combine-prs --query "author:app/dependabot"

# Combine renovate PRs
gh combine-prs --query "author:app/renovate"

# Combine by label
gh combine-prs --query "label:dependencies"

# Limit number of PRs
gh combine-prs --query "author:app/dependabot" --limit 10

# Select specific PRs by number
gh combine-prs --query "author:app/dependabot" --selected-pr-numbers "12,34,56"

# Skip status checks (use with caution)
gh combine-prs --query "author:app/dependabot" --skip-pr-check
```

**Important Notes**:
- Creates a candidate PR for review (doesn't auto-merge to main)
- When merging the combined PR, use **Merge Commit** (not squash) so GitHub marks original PRs as merged
- Only combines PRs that merge cleanly without conflicts

**Atomicity**: 94%

---

## Extension: gh-metrics (hectcastro/gh-metrics)

### Skill-Ext-Metrics-001: PR Review Analytics

**Statement**: Use `gh metrics --repo` to calculate PR review metrics for team health analysis.

**Agent Compatibility**: YES - Outputs table or CSV.

**Pattern**:

```bash
# Default metrics (last 10 days)
gh metrics --repo owner/repo

# Custom date range
gh metrics --repo owner/repo --start 2025-01-01 --end 2025-01-31

# Filter by author
gh metrics --repo owner/repo --query "author:username"

# Only weekdays (exclude weekends)
gh metrics --repo owner/repo --only-weekdays

# CSV export for further processing
gh metrics --repo owner/repo --csv > metrics.csv

# Current repo (uses git remote)
gh metrics
```

**Metrics Calculated**:

| Metric | Description |
|--------|-------------|
| Time to First Review | PR creation → first review |
| Feature Lead Time | First commit → merge |
| First to Last Review | First review → final approval |
| First Approval to Merge | First approval → merge |

**Use Cases**:
- Identify review bottlenecks
- Track team velocity
- Benchmark sprint performance
- Generate reports for stakeholders

**Atomicity**: 93%

---

## Extension: gh-milestone (valeriobelli/gh-milestone)

### Skill-Ext-Milestone-001: Create Milestone

**Statement**: Use `gh milestone create` with `--title`, `--description`, `--due-date` for non-interactive creation.

**Agent Compatibility**: YES - Use flags to avoid interactive prompts.

**Pattern**:

```bash
# Create with all flags (non-interactive)
gh milestone create --title "v2.0.0" --description "Major release" --due-date 2025-03-01

# Create with title only
gh milestone create --title "Sprint 5"

# Target different repo
gh milestone create --title "v1.0" --repo owner/other-repo
```

**Date Format**: `YYYY-MM-DD` (e.g., 2025-03-01)

**Atomicity**: 94%

---

### Skill-Ext-Milestone-002: List Milestones

**Statement**: Use `gh milestone list` with `--json` and `--jq` for scriptable output.

**Agent Compatibility**: YES - JSON output for parsing.

**Pattern**:

```bash
# List open milestones (default)
gh milestone list

# List all states
gh milestone list --state all
gh milestone list --state closed

# Limit results
gh milestone list --first 10

# Search by pattern
gh milestone list --query "v2"

# JSON output for scripting
gh milestone list --json id,title,progressPercentage,dueOn

# Extract specific field with jq
gh milestone list --json id,number --jq ".[0].id"

# Sort by due date
gh milestone list --orderBy.field due_date --orderBy.direction asc

# Target different repo
gh milestone list --repo owner/repo
```

**JSON Fields Available**: id, number, title, description, dueOn, progressPercentage, state, url

**Atomicity**: 95%

---

### Skill-Ext-Milestone-003: Edit Milestone

**Statement**: Use `gh milestone edit <number>` with flags to modify existing milestones.

**Agent Compatibility**: YES - Fully flag-driven.

**Pattern**:

```bash
# Edit title
gh milestone edit 1 --title "v2.0.0-rc1"

# Edit due date
gh milestone edit 1 --due-date 2025-04-01

# Edit description
gh milestone edit 1 --description "Updated scope"

# Combine edits
gh milestone edit 1 --title "v2.0" --due-date 2025-05-01 --description "Final release"
```

**Atomicity**: 93%

---

### Skill-Ext-Milestone-004: Delete Milestone

**Statement**: Use `gh milestone delete <number> --confirm` to delete without interactive prompt.

**Agent Compatibility**: YES - Use `--confirm` flag.

**Pattern**:

```bash
# Delete with confirmation bypass
gh milestone delete 1 --confirm

# Target different repo
gh milestone delete 1 --confirm --repo owner/repo
```

**Warning**: Deletion is permanent and removes the milestone from all associated issues.

**Atomicity**: 91%

---

## Extension: gh-hook (lucasmelin/gh-hook)

### Skill-Ext-Hook-001: List Webhooks

**Statement**: Use `gh hook list` to view repository webhooks.

**Agent Compatibility**: YES - Read-only operation.

**Pattern**:

```bash
# List webhooks for current repo
gh hook list

# Target specific repo
gh hook list --repo owner/repo
```

**Note**: Requires admin access to the repository.

**Atomicity**: 90%

---

### Skill-Ext-Hook-002: Create Webhook from File

**Statement**: Use `gh hook create --file` for non-interactive webhook creation from JSON.

**Agent Compatibility**: YES - Use `--file` flag to avoid TUI.

**Pattern**:

```bash
# Create from JSON file
gh hook create --file webhook.json

# Target specific repo
gh hook create --file webhook.json --repo owner/repo
```

**JSON File Format**:

```json
{
  "active": true,
  "events": ["push", "pull_request", "issues"],
  "config": {
    "url": "https://example.com/webhook",
    "content_type": "json",
    "insecure_ssl": "0",
    "secret": "optional-webhook-secret"
  }
}
```

**Common Events**: push, pull_request, issues, issue_comment, create, delete, release, workflow_run

**Atomicity**: 92%

---

### Skill-Ext-Hook-003: Delete Webhook

**Statement**: Use `gh hook delete` to remove webhooks by ID.

**Agent Compatibility**: YES - ID-based targeting.

**Pattern**:

```bash
# Delete webhook by ID
gh hook delete 12345678

# Target specific repo
gh hook delete 12345678 --repo owner/repo
```

**Atomicity**: 89%

---

## Extension: gh-gr (sarumaj/gh-gr)

### Skill-Ext-GR-001: Initialize Multi-Repo Mirror

**Statement**: Use `gh gr init` to set up management of multiple repositories in a directory.

**Agent Compatibility**: YES - Fully flag-driven.

**Pattern**:

```bash
# Initialize with directory
gh gr init --dir ~/projects

# With concurrency limit
gh gr init --dir ~/projects --concurrency 10

# Create subdirectories per org/user
gh gr init --dir ~/projects --subdirs

# Include only specific repos (regex)
gh gr init --dir ~/projects --include "myorg/.*"

# Exclude repos (regex)
gh gr init --dir ~/projects --exclude ".*-archive" --exclude "fork-.*"

# Size limit (exclude large repos)
gh gr init --dir ~/projects --sizelimit 52428800  # 50MB

# Combine all options
gh gr init --dir ~/github --subdirs --concurrency 20 --include "myorg/.*" --exclude ".*-deprecated"
```

**Atomicity**: 93%

---

### Skill-Ext-GR-002: Pull All Repositories

**Statement**: Use `gh gr pull` to fetch updates for all managed repositories.

**Agent Compatibility**: YES - Batch operation.

**Pattern**:

```bash
# Pull all repos
gh gr pull

# With custom concurrency
gh gr pull --concurrency 20

# With retry on rate limits
gh gr pull --retry

# With timeout
gh gr pull --timeout 5m
```

**Atomicity**: 94%

---

### Skill-Ext-GR-003: Check Status Across Repos

**Statement**: Use `gh gr status` to view git status for all managed repositories.

**Agent Compatibility**: YES - Outputs status summary.

**Pattern**:

```bash
# Show status for all repos
gh gr status

# Reset all dirty repos to remote state (DESTRUCTIVE)
gh gr status --reset-all
```

**Warning**: `--reset-all` discards all uncommitted changes.

**Atomicity**: 92%

---

### Skill-Ext-GR-004: Push All Repositories

**Statement**: Use `gh gr push` to push changes for all managed repositories.

**Agent Compatibility**: YES - Batch operation.

**Pattern**:

```bash
# Push all repos
gh gr push

# With concurrency
gh gr push --concurrency 10
```

**Atomicity**: 91%

---

### Skill-Ext-GR-005: Export/Import Configuration

**Statement**: Use `gh gr export` and `gh gr import` to backup/restore multi-repo configuration.

**Agent Compatibility**: YES - File-based.

**Pattern**:

```bash
# Export config to file
gh gr export > gr-config.json

# Import config from file
gh gr import < gr-config.json

# View current config
gh gr view
```

**Atomicity**: 90%

---

## Extension: gh-grep (k1LoW/gh-grep)

### Skill-Ext-Grep-001: Search Code Across Repositories

**Statement**: Use `gh grep` with `--include` filter for performance; searches via GitHub API.

**Agent Compatibility**: YES - Outputs search results.

**Performance Warning**: This tool is SLOW because it uses GitHub API. Always use `--include` to filter files.

**Pattern**:

```bash
# Search in specific repo
gh grep "TODO" --repo owner/repo

# Search with owner scope (all org repos)
gh grep "deprecated" --owner myorg

# Filter by file pattern (CRITICAL for performance)
gh grep "FROM.*alpine" --owner myorg --include "Dockerfile"
gh grep "password" --repo owner/repo --include "*.py"

# Exclude files/directories
gh grep "secret" --repo owner/repo --exclude "*test*"
gh grep "api_key" --repo owner/repo --exclude "*.md"

# Case insensitive
gh grep -i "fixme" --repo owner/repo

# Show line numbers
gh grep -n "TODO" --repo owner/repo

# Output with GitHub URLs (clickable)
gh grep "security" --repo owner/repo --url

# Show only matching parts
gh grep -o "v[0-9]+\.[0-9]+\.[0-9]+" --repo owner/repo

# Count matches only
gh grep -c "TODO" --repo owner/repo

# Show only filenames
gh grep --name-only "pattern" --repo owner/repo

# Show only repo names
gh grep --repo-only "pattern" --owner myorg

# Search specific branch
gh grep "feature" --repo owner/repo --branch develop

# Search specific tag
gh grep "version" --repo owner/repo --tag v1.0.0
```

**Use Cases**:
- Security audits (find hardcoded secrets patterns)
- Dependency audits (find specific import patterns)
- License compliance (find license headers)
- Migration planning (find deprecated API usage)

**Atomicity**: 88%

---

## Extension: gh-sub-issue (yahsan2/gh-sub-issue)

### Skill-Ext-SubIssue-001: Link Existing Issue as Sub-Issue

**Statement**: Use `gh sub-issue add` to create parent-child relationships between issues.

**Agent Compatibility**: YES - Fully flag-driven.

**Pattern**:

```bash
# Link by issue numbers (parent, child)
gh sub-issue add 123 456

# Using parent URL
gh sub-issue add https://github.com/owner/repo/issues/123 456

# Cross-repository linking
gh sub-issue add 123 456 --repo owner/repo
```

**Note**: GitHub supports up to 8 levels of issue hierarchy.

**Atomicity**: 93%

---

### Skill-Ext-SubIssue-002: Create New Sub-Issue

**Statement**: Use `gh sub-issue create` with `--parent` and `--title` for non-interactive creation.

**Agent Compatibility**: YES - Use flags to avoid prompts.

**Pattern**:

```bash
# Minimal creation
gh sub-issue create --parent 123 --title "Implement feature X"

# With body
gh sub-issue create --parent 123 --title "Bug fix" --body "Description here"

# With labels
gh sub-issue create --parent 123 --title "Task" --label bug --label priority

# With assignees
gh sub-issue create --parent 123 --title "Review" --assignee username

# With milestone
gh sub-issue create --parent 123 --title "Sprint task" --milestone "Sprint 5"

# Add to project(s)
gh sub-issue create --parent 123 --title "Roadmap item" --project "Q1 Goals"
gh sub-issue create --parent 123 --title "Task" --project "Sprint" --project "Roadmap"

# Cross-repo parent
gh sub-issue create --parent https://github.com/owner/other/issues/123 --title "Sub-task"

# Specify repo for new issue
gh sub-issue create --parent 123 --title "Task" --repo owner/repo
```

**Atomicity**: 94%

---

### Skill-Ext-SubIssue-003: List Sub-Issues

**Statement**: Use `gh sub-issue list` to view child issues of a parent.

**Agent Compatibility**: YES - Outputs list.

**Pattern**:

```bash
# List sub-issues by parent number
gh sub-issue list 123

# Target specific repo
gh sub-issue list 123 --repo owner/repo
```

**Atomicity**: 92%

---

### Skill-Ext-SubIssue-004: Remove Sub-Issue Link

**Statement**: Use `gh sub-issue remove` to unlink child from parent.

**Agent Compatibility**: YES - ID-based targeting.

**Pattern**:

```bash
# Remove sub-issue link
gh sub-issue remove 123 456

# Target specific repo
gh sub-issue remove 123 456 --repo owner/repo
```

**Atomicity**: 91%

---

## Extension Maintenance

### Skill-Ext-Maint-001: Update All Extensions

**Statement**: Use `gh extension upgrade --all` to update all installed extensions.

**Pattern**:

```bash
# Upgrade all extensions
gh extension upgrade --all

# Upgrade specific extension
gh extension upgrade notify
```

**Atomicity**: 95%

---

### Skill-Ext-Maint-002: List Installed Extensions

**Statement**: Use `gh extension list` to view installed extensions with versions.

**Pattern**:

```bash
gh extension list
```

**Output Format**: `name  owner/repo  version`

**Atomicity**: 98%

---

### Skill-Ext-Maint-003: Remove Extension

**Statement**: Use `gh extension remove` to uninstall an extension.

**Pattern**:

```bash
gh extension remove extension-name
```

**Atomicity**: 95%

---

## Quick Reference: Agent-Compatible Commands

| Extension | Agent Command | Purpose |
|-----------|---------------|---------|
| gh-notify | `gh notify -s` | Static notification listing |
| gh-notify | `gh notify -r` | Mark all as read |
| gh-combine-prs | `gh combine-prs --query` | Batch dependency PRs |
| gh-metrics | `gh metrics --repo` | PR review analytics |
| gh-milestone | `gh milestone list --json` | List milestones (JSON) |
| gh-milestone | `gh milestone create --title` | Create milestone |
| gh-hook | `gh hook list` | List webhooks |
| gh-hook | `gh hook create --file` | Create from JSON |
| gh-gr | `gh gr status` | Multi-repo status |
| gh-gr | `gh gr pull` | Pull all repos |
| gh-grep | `gh grep --include` | Code search |
| gh-sub-issue | `gh sub-issue add` | Link issues |
| gh-sub-issue | `gh sub-issue create --parent --title` | Create sub-issue |

---

## Anti-Patterns

### Anti-Pattern-Ext-001: Using Interactive Mode

**Problem**: Running extensions without required flags launches interactive TUI.

**Solution**: Always use `-s` (notify), `--file` (hook), or required flags (milestone, sub-issue).

### Anti-Pattern-Ext-002: gh-grep Without Include Filter

**Problem**: `gh grep` without `--include` is extremely slow.

**Solution**: Always specify `--include "*.extension"` to filter file types.

### Anti-Pattern-Ext-003: Forgetting Merge Commit for Combined PRs

**Problem**: Squash merging a combined PR leaves original PRs open.

**Solution**: Always use **Merge Commit** when merging combined PRs.

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-agent-workflow-phase3](skills-agent-workflow-phase3.md)
- [skills-agent-workflows](skills-agent-workflows.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-analysis](skills-analysis.md)
