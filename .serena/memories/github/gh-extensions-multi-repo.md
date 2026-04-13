# GitHub Extension: gh-gr (sarumaj/gh-gr)

Multi-repository management for cloning, syncing, and status checking across organizations.

## Skill-Ext-GR-001: Initialize Multi-Repo Mirror

**Statement**: Use `gh gr init` to set up management of multiple repositories in a directory.

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

## Skill-Ext-GR-002: Pull All Repositories

**Statement**: Use `gh gr pull` to fetch updates for all managed repositories.

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

## Skill-Ext-GR-003: Check Status Across Repos

**Statement**: Use `gh gr status` to view git status for all managed repositories.

```bash
# Show status for all repos
gh gr status

# Reset all dirty repos to remote state (DESTRUCTIVE)
gh gr status --reset-all
```

**Warning**: `--reset-all` discards all uncommitted changes.

## Skill-Ext-GR-004: Push All Repositories

**Statement**: Use `gh gr push` to push changes for all managed repositories.

```bash
# Push all repos
gh gr push

# With concurrency
gh gr push --concurrency 10
```

## Skill-Ext-GR-005: Export/Import Configuration

**Statement**: Use `gh gr export` and `gh gr import` to backup/restore multi-repo configuration.

```bash
# Export config to file
gh gr export > gr-config.json

# Import config from file
gh gr import < gr-config.json

# View current config
gh gr view
```

## Related

- [gh-extensions-anti-patterns](gh-extensions-anti-patterns.md)
- [gh-extensions-combine-prs](gh-extensions-combine-prs.md)
- [gh-extensions-grep](gh-extensions-grep.md)
- [gh-extensions-hook](gh-extensions-hook.md)
- [gh-extensions-maintenance](gh-extensions-maintenance.md)
