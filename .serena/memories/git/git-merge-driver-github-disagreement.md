# GitHub Runs No Custom Merge Driver, So Local and Server Merges Disagree

**Category**: Git Operations
**Source**: 2026-07-28, PR #3636. Verified on git 2.43.0.

Symptom this explains: a PR that GitHub reports `CONFLICTING` while a local merge
is clean, or the reverse.

Precondition: a custom driver must actually be running. Read
`git-merge-driver-declared-versus-running.md` first. A definition existing is not
proof that it ran, and a conflict is not proof either. Most of the time no driver
runs, and then this whole mechanism is a dead end.

## Statement

A custom merge driver is a shell command named in git config, local, global, or
system. GitHub computes mergeability on its own servers, where that config does
not exist, so the command cannot run there. A merge involving a path served by a
custom driver can be clean locally and `CONFLICTING` on GitHub, or the reverse,
and both answers are correct for the code that produced them.

Both directions reproduce locally:

| edits | with driver | without driver |
|---|---|---|
| overlapping | exits 0, driver resolves | exits 1, text merge conflicts |
| non-overlapping | exits 1, driver declines | exits 0, text merge succeeds |

The limit is on **custom** drivers only. Built-ins (`text`, `binary`, `union`)
are compiled into git rather than configured, so a path using one is not subject
to it.

`origin/main` currently ships no custom driver definition, so this mechanism is
dormant for a clean clone. It is not dormant in a clone carrying a stale
definition, and it returns the moment a driver is added.

## Triage

Read `docs/autonomous-pr-monitor.md` "Stale merge-state cache" first. It owns the
independent stale-cache cause, and ancestry is authoritative on its own: if the
base is already an ancestor of the head there is no merge to compute and no
driver question to ask.

Fetch the PR head explicitly. `git fetch origin main` gets the base but not an
open PR head. Verified against open PR #3707: after `git fetch origin main` the
head object was absent, and present only after fetching the pull ref.

```bash
set -uo pipefail
PR=3636
BASE=$(gh pr view "$PR" --json baseRefOid -q .baseRefOid)
HEAD=$(gh pr view "$PR" --json headRefOid -q .headRefOid)
git fetch -q origin main "pull/$PR/head"
git cat-file -e "$BASE^{commit}" && git cat-file -e "$HEAD^{commit}"
```

Step 1, ancestry. Terminal when it hits.

```bash
if git merge-base --is-ancestor "$BASE" "$HEAD"; then
  echo "base is an ancestor: stale cache, see autonomous-pr-monitor.md"
  exit 0
fi
```

Step 2, the effective merge attribute on each changed path, as of the PR head.
Use NUL delimiters: with newline delimiters, `xargs` treats quotes and spaces as
special, drops the offending path, and exits 1. Verified on a file named
`single'quote.md`, which the newline form skipped while reporting
`xargs: unmatched single quote`.

```bash
git diff --name-only -z "$BASE...$HEAD" \
  | xargs -0 -r git check-attr --source="$HEAD" merge -- \
  | tee /tmp/attrs.txt
grep -c ': unspecified$' /tmp/attrs.txt   # these are NOT automatically safe
git config --get merge.default            # a value here drives every unspecified path
```

Step 3, check **every** distinct non built-in value from step 2, not just the
first. A built-in (`text`, `binary`, `union`) needs no definition; anything else
does.

```bash
sed 's/.*: merge: //' /tmp/attrs.txt | sort -u \
  | grep -Ev '^(text|binary|union|unspecified|set|unset)$' \
  | while read -r name; do
      git config --show-origin --get "merge.$name.driver" \
        || echo "NO DEFINITION: $name falls back to a text merge"
    done
```

Step 3 is the one people skip. Without it, step 2 produces a confident wrong
answer. A definition found here still only proves selection is possible. To prove
the command ran, merge locally under `GIT_TRACE=1` and look for a `run_command:`
line naming the driver.

## Controls that lie

**The `merge-tree` control resolves attributes from your checkout, not from the
commits you pass it.** Verified: with the attribute present in `HEAD`, a merge of
two commits invoked the driver and exited 0; after moving `HEAD` to a commit
without the attribute, the same two commit arguments produced no invocation and
exited 1. Run it from a detached worktree at the PR head, or you are measuring
your own checkout.

