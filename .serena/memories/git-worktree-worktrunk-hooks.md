# Worktrunk Post-Create Hook for Git Hooks Configuration

**Atomicity**: 95%
**Category**: Git Operations, Worktree Management
**Date**: 2026-01-08

## Context

When using Worktrunk (git worktree management tool) to create worktrees, git hooks path configuration must be set in each worktree to ensure pre-commit and other hooks work correctly.

## Pattern

Configure post-create hook in `.config/wt.toml` at repository root:

```toml
# Worktrunk Configuration
# Documentation: https://worktrunk.dev/hook/

[post-create]
# Configure git hooks path to .githooks directory
# This ensures pre-commit and other hooks work in worktrees
configure-hooks = "git config core.hooksPath .githooks"
```

## Worktrunk Hook Types

Available hook types (from https://worktrunk.dev/hook/):

- **post-create**: Runs after worktree creation, blocks until complete (use for required setup)
- **post-start**: Runs after creation in background (parallel execution)
- **post-switch**: Runs after every switch operation in background
- **pre-commit**: Runs before committing during merge, fail-fast
- **pre-merge**: Runs before merging to target, fail-fast
- **post-merge**: Runs after successful merge, best-effort
- **pre-remove**: Runs before worktree removal, fail-fast

## Configuration Location

- **Project hooks**: `.config/wt.toml` in repository root
- **User hooks**: `~/.config/worktrunk/config.toml` (applies to all repositories)

## Template Variables

Worktrunk supports template variables that expand at runtime:

- `{{ repo }}`: Repository name
- `{{ branch }}`: Branch name
- `{{ worktree_path }}`: Path to worktree
- `{{ commit }}`: Commit SHA
- `{{ branch | sanitize }}`: Branch name with slashes replaced by dashes
- `{{ branch | hash_port }}`: Deterministic port (10000-19999) from branch name

## Decision Rationale

**Why post-create over post-start**:
- post-create blocks until complete, ensuring hooks are configured before worktree use
- post-start runs in background, could race with first commit attempt

**Why named command format**:
- `configure-hooks = "command"` is more semantic than just `"command"`
- Easier to understand and maintain with multiple hooks

## Related

- parallel-001-worktree-isolation: Worktree isolation patterns
- git-hooks-001-pre-commit-branch-validation: Pre-commit hook patterns
