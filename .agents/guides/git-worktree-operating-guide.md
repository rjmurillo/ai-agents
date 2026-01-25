# Guidance for an AI Agent: Using Git Worktrees to Level Up

Git worktrees let you check out **multiple branches from one clone** into separate folders. You get:

- Fast context switching (no stash, no clean/reset loops)
- Real parallelism (feature work + bugfix + review in separate dirs)
- Shared object database (less disk and faster fetch than multiple clones)

This is ideal for AI agents that run experiments, make changes, and validate without polluting a single working directory.

---

## Mental model (what a worktree is)

- One "primary" repo holds the **.git** directory (objects, refs).
- Each worktree is a separate working directory with its own:
  - checked-out branch (or detached HEAD)
  - index
  - untracked files
- All worktrees share:
  - object store (commits/blobs)
  - refs namespace (branches/tags are global to the repo)

**Implication:** you can work in parallel safely, but branch names and ref updates are shared.

---

## Recommended layout

Create a parent folder that holds the main repo and all worktrees as siblings.

```text
/repos/myproj/
  main/                 # primary worktree (clean, stable)
  wt-feature-xyz/       # feature branch
  wt-bugfix-123/        # bugfix branch
  wt-review-pr456/      # PR review / reproduction
```

**Rule:** never nest worktrees inside each other.

---

## Agent operating policy (high signal rules)

### Hard rules

1. **Do not do real work in `main/`.** Treat it as a clean baseline.
2. **One task = one worktree.** No mixed goals in one directory.
3. **One branch can be checked out by only one worktree at a time.**
4. **Never delete a worktree folder with `rm -rf`.** Use `git worktree remove`.

### Soft rules (strongly preferred)

- Use short-lived worktrees for experiments; keep only what you need.
- Use clear naming: `wt-<type>-<ticket>-<slug>`.

---

## Standard lifecycle (create, work, validate, integrate, clean)

### 0) Ensure baseline is clean and up to date

In `main/`:

```bash
git status --porcelain
git fetch --prune
git switch main
git pull --ff-only
```

### 1) Create a new worktree for a task

From `main/`:

```bash
# Create branch and worktree in one step (preferred)
git worktree add -b feature/xyz ../wt-feature-xyz origin/main
```

If the branch already exists:

```bash
git worktree add ../wt-feature-xyz feature/xyz
```

### 2) Work inside the new worktree

```bash
cd ../wt-feature-xyz
git status
# edit files
git diff
```

### 3) Validate locally (in the worktree)

Run build/test/lint in the worktree directory.

- Keep build outputs isolated per worktree.
- Share only safe caches (NuGet packages, etc.), not `bin/obj`.

Example (.NET):

- OK to share: global NuGet cache (`~/.nuget/packages`)
- Avoid sharing: `bin/`, `obj/` across worktrees

### 4) Commit and push

```bash
git add -A
git commit -m "feat: implement xyz"
git push -u origin feature/xyz
```

### 5) Clean up the worktree after merge (or abandonment)

From anywhere in the repo:

```bash
git worktree remove ../wt-feature-xyz
git branch -d feature/xyz         # only if merged
# if not merged and you are discarding:
git branch -D feature/xyz
```

---

## Process flow (agent-safe)

```text
[main clean?] -> no -> [stop: fix or reset]
      |
     yes
      v
[fetch+rebase/pull baseline]
      |
      v
[create worktree+branch]
      |
      v
[edit+test in worktree]
      |
      v
[commit+push]
      |
      v
[PR/merge]
      |
      v
[worktree remove + branch delete]
```

---

## Worktree naming conventions (reduce collisions)

Use a predictable scheme:

- `wt-feature-<ticket>-<slug>`
- `wt-bugfix-<ticket>-<slug>`
- `wt-spike-<topic>`
- `wt-review-<pr#>`

Branch naming:

- `feature/<ticket>-<slug>`
- `bugfix/<ticket>-<slug>`
- `spike/<topic>`

This avoids multiple agents fighting over the same branch name.

---

## Parallelism patterns (what to do for multi-agent work)

### Pattern A: One repo, many worktrees, one agent per worktree

- Best for local multi-tasking and bounded concurrency.
- Shared object store is efficient.
- Shared refs mean you must coordinate branch names.

### Pattern B: "Golden main" + ephemeral task worktrees

- Keep `main/` always clean and aligned to `origin/main`.
- Create and delete worktrees per attempt.
- Minimizes residue from failed experiments.

---

## Safety rails and inspection commands

List worktrees:

```bash
git worktree list
```

See which branches are currently checked out somewhere:

```bash
git branch --show-current
git worktree list --porcelain
```

Prune stale metadata (after manual folder moves or crashes):

```bash
git worktree prune
```

Lock a worktree (prevents accidental removal):

```bash
git worktree lock ../wt-feature-xyz
git worktree unlock ../wt-feature-xyz
```

---

## Avoid these common agent mistakes

1. **Editing in `main/` then creating a branch**

   - You risk bringing accidental changes and untracked files along.
   - Fix: create worktree first, then edit.

2. **Reusing one worktree for multiple tasks**

   - You mix diffs, confuse tests, and break bisectability.
   - Fix: one task per worktree.

3. **Checking out the same branch in two worktrees**

   - Git blocks this for good reason.
   - Fix: new branch per attempt, or detach for experiments.

4. **Running destructive operations globally**

   - `git gc`, `git repack`, aggressive cleanup affects all worktrees.
   - Fix: avoid unless you own the repo state.

---

## Advanced: Detached experiments (fast spike without branch pressure)

For throwaway exploration:

```bash
git worktree add --detach ../wt-spike origin/main
cd ../wt-spike
# experiment
```

If the spike becomes real work:

```bash
git switch -c spike/my-idea
```

---

## Advanced: Per-worktree configuration (reduce surprises)

If you need different settings per worktree:

```bash
git config worktreeConfig true
# then in a worktree:
git config user.name "Agent"
git config user.email "agent@local"
```

Use with caution if you share the repo with humans.

---

## Troubleshooting

### "fatal: 'branch' is already checked out at ..."

That branch is attached to another worktree.

- Fix: pick a new branch name, or remove the other worktree.

### Worktree folder deleted manually, Git still thinks it exists

```bash
git worktree prune
git worktree list
```

### You need to recreate a worktree with the same path

Remove first:

```bash
git worktree remove ../wt-feature-xyz
```

---

## Minimal "agent checklist" before claiming completion

In the worktree:

- `git status --porcelain` is clean (except intentional changes)
- tests pass in that worktree
- commits are focused and small
- branch pushed to origin
- worktree removed after merge (or locked if still active)

---

## TL;DR for agents

- Treat `main/` as immutable baseline.
- Create a worktree per task.
- Validate inside that worktree.
- Push, PR, merge.
- Remove the worktree cleanly.
