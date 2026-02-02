# GitHub Extension: gh-combine-prs (rnorth/gh-combine-prs)

## Skill-Ext-Combine-001: Batch Dependabot PRs

**Statement**: Use `gh combine-prs --query` to merge multiple PRs into a single combined PR.

**Prerequisites**: Requires `jq` installed.

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

## Important Notes

- Creates a candidate PR for review (doesn't auto-merge to main)
- When merging the combined PR, use **Merge Commit** (not squash) so GitHub marks original PRs as merged
- Only combines PRs that merge cleanly without conflicts

## Related

- [gh-extensions-anti-patterns](gh-extensions-anti-patterns.md)
- [gh-extensions-grep](gh-extensions-grep.md)
- [gh-extensions-hook](gh-extensions-hook.md)
- [gh-extensions-maintenance](gh-extensions-maintenance.md)
- [gh-extensions-metrics](gh-extensions-metrics.md)
