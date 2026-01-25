# GitHub CLI Projects (v2)

## Prerequisites

```bash
# Add project scope before using project commands
gh auth refresh -s project
gh auth status  # Verify scope added
```

## Skill-GH-Project-001: Project Management (92%)

**Statement**: Use `gh project` for GitHub Projects (v2); requires `project` scope.

```bash
# Create project
gh project create --owner myorg --title "Q1 Roadmap"

# List projects
gh project list --owner myorg

# View project (browser)
gh project view 1 --owner myorg --web

# Close project
gh project close 1 --owner myorg

# Copy project (template)
gh project copy 1 --source-owner source-org --target-owner target-org --title "Copy"

# Link repository
gh project link 1 --owner myorg --repo myorg/myrepo
```

## Skill-GH-Project-002: Project Item Management (91%)

**Statement**: Use `gh project item-add` to add issues/PRs; `gh project field-list` for custom fields.

```bash
# Add issue/PR by URL
gh project item-add 1 --owner myorg --url https://github.com/myorg/repo/issues/123

# Create draft item
gh project item-create 1 --owner myorg --title "New task" --body "Description"

# Edit item field
gh project item-edit --id ITEM_ID --field-id STATUS_FIELD_ID --single-select-option-id OPTION_ID

# Archive item
gh project item-archive 1 --owner myorg --id ITEM_ID

# Create custom field
gh project field-create 1 --owner myorg --name "Priority" --data-type "SINGLE_SELECT"
```

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
