# Worktrunk Integration Analysis

**Date**: 2026-01-08
**Status**: Complete
**Source**: https://worktrunk.dev/

## Executive Summary

Worktrunk is a CLI tool that simplifies git worktree management. It makes "worktrees as easy as branches." The tool was designed for running multiple AI agents in parallel. It provides lifecycle hooks, LLM commit message generation, Claude Code integration, and CI status tracking.

This analysis covers the full Worktrunk feature set and identifies integration opportunities for the ai-agents project.

---

## 1. What is Worktrunk?

### 1.1 Core Purpose

Worktrunk addresses the clunky native git worktree UX by:

- Computing paths from configurable templates
- Allowing worktrees to be addressed by branch name alone
- Automating the full worktree lifecycle (create, merge, remove)
- Providing hooks for setup automation
- Tracking CI status across worktrees

### 1.2 Installation

**Homebrew (macOS & Linux):**

```bash
brew install max-sixty/worktrunk/wt && wt config shell install
```

**Cargo:**

```bash
cargo install worktrunk && wt config shell install
```

Shell integration is required for directory switching with `wt switch`.

### 1.3 Configuration Files

| File | Purpose | Approval |
|------|---------|----------|
| `~/.config/worktrunk/config.toml` | User settings for all repos | Not required |
| `.config/wt.toml` | Project-specific hooks | Required |

---

## 2. Core Commands

### 2.1 wt switch

Navigate between worktrees, creating if needed.

```bash
wt switch <BRANCH>                    # Switch to existing or create
wt switch --create <BRANCH>           # Create new branch and worktree
wt switch --create <BRANCH> --base=@  # Branch from current HEAD
wt switch ^                           # Switch to default branch
wt switch -                           # Return to previous worktree
wt switch feat --execute claude       # Switch and launch Claude
```

**Options:**

- `--create, -c`: Create new branch
- `--base, -b <BASE>`: Specify base branch
- `--execute, -x <CMD>`: Run command after switch
- `--yes, -y`: Skip approval prompts
- `--clobber`: Remove stale paths
- `--no-verify`: Skip hooks

**Branch Shortcuts:**

- `^` = Default branch (main/master)
- `@` = Current branch/worktree
- `-` = Previous worktree

### 2.2 wt list

Display worktrees with status information.

```bash
wt list                    # Standard table view
wt list --full             # Include CI status and diffs
wt list --branches         # Include branches without worktrees
wt list --format=json      # JSON output for scripting
wt list --progressive      # Show fast info immediately
```

**Output Columns:**

- Branch name
- Status symbols (staged, modified, untracked, conflicts)
- HEAD commits (uncommitted changes)
- Divergence from default branch and remote
- Commit hash and age
- Last commit message

**With --full:**

- Line diffs vs merge-base
- CI pipeline status (passed/running/failed)
- Remote divergence details

### 2.3 wt remove

Delete worktrees and branches after confirming merge.

```bash
wt remove                  # Remove current, return to main
wt remove feature          # Remove specific branch
wt remove --no-delete-branch  # Keep the branch
wt remove -D               # Force delete unmerged
wt remove -f               # Remove with untracked files
```

**Safety Features:**

- Automatic merged-branch detection
- Works across squash-merge and rebase workflows
- Background operation by default
- Logs saved to `.git/wt-logs/{branch}-remove.log`

### 2.4 wt merge

Merge current branch into target (default branch).

```bash
wt merge                   # Merge to default branch
wt merge release           # Merge to specific target
wt merge --no-squash       # Preserve individual commits
wt merge --no-remove       # Keep worktree after merge
```

**Processing Pipeline:**

1. Squash commits (creates backup ref)
2. Rebase if behind target
3. Pre-merge hooks (fail-fast)
4. Fast-forward merge
5. Pre-remove hooks
6. Cleanup worktree/branch
7. Post-merge hooks (best-effort)

### 2.5 wt select

Interactive worktree picker with live preview.

**Preview Tabs (1-4):**

- HEAD: Uncommitted changes diff
- log: Recent commits
- main: Changes since merge-base
- remote: Comparison against upstream

**Controls:**

- Arrow keys: Navigate
- Enter: Switch
- Escape: Cancel
- Typing: Filter by name
- Alt-p: Toggle preview

### 2.6 wt step

Execute individual workflow operations.

```bash
wt step commit             # Create commit with AI message
wt step squash             # Consolidate commits
wt step rebase             # Rebase onto target
wt step push               # Advance target branch
wt step copy-ignored       # Transfer .worktreeinclude files
wt step for-each <cmd>     # Run command across all worktrees
```

### 2.7 wt config

Manage configuration and state.

