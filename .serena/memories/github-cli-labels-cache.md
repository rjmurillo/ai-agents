# GitHub CLI Labels, Cache, and Rulesets

## Skill-GH-Label-001: Label Creation (94%)

**Statement**: Use `gh label create` with `--color` (hex) and `--description`; `--force` to update.

```bash
# Create with color and description
gh label create "bug" --color E99695 --description "Something isn't working"

# Create priority labels
gh label create "priority:critical" --color FF0000 --description "Critical priority"
gh label create "priority:high" --color FFA500 --description "High priority"

# Update existing label
gh label create "bug" --color FF0000 --force

# Edit properties
gh label edit "old-name" --name "new-name"
```

**Note**: Color values require exactly 6 hex characters (no # prefix).

## Skill-GH-Label-002: Label Cloning (91%)

**Statement**: Use `gh label clone` to copy label sets between repositories.

```bash
# Clone labels from source to current repo
gh label clone source-owner/source-repo

# Clone with force overwrite
gh label clone source-owner/template-repo --force
```

**Best Practice**: Maintain template repository with standard labels.

## Skill-GH-Cache-001: Actions Cache Management (90%)

**Statement**: Use `gh cache list` to audit; `gh cache delete --all` to reclaim storage.

```bash
# Sort by size (find largest)
gh cache list --json key,sizeInBytes --jq 'sort_by(.sizeInBytes) | reverse | .[:5]'

# Delete all caches
gh cache delete --all
```

**Use Case**: Clear caches when builds fail due to stale dependencies.

## Skill-GH-Ruleset-001: Ruleset Compliance (89%)

**Statement**: Use `gh ruleset check` to validate branch compliance before pushing.

```bash
# Check if branch complies
gh ruleset check feature-branch

# List all rulesets
gh ruleset list

# Pre-push check
gh ruleset check my-branch && git push
```

**Alias**: `gh rs` (shorthand for ruleset commands)

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