**The driver-disabling control manufactures its own positive result.**

```bash
set +e
git merge-tree --write-tree "$HEAD" "$BASE" >/dev/null; on=$?
git -c "merge.$name.driver=false" \
    merge-tree --write-tree "$HEAD" "$BASE" >/dev/null; off=$?
set -e
echo "on: $on  off: $off"
```

Note `set +e`. Under `set -e` the failing case exits the script before the second
status is ever captured, verified: the snippet prints only the first line and
exits 1.

On a name that was **never configured**, this prints `on: 0` and `off: 1`, the
exact signature usually read as proof the driver is the cause. What `-c` did was
install a driver that always fails. Differing results show only that merge
configuration affects this merge. Equal results are inconclusive, because an
installed driver may decline. Neither substitutes for step 3 plus a trace.

**A wrong file count is not evidence of a merge problem.** GitHub pins the base
it compares against, and that pin can lag the base branch. Verified on PR #3647:
the API reported 316 changed files against a real diff of 5, all the extras
being base-branch work attributed to the branch. This looks alarming mid-triage
and means nothing about drivers. Trust `git diff --stat "origin/$BASE...HEAD"`,
and note that it clears on a different trigger than stale mergeability does. See
`docs/autonomous-pr-monitor.md` for both triggers.

**The two-dot form invents deletions, and the count scales with how far behind
you are.** Note the three dots above. `origin/main..HEAD` compares the current
tip of main against your head, so every commit that landed on main since you
branched reads as content your branch removed. `origin/main...HEAD` compares the
merge base instead, which is what GitHub shows.

Verified 2026-08-02 on branch `docs/testing-discriminating-input`, 7 behind and 2
ahead, whose real change adds three lines and deletes nothing:

| form | result |
|---|---|
| `git diff --shortstat origin/main..HEAD` | 62 files, 207 insertions, **4978 deletions** |
| `git diff --shortstat origin/main...HEAD` | 4 files, 118 insertions, 0 deletions |
| `git diff --shortstat $(git merge-base HEAD origin/main) HEAD` | 4 files, 118 insertions, 0 deletions |

The failure mode is not a wrong number, it is a wrong decision. Four thousand
deletions on a three-line change reads as an accidental mass revert, and the
reflex is to reset or re-branch, which discards real work to fix an artifact of
the diff command. Check `git rev-list --left-right --count origin/main...HEAD`
first: a non-zero left number means the two-dot form will lie, and by roughly
that much.

## Resolution

Only for the local-clean, server-conflicting direction. Merge `origin/main` into
the branch locally and push the merge commit, so GitHub sees a result it does not
have to compute.

```bash
git fetch origin main && git merge origin/main --no-edit && git push
```

**This expires.** It fixes one base SHA. The next commit on `main` touching the
same path returns the PR to `CONFLICTING`. Observed once on PR #3636, which
returned to `CONFLICTING` within the hour. That observation is from the live PR
and is not reproducible from this memory, because `refs/pull/3636/merge` no
longer exists.

The reverse direction, local conflict with a clean server merge, has no such fix.
The local merge cannot complete, so there is nothing to push. Resolve by hand or
fix the driver.

Two wrong turns: `git rebase origin/main` needs a force push, prohibited here.
`git checkout origin/main -- <path>` discards everything the branch contributed
to that path, which is the worst option for a path a driver exists to combine.

## Verifying the merge kept the data

Line and record counts prove nothing when the driver is not a pure union. A
driver honouring deletions can land below either parent, and a result above both
parents can still be missing records. Compare identity keys per collection
against each parent. Comparing serialized records reports a false drop for every
record the driver legitimately rewrote.

When reading a driver script, `%A` is the current side of the merge in progress,
not inherently `main`. A driver hardcoding that assumption is wrong on half its
invocations.

## Related

- `git-merge-driver-declared-versus-running.md`. Prove the driver runs first.
- `docs/autonomous-pr-monitor.md`, "Stale merge-state cache". The other cause.
- Issue #3644, closed with the causal graph that surfaced this.
- Issue #3693. The stale-cache refresh cannot clear a no-op merge.
