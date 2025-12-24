# GitHub CLI Repository Management

## Skill-GH-Repo-001: Repository Settings (94%)

**Statement**: Use `gh repo edit` with feature flags; use `--visibility` with acknowledgment flag.

```bash
# Enable/disable features
gh repo edit --enable-discussions --enable-projects
gh repo edit --enable-squash-merge --delete-branch-on-merge

# Security features
gh repo edit --enable-advanced-security
gh repo edit --enable-secret-scanning --enable-secret-scanning-push-protection

# Change visibility (requires acknowledgment)
gh repo edit --visibility private --accept-visibility-change-consequences

# Set default branch
gh repo edit --default-branch main
```

## Skill-GH-Repo-002: Fork Synchronization (92%)

**Statement**: Use `gh repo sync` to keep forks current; `--force` for hard reset.

```bash
# Sync local fork with parent
gh repo sync

# Sync specific branch
gh repo sync --branch v1

# Force sync (overwrites local changes)
gh repo sync --force
```

## Skill-GH-Repo-003: Deploy Key Management (91%)

**Statement**: Use `gh repo deploy-key` for CI/CD SSH key management.

```bash
# Add with write permission
gh repo deploy-key add key.pub --title "Deploy Key" --allow-write

# List deploy keys
gh repo deploy-key list

# Delete by ID
gh repo deploy-key delete 12345
```

## Skill-GH-Repo-004: Repository Lifecycle (90%)

**Statement**: Use `gh repo archive` to deprecate while preserving history.

```bash
# Archive (read-only, preserves history)
gh repo archive owner/repo

# Unarchive (reactivate)
gh repo unarchive owner/repo

# Rename
gh repo rename old-name new-name

# Set default repo for commands
gh repo set-default owner/repo
```

**Anti-pattern**: Deleting repos instead of archiving loses history and breaks links.
