# GitHub CLI Extension Maintenance

## Skill-Ext-Maint-001: Update All Extensions

**Statement**: Use `gh extension upgrade --all` to update all installed extensions.

```bash
# Upgrade all extensions
gh extension upgrade --all

# Upgrade specific extension
gh extension upgrade notify
```

## Skill-Ext-Maint-002: List Installed Extensions

**Statement**: Use `gh extension list` to view installed extensions with versions.

```bash
gh extension list
```

**Output Format**: `name  owner/repo  version`

## Skill-Ext-Maint-003: Remove Extension

**Statement**: Use `gh extension remove` to uninstall an extension.

```bash
gh extension remove extension-name
```

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
