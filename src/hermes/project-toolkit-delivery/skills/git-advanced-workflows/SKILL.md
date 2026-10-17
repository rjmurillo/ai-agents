---
name: git-advanced-workflows
version: 1.2.0
description: Advanced Git workflows for rebasing, cherry-picking, bisect, worktrees, and reflog. Use when managing complex Git histories, collaborating on feature branches, or recovering from repo issues. Use when you say "rebase my branch", "cherry-pick a commit", "find the breaking commit", "recover lost commits", "triage stale worktrees", or "sync or publish a dirty checkout".
license: MIT
---

# Git Advanced Workflows

Advanced Git techniques for clean history, effective collaboration, and confident recovery.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `rebase my branch` | Interactive or standard rebase guidance |
| `cherry-pick a commit` | Cherry-pick with conflict resolution |
| `find the breaking commit` | Git bisect workflow |
| `recover lost commits` | Reflog exploration and recovery |
| `sync or publish a dirty checkout` | Commit local work and bring the branch up to date, or move only requested files to a clean topic branch |

## Process

### Phase 1: Assess the Situation

1. Identify which workflow applies (rebase, cherry-pick, bisect, worktree, sync, publish, recovery)
2. Check current branch state: `git status`, `git log --oneline -10`
3. Create a safety branch before any destructive operation: `git branch backup-<timestamp>`
   - macOS/Linux (bash/zsh): `git branch backup-$(date +%s)`
   - Windows PowerShell: `git branch backup-$(Get-Date -UFormat %s)`

### Phase 2: Execute the Workflow

#### Rebase: Clean Up Feature Branch Before PR

```bash
git checkout feature/user-auth
# Record the remote tip BEFORE rewriting. A later fetch moves the tracking
# ref, so reading it at push time would let the lease overwrite new commits.
git fetch origin
EXPECTED_REMOTE_SHA=$(git rev-parse origin/feature/user-auth)
git rebase -i main
# Squash "fix typo" commits, reword messages, reorder logically
git push --force-with-lease="refs/heads/feature/user-auth:$EXPECTED_REMOTE_SHA" \
  origin HEAD:refs/heads/feature/user-auth
```

**Rebase operations:** `pick` (keep), `reword` (change message), `edit` (amend content), `squash` (combine keeping message), `fixup` (combine discarding message), `drop` (remove).

**Autosquash pattern:**

```bash
git commit --fixup HEAD        # Mark as fixup for previous commit
git rebase -i --autosquash main  # Auto-marks fixup commits
```

**Split a commit:**

```bash
git rebase -i HEAD~3          # Mark commit with 'edit'
git reset HEAD^               # Reset commit, keep changes in working tree (unstaged)
git add file1.py && git commit -m "feat: add validation"
git add file2.py && git commit -m "feat: add error handling"
git rebase --continue
```

#### Cherry-Pick: Apply Hotfix to Multiple Releases

```bash
git checkout main
git commit -m "fix: critical security patch"

git checkout release/2.0
git cherry-pick abc123

git checkout release/1.9
git cherry-pick abc123
# On conflict: fix files, git add, git cherry-pick --continue
```

**Partial cherry-pick** (specific files only):

```bash
git show --name-only abc123
git restore --staged --worktree --source=abc123 -- path/to/file1.py path/to/file2.py  # --staged stages the changes so the following commit captures them
git commit -m "cherry-pick: apply specific changes from abc123"
```

