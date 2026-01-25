# Worktrunk Integration Guide

**Atomicity**: 65% (comprehensive reference covering multiple concepts)
**Category**: Git Operations, Worktree Management, Agent Coordination
**Date**: 2026-01-08
**Source**: https://worktrunk.dev/

## Overview

Worktrunk is a CLI tool for git worktree management designed for running multiple AI agents in parallel. It makes "worktrees as easy as branches."

## Installation

```bash
# Homebrew (macOS & Linux)
brew install max-sixty/worktrunk/wt && wt config shell install

# Cargo
cargo install worktrunk && wt config shell install
```

## Core Commands

| Command | Purpose |
|---------|---------|
| `wt switch <branch>` | Navigate to worktree (creates if needed) |
| `wt switch -c <branch>` | Create new branch and worktree |
| `wt switch ^` | Switch to default branch |
| `wt switch -` | Return to previous worktree |
| `wt list` | Show all worktrees with status |
| `wt list --full` | Include CI status and diffs |
| `wt remove` | Remove current worktree |
| `wt merge` | Merge to default branch |
| `wt select` | Interactive picker with preview |
| `wt step <op>` | Execute single operation |

## Configuration Files

- **User config**: `~/.config/worktrunk/config.toml` (no approval needed)
- **Project config**: `.config/wt.toml` (requires approval)

## Hook Types

| Hook | Timing | Blocking | Fail-fast |
|------|--------|----------|-----------|
| `post-create` | After worktree creation | Yes | No |
| `post-start` | After worktree creation | No (background) | No |
| `post-switch` | After every switch | No (background) | No |
| `pre-commit` | Before commit during merge | Yes | Yes |
| `pre-merge` | Before merging to target | Yes | Yes |
| `post-merge` | After successful merge | Yes | No |
| `pre-remove` | Before worktree removal | Yes | Yes |

## Hook Configuration

```toml
# Single command
post-create = "npm install"

# Multiple commands (sequential)
[pre-merge]
lint = "npm run lint"
test = "npm test"
```

## Template Variables

| Variable | Description |
|----------|-------------|
| `{{ branch }}` | Current branch name |
| `{{ repo }}` | Repository name |
| `{{ worktree_path }}` | Absolute worktree path |
| `{{ default_branch }}` | Default branch name |
| `{{ branch \| sanitize }}` | Branch with `/` replaced by `-` |
| `{{ branch \| hash_port }}` | Unique port (10000-19999) |

## ai-agents Configuration Pattern

**For current configuration**, see `.config/wt.toml` and `.worktreeinclude` in repository.

**Example implementation pattern**:

```toml
# .config/wt.toml
[post-create]
# Configure git hooks path to .githooks directory
configure-hooks = "git config core.hooksPath .githooks"

# Copy gitignored files from main worktree to eliminate cold starts
copy = "wt step copy-ignored"

[pre-merge]
# Run markdown linting before merge to catch documentation issues
# Fails on violations without modifying files (no --fix flag prevents uncommitted changes during merge)
lint = "npx markdownlint-cli2 \"**/*.md\""
```

**Example copy-ignored configuration** (`.worktreeinclude`):

```text
node_modules/
.cache/
```

**Pattern**: Configure hooks and copy dependencies on worktree creation. Validate before merge.

## Claude Code Integration

Install plugin: `claude plugin marketplace add max-sixty/worktrunk`

Status indicators in `wt list`:

- 🤖 = Claude actively working
- 💬 = Claude waiting for input

## Workflow Example

```bash
# Create feature worktree
wt switch --create feat/feature-name

# Work on feature (hooks configure environment automatically)
# - git hooks configured
# - node_modules copied from main worktree
# - ready to work immediately

# Merge when done (pre-merge hooks validate)
wt merge  # Runs markdown linting before merge

# Cleanup is automatic
```

## Benefits

- **Parallel agent isolation**: Each agent gets own worktree
- **Automated setup**: Hooks configure git hooks, copy dependencies
- **No cold starts**: Dependencies copied from main worktree
- **Local CI gates**: Pre-merge validation catches issues before remote push
- **Visual tracking**: See Claude activity across worktrees with `wt list`

## Related

- parallel-001-worktree-isolation: Worktree isolation patterns
- git-hooks-001-pre-commit-branch-validation: Pre-commit hook patterns
- Analysis: `.agents/analysis/worktrunk-integration.md`
- Documentation: AGENTS.md Worktrunk Setup section

## Related

- [git-003-staged-changes-guard](git-003-staged-changes-guard.md)
- [git-004-branch-switch-file-verification](git-004-branch-switch-file-verification.md)
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md)
- [git-branch-cleanup-pattern](git-branch-cleanup-pattern.md)
- [git-conflict-deleted-file](git-conflict-deleted-file.md)