```bash
wt config create           # Create user config
wt config create --project # Create project config
wt config shell install    # Install shell integration
wt config state marker set "🤖"  # Set status marker
```

---

## 3. Hooks System

### 3.1 Hook Types

| Hook | Timing | Blocking | Fail-fast |
|------|--------|----------|-----------|
| `post-create` | After worktree creation | Yes | No |
| `post-start` | After worktree creation | No (background) | No |
| `post-switch` | After every switch | No (background) | No |
| `pre-commit` | Before commit during merge | Yes | Yes |
| `pre-merge` | Before merging to target | Yes | Yes |
| `post-merge` | After successful merge | Yes | No |
| `pre-remove` | Before worktree removal | Yes | Yes |

**Key Distinctions:**

- `post-create`: Blocking setup tasks (dependency install)
- `post-start`: Long-running tasks (dev servers)
- `pre-merge`: Local CI gates (tests, linting)

### 3.2 Configuration Format

**Single command:**

```toml
post-create = "npm install"
```

**Multiple commands (sequential):**

```toml
[pre-merge]
lint = "npm run lint"
test = "npm test"
```

### 3.3 Template Variables

**Repository & Path:**

- `{{ repo }}`: Repository directory name
- `{{ repo_path }}`: Absolute path to repository root
- `{{ worktree_path }}`: Absolute worktree path
- `{{ main_worktree_path }}`: Default branch worktree path

**Branch & Commit:**

- `{{ branch }}`: Current branch name
- `{{ commit }}`: Full HEAD commit SHA
- `{{ short_commit }}`: Short commit SHA
- `{{ default_branch }}`: Default branch name

**Merge-Specific:**

- `{{ target }}`: Target branch (merge hooks only)
- `{{ base }}`: Base branch (creation hooks only)

**Remote:**

- `{{ remote }}`: Primary remote name
- `{{ remote_url }}`: Remote URL
- `{{ upstream }}`: Upstream tracking branch

### 3.4 Filters

- `{{ branch | sanitize }}`: Replace `/` and `\` with `-`
- `{{ branch | hash_port }}`: Hash to port range 10000-19999

### 3.5 JSON Context

Hooks receive full context as JSON on stdin:

```json
{
  "repo": "myproject",
  "branch": "feature/auth",
  "hook_type": "post-create",
  "hook_name": "install"
}
```

### 3.6 Security Model

- Project hooks require approval on first run
- Approvals saved to user config
- Re-approval triggers when commands change
- User hooks never require approval

---

## 4. Claude Code Integration

### 4.1 Plugin Installation

```bash
claude plugin marketplace add max-sixty/worktrunk
claude plugin install worktrunk@worktrunk
```

### 4.2 Status Indicators

The plugin tracks Claude activity in worktrees:

- **🤖**: Claude is actively working
- **💬**: Claude is waiting for input

### 4.3 Statusline Integration

```bash
wt list statusline --claude-code
```

Configure in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "wt list statusline --claude-code"
  }
}
```

Example output: `~/w/myproject.feature-auth !🤖 @+42 -8 ↑3 ⇡1 ●`

---

## 5. Advanced Features

### 5.1 LLM Commit Generation

Configure in user config:

```toml
[commit_generation]
command = "llm"
args = ["-m", "claude-3-opus", "Write a commit message for:\n{{ git_diff }}"]
```

### 5.2 Copy-Ignored Files

Create `.worktreeinclude` listing gitignored files to copy:

```text
node_modules/
.cache/
.env.local
```

Run in post-create hook:

```toml
[post-create]
copy = "wt step copy-ignored"
```

### 5.3 Deterministic Ports

Each worktree gets a unique dev server port:

```toml
[post-start]
dev = "npm run dev -- --port {{ branch | hash_port }}"
```

### 5.4 Database Isolation

```toml
[post-start]
db = "docker run -d --name {{ repo }}-{{ branch | sanitize }}-postgres postgres:15"

[pre-remove]
db-stop = "docker stop {{ repo }}-{{ branch | sanitize }}-postgres 2>/dev/null || true"
```

---

## 6. ai-agents Project Integration

### 6.1 Current State

The ai-agents project already has:

- Post-create hook for git hooks configuration
- Pre-commit hooks in `.githooks/` directory
- `core.hooksPath` set to `.githooks`

### 6.2 Integration Opportunities

#### 6.2.1 Enhanced Hooks Configuration

Current `.config/wt.toml`:

```toml
[post-create]
configure-hooks = "git config core.hooksPath .githooks"
```

Potential enhancements:

