# GitHub Extension: gh-milestone (valeriobelli/gh-milestone)

## Skill-Ext-Milestone-001: Create Milestone

**Statement**: Use `gh milestone create` with `--title`, `--description`, `--due-date` for non-interactive creation.

```bash
# Create with all flags (non-interactive)
gh milestone create --title "v2.0.0" --description "Major release" --due-date 2025-03-01

# Create with title only
gh milestone create --title "Sprint 5"

# Target different repo
gh milestone create --title "v1.0" --repo owner/other-repo
```

**Date Format**: `YYYY-MM-DD`

## Skill-Ext-Milestone-002: List Milestones

**Statement**: Use `gh milestone list` with `--json` and `--jq` for scriptable output.

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
```

**JSON Fields**: id, number, title, description, dueOn, progressPercentage, state, url

## Skill-Ext-Milestone-003: Edit Milestone

**Statement**: Use `gh milestone edit <number>` with flags to modify existing milestones.

```bash
# Edit title
gh milestone edit 1 --title "v2.0.0-rc1"

# Edit due date
gh milestone edit 1 --due-date 2025-04-01

# Combine edits
gh milestone edit 1 --title "v2.0" --due-date 2025-05-01 --description "Final release"
```

## Skill-Ext-Milestone-004: Delete Milestone

**Statement**: Use `gh milestone delete <number> --confirm` to delete without interactive prompt.

```bash
# Delete with confirmation bypass
gh milestone delete 1 --confirm
```

**Warning**: Deletion is permanent and removes the milestone from all associated issues.
