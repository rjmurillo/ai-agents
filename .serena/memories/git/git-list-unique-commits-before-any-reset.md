# Skill: List a branch's unique commits before any `git reset --hard` (90%)

## Statement

Before running `git reset --hard <remote>` on a shared branch, list what the
reset would discard:

```bash
git log --oneline --no-merges "<remote>/<branch>..HEAD" --not origin/main
```

Any commit surviving that filter is authored work that exists nowhere else.
Merge commits and commits inherited from `main` are noise; `--no-merges` and
`--not origin/main` remove both, so a non-empty result is signal, not volume.

## The instinct that is wrong here

`git merge --ff-only FETCH_HEAD` printing `Already up to date.` reads like
"local and remote agree." It does not mean that. It means the remote tip is an
ancestor of local HEAD, which is exactly what being **ahead** looks like. The
message is identical whether you are level with the remote or carrying unpushed
commits on top of it.

So the natural next move, "the merge was a no-op, I will reset to the remote and
start clean," destroys precisely the commits the message failed to mention.

## Evidence

Measured 2026-08-04 on `fix/gate-enforcement-clean` in a worktree created for
PR #4426.

```text
$ git merge --ff-only FETCH_HEAD
Already up to date.
$ git ls-remote origin fix/gate-enforcement-clean | cut -f1
f0aa33011...
$ git rev-parse HEAD
<differs from f0aa33011>
```

The differing SHAs are what prompted the check. The filter returned exactly one
commit:

```text
79314576b  fix(tests): make the plugin-instructions guard fail on a missing dir
```

It was unpushed, authored by another agent, and it was the same fix I was about
to write from scratch. A `git reset --hard origin/...` at that moment would have
deleted it with no warning and no reflog entry anyone would think to search,
because the reset would have looked like a clean sync.

Recovery used: `git branch backup/4426-merge` to pin the state, reset, then
`git cherry-pick 79314576b`.

## Why the count is not enough

`git rev-list --count <remote>..HEAD` returning a non-zero number is a weaker
signal, because a routine `git merge origin/main` inflates it with dozens of
main-derived commits and one merge commit. Reviewers learn to ignore a number
that is usually large for boring reasons. The filtered `git log` is short by
construction: on a synced branch it prints nothing at all, so anything it prints
demands attention.

## Scope

Applies to `git reset --hard`, `git checkout -B`, `git branch -f`, and any
worktree teardown that discards a branch tip. It applies with more force in a
multi-agent repository, where "my worktree" and "my commits" are not the same
set: another agent may have pushed nothing yet and left work only on disk.

Related: `git/git-empty-hook-run-means-an-empty-push.md` (the mirror-image
failure, where the local report says work moved and the remote disagrees).