```toml
[post-create]
configure-hooks = "git config core.hooksPath .githooks"
copy = "wt step copy-ignored"

[pre-merge]
lint = "npx markdownlint-cli2 --fix '**/*.md'"
test = "pwsh scripts/Validate-Session.ps1 -SessionLogPath .agents/sessions/*.md"
```

#### 6.2.2 Claude Code Plugin

Install the Worktrunk Claude Code plugin to track agent activity across worktrees. This enables:

- Visual status in `wt list` output
- Statusline integration showing current worktree
- Agent coordination across parallel worktrees

#### 6.2.3 Copy-Ignored for Dependencies

Create `.worktreeinclude`:

```text
node_modules/
.cache/
```

This eliminates cold starts when creating new worktrees.

#### 6.2.4 Pre-merge Validation

Add pre-merge hooks for session protocol validation:

```toml
[pre-merge]
protocol = "pwsh scripts/Validate-Session.ps1 -SessionLogPath .agents/sessions/*.md -PreCommit"
lint = "npx markdownlint-cli2 '**/*.md'"
```

### 6.3 Workflow Integration

**Recommended workflow for parallel agent work:**

1. Create worktree: `wt switch --create feat/feature-name`
2. Post-create hook configures git hooks automatically
3. Start Claude in worktree
4. Work on feature
5. Pre-merge hooks validate before merge
6. Merge: `wt merge`
7. Cleanup automatic

### 6.4 Benefits

| Benefit | Description |
|---------|-------------|
| Isolation | Each agent gets independent worktree |
| No uncommitted mixing | Changes don't leak between agents |
| Automated setup | Hooks configure environment automatically |
| Local CI | Pre-merge validation catches issues early |
| Visual tracking | See agent status across all worktrees |

---

## 7. Platform Considerations

### 7.1 Windows Support

Core commands work on Git Bash (recommended) and PowerShell. However:

- Hooks fail in pure PowerShell (bash syntax)
- `wt select` unavailable on Windows

**Recommendation**: Use Git Bash or WSL for hook execution.

### 7.2 Cross-Platform Hooks

For cross-platform hooks, consider PowerShell scripts:

```toml
[post-create]
configure-hooks = "pwsh -c 'git config core.hooksPath .githooks'"
```

---

## 8. Security Considerations

### 8.1 Hook Approval Model

- Project hooks require explicit user approval
- Approvals stored in user config
- Command changes trigger re-approval

### 8.2 Recommendations

1. Review `.config/wt.toml` before approving
2. Use `--no-verify` sparingly
3. Keep hook commands simple and auditable

---

## 9. Recommendations

### 9.1 Immediate Actions

1. **Install Claude Code plugin** for agent status tracking
2. **Create `.worktreeinclude`** for dependency sharing
3. **Add pre-merge hooks** for validation

### 9.2 Future Enhancements

1. Add database isolation hooks for services
2. Configure LLM commit generation
3. Add post-start hooks for development servers
4. Create project-specific documentation

### 9.3 Documentation Updates

1. Add Worktrunk setup instructions to AGENTS.md
2. Document parallel agent workflow
3. Update CLAUDE.md with Worktrunk integration notes

---

## 10. References

- [Worktrunk Documentation](https://worktrunk.dev/)
- [Claude Code Integration](https://worktrunk.dev/claude-code/)
- [Hooks Reference](https://worktrunk.dev/hook/)
- [Tips & Patterns](https://worktrunk.dev/tips-patterns/)
- [FAQ](https://worktrunk.dev/faq/)

---

## Appendix A: Quick Reference

### Commands

| Command | Purpose |
|---------|---------|
| `wt switch <branch>` | Navigate to worktree |
| `wt switch -c <branch>` | Create branch and worktree |
| `wt list` | Show all worktrees |
| `wt list --full` | Include CI status |
| `wt remove` | Remove current worktree |
| `wt merge` | Merge to default branch |
| `wt select` | Interactive picker |
| `wt step <op>` | Execute single operation |
| `wt config create` | Create config file |

### Hook Types

| Hook | When | Blocking |
|------|------|----------|
| `post-create` | After creation | Yes |
| `post-start` | After creation | No |
| `post-switch` | After switch | No |
| `pre-commit` | Before commit | Yes |
| `pre-merge` | Before merge | Yes |
| `post-merge` | After merge | Yes |
| `pre-remove` | Before remove | Yes |

### Template Variables

| Variable | Description |
|----------|-------------|
| `{{ branch }}` | Current branch name |
| `{{ repo }}` | Repository name |
| `{{ worktree_path }}` | Worktree path |
| `{{ branch \| sanitize }}` | Safe branch name |
| `{{ branch \| hash_port }}` | Unique port (10000-19999) |