#### Bisect: Find Bug Introduction

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.1.0
# Git checks out middle commit. Run tests, mark good/bad, repeat.
git bisect reset  # When done
```

**Automated bisect:**

```bash
git bisect start HEAD v2.1.0
git bisect run ./test.sh
# test.sh: exit 0 = good, 125 = skip, any other non-zero = bad
```

#### Worktree: Multi-Branch Development

```bash
git worktree add ~/worktrees/myapp-hotfix hotfix/critical-bug
# Work in the new worktree using the -C flag to avoid changing the current directory.
# e.g., git -C ~/worktrees/myapp-hotfix commit -a -m "fix: critical bug"
git worktree remove ~/worktrees/myapp-hotfix  # Clean up when done
git worktree prune  # Remove stale entries
```

**Publish requested files from a stale or dirty checkout.** Leave the source
checkout untouched, and move only the requested paths to a clean topic branch:

1. Fetch the intended remote. Inspect the source branch, status, latest commit,
   and divergence before touching anything.
2. Confirm the worktree path and branch name are unused, then add a clean
   worktree from the fetched base.
3. For each requested tracked path, check whether upstream changed it since the
   merge base. The three-dot form diffs from the merge base, so local commits
   on the path do not count as upstream change.
4. If upstream left the path alone, apply the source's diff from the merge base.
   That diff carries local commits and uncommitted edits on the path, and
   `--binary` lets binary files apply. Copy requested untracked files directly.
5. If upstream changed the path, stop. Do a three-way merge and inspect every
   conflict instead of copying the whole file.
6. Byte-compare each candidate path with the source.
7. Stage only requested paths. Inspect the staged names and diff, and run the
   checks that fit the artifact.
8. Commit with the repository's configured `user.name` and `user.email`. Add a
   DCO sign-off (`-s`) when the repository requires one.
9. Fetch and rebase the topic branch right before pushing. Push the topic
   branch, never a protected default branch. Fetch again and confirm the remote
   ref equals `HEAD`.
10. Leave unrelated edits in the source checkout intact, and report them
    separately.

```bash
git fetch origin
git -C <source> status --short --branch
git worktree add -b <feature> <worktree> origin/<base>
base=$(git -C <source> merge-base HEAD origin/<base>)
# Exit 0 means upstream never touched the path since the merge base
git -C <source> diff --quiet HEAD...origin/<base> -- <path>
git -C <source> diff --binary "$base" -- <path> | git -C <worktree> apply --index
cmp <source>/<path> <worktree>/<path>
git -C <worktree> diff --cached --name-only
git -C <worktree> commit -m "<type>(<scope>): <desc>"
git -C <worktree> fetch origin && git -C <worktree> rebase origin/<base>
git -C <worktree> push origin HEAD:refs/heads/<feature>
git -C <worktree> fetch origin
test "$(git -C <worktree> rev-parse HEAD)" = "$(git -C <worktree> rev-parse origin/<feature>)"
```

**Move-safe caveat:** moving a worktree after `uv` created `.venv` leaves the
absolute-path shebangs in `.venv/bin/*` (POSIX) or `.venv/Scripts/*` (Windows)
stale, so direct `.venv/bin/pytest` calls fail with "bad interpreter". Run
`scripts/maintenance/repair_worktree_venv.py` with `uv run python` (or run
`uv sync --frozen --extra dev --reinstall`) to rewrite them, and prefer
`uv run python -m pytest` for move-safe validation. Each flag earns its place:
`--reinstall` recreates the launchers (a plain `--frozen` sync no-ops when the
packages already appear installed and leaves the stale shebangs unrewritten),
`--extra dev` keeps pytest/ruff/mypy in the repaired venv, and `--frozen`
reproduces `uv.lock` without re-resolving so the result matches CI.

**Shared-state caveat:** every worktree shares one `.git`. Only `HEAD` and the
other pseudorefs, the index, the working tree, `refs/bisect/*`,
`refs/worktree/*`, and `refs/rewritten/*` belong to one worktree. Every branch,
every tag, `refs/remotes/*`, and `refs/stash` are shared. Three traps follow
when several sessions work one clone at once:

| Hazard | Symptom | First command | Fix |
|--------|---------|---------------|-----|
| Stash is repo-wide | `git stash list` shows an entry you never made, or `git stash pop` conflicts on a file you never touched | `git stash list --format='%gd %gs'` and read the `WIP on <branch>` subject | Pop only an entry that names your branch, by index, onto a clean tree. Undo a foreign pop with the steps below. Save your own work as a WIP commit on your branch instead of stashing |
| Base goes stale in long runs | Gates or conflicts appear on files you never touched, after a local run was green | `git fetch origin main && git rev-list --left-right --count origin/main...HEAD` | A non-zero left count means your branch lacks commits on `main`. `git merge origin/main`, regenerate, and re-run the failing gate. A fetch in any worktree moves `origin/main` for all of them but never moves your branch |
| "Next free number" races | Two branches add the same sequential id (spec, ADR, record) and each passes alone | After `git merge origin/main`, re-run the id-uniqueness check | Renumber the unmerged side. Allocate the id after a fresh fetch, as late as possible before commit |

**Undo a foreign pop.** Git refuses a pop over unstaged edits to the same
path, but merges it into staged edits. Do not reset to `HEAD`; that discards
your staged work. Record the entry first: `sha=$(git rev-parse 'stash@{N}')`.

- Conflicting pop (exit 1, entry kept): for each `UU` path, run
  `git checkout --ours -- <path> && git add -- <path>`. Stage 2 holds your
  pre-pop version, staged edits included. Then reverse the paths it applied
  cleanly: `git diff "$sha^1" "$sha" -- <paths> | git apply -R --index`.
- Clean pop (exit 0): it dropped the owner's entry. Restore that first with
  `git stash store -m restored <sha>`, taking `<sha>` from the
  `Dropped refs/stash@{0} (<sha>)` line. Reverse it the same way; for a path
  you had staged, drop `--index`.

#### Synchronize a Dirty Checkout with the Latest Remote Head

When asked to commit local changes and bring the checkout up to date, inspect
`git status --short --branch`, the current branch, remotes, and
`git log -1 --oneline`. Fetch the intended remote and measure divergence with
`git rev-list --left-right --count <remote>/<branch>...HEAD`. The left count is
remote-ahead and the right count is local-ahead, the same orientation as the
Shared-state table above.

Review the complete working-tree diff, including untracked files, before
staging. Stage only intended paths, inspect the staged names and diff, run
`git diff --cached --check`, and commit. `git rebase` refuses to start while
unstaged edits remain, so deal with the leftovers first. Commit them as a
separate WIP commit, or move the requested work to a clean worktree with the
Publish procedure above. Do not use `--autostash`: the stash is repo-wide (see
the Shared-state caveat).

If the branch is behind and private, create a safety branch (Phase 1 step 3),
then rebase local commits onto the fetched remote head. Use a merge for a
shared branch. Do not reset away local commits or discard working-tree changes
to make the graph look current.

If the rebase conflicts, inspect the base, the local commit, and the conflict
hunks before resolving each file. During a rebase, `--ours` is the branch being
rebased onto (upstream) and `--theirs` is your local commit, the reverse of a
merge. That swap is the usual reason a mechanical pick discards the wrong side.
Never choose either side mechanically: one commit can hold valuable changes on
both sides.

After integration, confirm every intended path is committed and the left
(remote-ahead) count is `0`. A non-zero right count is committed work not yet
published. If the user asked for the remote to hold the work too, push the
branch, fetch again, and confirm the count is `0 0` and the remote ref equals
`HEAD`.

#### Recovery: Undo Mistakes with Reflog

```bash
git reflog                     # Find lost commit hash
git reset --hard def456        # Restore to that state
# Or create branch: git branch recovery def456
```

**Abort operations in progress:**

```bash
git rebase --abort
git merge --abort
git cherry-pick --abort
git bisect reset
```

**Other recovery commands:**

```bash
git restore --source=abc123 path/to/file  # Restore file from commit
git reset --soft HEAD^                     # Undo commit, keep changes staged
git reflog                                 # 1. Find the hash of the desired commit
git branch recovered abc123                # 2. Create a branch from that hash (within reflog retention; ~90 days by default, configurable)
```

#### Worktree: Triage Live Versus Abandoned

A dirty worktree proves someone once started, not that anyone is working now.
Before standing down on an issue because a worktree looks owned, or before
removing a worktree whose tip may be unreachable, follow
`references/worktree-triage.md`: measure the newest file age (live means under
about 60 minutes), confirm with `git -C "$p" status --porcelain`, join the
fleet against `gh pr list --state all --json number,state,headRefName,headRefOid`,
and anchor every unreachable tip with `git update-ref refs/salvage/...` plus a
verified bundle before `git worktree remove`.

### Phase 3: Verify and Clean Up

1. Confirm working tree is clean: `git status`
2. Validate history: `git log --oneline` matches expectations
3. Run tests after any history rewrite
4. Remove worktrees if created: `git worktree list`

## Decision Guide

### Rebase vs Merge

| Use Rebase | Use Merge |
|------------|-----------|
| Cleaning local commits before push | Integrating completed features into main |
| Keeping feature branch current with main | Preserving exact collaboration history |
| Creating linear history for review | Public branches used by others |

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Rebasing shared branches | Rewrites history for all collaborators | Merge for shared branches |
| `--force`, or a bare `--force-with-lease` | Overwrites teammates' work; a fetch can advance the lease's expected value | Pin the lease to an observed SHA: `--force-with-lease=<ref>:<sha>` |
| Bisecting on dirty working tree | Checkout fails with uncommitted changes | Commit or stash first |
| Orphaned worktrees | Consume disk space silently | Remove after use |
| `git stash` with several live worktrees | One stash stack serves every worktree; `pop` takes the newest entry, whoever made it | WIP commit on your own branch |
| Treating a dirty worktree as owned | Freezes issues whose worktree a fleet wipe orphaned | Measure file age and list files (`references/worktree-triage.md`) |
| Removing a worktree before anchoring its tip | Drops commits nothing else references | `git update-ref refs/salvage/<slug> <sha>` and bundle first |
| No backup before complex rebase | No recovery path if rebase fails | Create safety branch first |

## Verification

- [ ] Working tree is clean (`git status`)
- [ ] Branch history matches expectations (`git log --oneline`)
- [ ] Tests pass after history rewrite
- [ ] Force push pinned `--force-with-lease=<ref>:<sha>` to an observed SHA
- [ ] Worktrees cleaned up (`git worktree list`)
