# Worktree Triage: Live Versus Abandoned

Use this reference when a worktree looks owned, when a fleet leaves worktrees
behind, or before you remove any worktree whose tip may be unreachable. The
Serena memory `fleet-worktree-live-versus-abandoned` holds the measurements
that motivated each step; this file holds the procedure.

## Step 1: Age, not name, decides live versus abandoned

A dirty worktree proves someone once started, not that anyone is working now.
The agent fleet is not durable state; a runtime wipe leaves every worktree
behind. Treat "dirty" as "owned" and every orphaned issue stays frozen.

A worktree is LIVE only when its newest file touch is under about 60 minutes
old. Anything older with uncommitted edits or unpushed commits is ABANDONED and
is a harvest candidate, not an exclusion zone. The age is a first filter, not
a verdict: a long read-only review phase can pass 60 minutes without a write,
so Step 2 confirms with the file list before you act.

Linux, or macOS with GNU findutils (`gfind` in place of `find`):

```bash
newest=$(find "$p" -path '*/.git' -prune -o -type f -printf '%T@\n' | sort -rn | head -1)
python3 -c "import time,sys; print(int((time.time()-float(sys.argv[1]))/60))" "$newest"
```

macOS with the default BSD `find` (no `-printf`):

```bash
newest=$(find "$p" -path '*/.git' -prune -o -type f -exec stat -f '%m' {} + | sort -rn | head -1)
python3 -c "import time,sys; print(int((time.time()-float(sys.argv[1]))/60))" "$newest"
```

Windows PowerShell:

```powershell
$newest = Get-ChildItem $p -Recurse -File |
  Where-Object FullName -NotMatch '[\\/]\.git[\\/]' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
[int]((Get-Date) - $newest.LastWriteTime).TotalMinutes
```

The later steps are Bash; run them from Git Bash or WSL on Windows.

Do not match directory basenames against dispatched agent names. A basename
with a numeric collision suffix reads as a live agent and is not one; the
false-LIVE direction is the expensive one.

## Step 2: Confirm with the file list

Age alone can mislead. Check whether the worktree holds the specific files you
need:

```bash
git -C "$p" status --porcelain
```

## Step 3: Do not over-claim unlanded work

`git rev-list --count origin/main..HEAD` overstates unlanded work in a
squash-merge repository: a squash-merged branch still reports all of its
original commits as ahead. `git ls-remote` returning nothing is not proof
either; GitHub deletes head branches after merge.

Test whether the branch's own changed files still differ from `main`:

```bash
git -C "$p" diff -z --name-only origin/main...HEAD \
  | xargs -0 -r git -C "$p" diff --name-only origin/main HEAD -- \
  | wc -l
```

The NUL-delimited pipe keeps a path with spaces, tabs, or glob characters as
one pathspec; an unquoted `$own` expansion would split it and drop the file
from the comparison.

The count is an upper bound (it also counts files `main` moved on its own).
Treat it as a triage signal, never as a finding.

## Step 4: At fleet scale, join against pull request state

Per-worktree checks do not scale past a few dozen worktrees, and every cheap
test fails the same way: landed work and lost work both show "not on main, no
remote branch". One API call classifies the fleet against recent pull requests:

```bash
gh pr list --state all --limit 1000 --json number,state,headRefName,headRefOid
```

Join by branch name. Three populations fall out; all three can hold work that
is absent from `main`, so the join changes triage priority, not certainty.

| Population | Verdict |
|---|---|
| Detached checkout, no branch | Review leftovers; confirm reachability with `git for-each-ref --contains "$sha"` before removal |
| Branch is head of a MERGED pull request | Landed; anchor its tip first, since a merged head can carry a later stranded commit |
| Named branch, no pull request in the fetched set | Highest-priority triage; most likely to hold lost work |

When a branch appears in more than one pull request, let MERGED win only when
that pull request's `headRefOid` matches the worktree's current tip. A reused
head name can span an older merged PR, a newer open PR, and a local post-merge
tip; a tip that does not match the merged OID needs individual triage.

Sort the third population by commit date, not commit count. Paginate the pull
request query before treating absence from the fetched set as proof that no
pull request exists.

## Step 5: Anchor unreachable tips before removing anything

Removing a worktree drops its tip when nothing else references it. Create two
independent anchors first:

```bash
SALVAGE_DIR="$HOME/salvage"   # any directory outside the repository
mkdir -p "$SALVAGE_DIR"
git update-ref "refs/salvage/<nnn>-<branch-slug>" "$sha"   # once per tip
git for-each-ref --format="%(refname)" refs/salvage/ \
  | git bundle create "$SALVAGE_DIR/tips.bundle" --stdin
git bundle verify "$SALVAGE_DIR/tips.bundle"
```

`git bundle create` refuses a list of bare SHAs (`Refusing to create empty
bundle`), so `update-ref` is a prerequisite. The refs survive `git gc` and live
in the canonical repository where a worktree prune cannot orphan them. The
bundle survives losing the repository.

## Step 6: Harvest on merit

Abandoned work is unreviewed, unproven, and often wrong. Keep only what you
verify independently, and say what you discarded.
