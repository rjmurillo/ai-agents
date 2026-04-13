# GitHub Extension: gh-sub-issue (yahsan2/gh-sub-issue)

Parent-child issue hierarchy management (GitHub supports up to 8 levels).

## Skill-Ext-SubIssue-001: Link Existing Issue as Sub-Issue

**Statement**: Use `gh sub-issue add` to create parent-child relationships between issues.

```bash
# Link by issue numbers (parent, child)
gh sub-issue add 123 456

# Using parent URL
gh sub-issue add https://github.com/owner/repo/issues/123 456

# Cross-repository linking
gh sub-issue add 123 456 --repo owner/repo
```

## Skill-Ext-SubIssue-002: Create New Sub-Issue

**Statement**: Use `gh sub-issue create` with `--parent` and `--title` for non-interactive creation.

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
```

## Skill-Ext-SubIssue-003: List Sub-Issues

**Statement**: Use `gh sub-issue list` to view child issues of a parent.

```bash
# List sub-issues by parent number
gh sub-issue list 123

# Target specific repo
gh sub-issue list 123 --repo owner/repo
```

## Skill-Ext-SubIssue-004: Remove Sub-Issue Link

**Statement**: Use `gh sub-issue remove` to unlink child from parent.

```bash
# Remove sub-issue link
gh sub-issue remove 123 456

# Target specific repo
gh sub-issue remove 123 456 --repo owner/repo
```

## Related

- [gh-extensions-anti-patterns](gh-extensions-anti-patterns.md)
- [gh-extensions-combine-prs](gh-extensions-combine-prs.md)
- [gh-extensions-grep](gh-extensions-grep.md)
- [gh-extensions-hook](gh-extensions-hook.md)
- [gh-extensions-maintenance](gh-extensions-maintenance.md)
