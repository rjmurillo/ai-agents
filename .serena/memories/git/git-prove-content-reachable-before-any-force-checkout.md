# Skill: Prove working tree content is reachable before any `git checkout -f` (90%)

## Statement

Before discarding a dirty working tree, prove each file's content is reachable
from a ref. Presence in the object database is not the same claim and does not
support the deletion.

```bash
git rev-list --objects origin/main | awk '{print $1}' | sort -u > reachable.txt
git hash-object <file>                   # membership in reachable.txt is the proof
```

`git ls-tree -r origin/main` is the wrong set. It reads the tip tree only, so a
file matching an older committed revision reads as unreachable, and its third
column carries gitlink commit OIDs for submodules. `git rev-list origin/main --
<path>` proves nothing at all here: it lists commits that touched the path and
never looks at your content.

This is the working tree counterpart to
`git/git-list-unique-commits-before-any-reset.md`. That one protects commits at
the moment of a destructive reset. This one protects uncommitted file content at
the same moment. A checkout that is safe for every commit can still be
unrecoverable for the files.

## The instinct that is wrong here

The natural probe for "does git already have this content" is `git hash-object
<file>` followed by `git cat-file -e <oid>`. Exit 0 reads as "git has it, so
deleting the file loses nothing."

`cat-file -e` does not say that. It answers from the object database alone and
reports nothing about reachability. A blob written by `git add` and then
abandoned, by a reset, an amended commit, or a dropped stash, still exists and
still exits 0 while no ref reaches it. Discard the working tree copy and the
only surviving witness is an unreferenced object, which a default `git gc` keeps
for two weeks (`gc.pruneExpire`, default `2.weeks.ago`) and then removes.

The untracked side carries the mirror of this error. A file `git status` reports
as untracked, whose **path** is tracked in the target ref, is not thereby safe.
Path membership is not content membership. `git checkout -f` overwrites it with
the ref's version, reporting only the branch switch and never the file, and
because the content was never staged no blob of it was written. Unless that
exact content is reachable through some other path, it leaves no trace and,
unlike the commit case, there is nothing to recover afterward.

## Evidence

Measured 2026-08-05 on the main clone, detached at `48c520ee9` and 361 commits
behind `origin/main`, carrying 333 modified files and 219 untracked entries.
Those 219 entries expand to 233 files, because `git status` collapses a wholly
untracked directory into a single line and the per file question needs the
expansion.

The blob probe classified 333 of 333 modified files as already known to git and
0 as novel. That result was correct in outcome but weaker than the reasoning it
was asked to carry: it proved the objects existed, not that any ref reached
them. Only 131 files were proven reachable, by matching `origin/main` byte for
byte. The other 202 rested on object presence plus timing. A further 20 of those
had been counted as traced through `git rev-list origin/main -- <path>`, which
proves nothing, so they fold back into the unproven set.

Timing corroborates; it does not prove. No file carried an mtime later than
2026-08-03, the bulk shared `17:55:38.977` to the millisecond, which is one git
operation rather than authoring, and `git reflog` recorded nothing between
2026-07-29 03:51 and the cleanup, so `HEAD` never moved in the window. The 18
paths absent from `origin/main` carry scattered mtimes across 2026-07-27, 07-30,
07-31, and 08-05, the signature of a person at a keyboard, and none sits in the
mass write. Their content was never checked either, so "absent path" is what was
measured and "novel file" is what was inferred.

The same limit binds the untracked set: 215 of 233 matched a tracked path and
were overwritten with no content check. Record the residual gap at full size.
202 modified and 215 untracked files were argued, not measured, and after a
force checkout the question is no longer answerable. The correct probe was cheap
and available, and skipping it converted a provable claim into an argued one.

## Reconstructing the answer after the fact

Lead with the mechanism. `git checkout -f` reads trees and writes files; it
never hashes working tree content, and plain `git hash-object` without `-w`
writes nothing. So absent a hook, no object can be attributed to a force
checkout, and a reviewer citing `git fsck` output as evidence that one destroyed
work has mistaken the resting state of the object database for a symptom. The
exception is real and easy to miss: `post-checkout` runs on every checkout, and
a hook that writes objects makes checkout create them. Clear `core.hooksPath`
and the hooks directory before leaning on this.

Object timing corroborates, and three traps limit it:

```bash
git fsck --no-reflogs --unreachable --connectivity-only | grep '^unreachable blob'
stat -c '%y' "$(git rev-parse --git-path objects)"/<xx>/<rest>
```

Ask for `--unreachable`, not `dangling`. A dangling blob is an unreachable tip;
a blob held by an unreachable tree or commit, which is exactly the amended
commit and dropped stash case, appears only under `--unreachable`. On this
repository the two differ by 44 against 9181.

Do not treat packed as old. `git fetch` writes a pack once a transfer exceeds
`transfer.unpackLimit` (default 100 objects), with no `gc` or `repack` involved,
and rewriting an existing object freshens mtimes. A packed object also has no
individual path to stat, so it drops out of the mtime sweep entirely.

Do not hardcode `.git/objects`. In a linked worktree `.git` is a file and that
directory does not exist, so the sweep silently finds nothing; `git rev-parse
--git-path objects` resolves to the shared one.

Read any resulting count with care rather than as a finding. Worktrees share one
object database, and this repository carries more than 350 registered worktrees
and 45 stashes, so unreachable blobs from unrelated work are its resting state.
Neither the 9181 nor the 44 says anything on its own. What settled the question
was attribution: every loose object written after the cleanup timestamp traced
to later session work, and the hooks directory was empty.

## Scope

Applies to the forcing forms: `git checkout -f`, `git reset --hard`, `git
restore --source`, `git clean -f`, and `git worktree remove --force`. Each
overwrites or deletes working tree files without a prompt. Plain `git checkout
-B` is not one of them, because it carries modifications forward, and plain `git
clean` refuses outright since `clean.requireForce` defaults to true. The flag is
what removes the prompt.

It binds hardest on a stale checkout, where the volume is large enough that
nobody reads the list and every entry looks like noise. That is the case where
one novel file hides best.

## Related

- `git/git-list-unique-commits-before-any-reset.md`: the commit side of this
  same moment. Run both before any destructive sync.
- `git/git-stale-detached-clone-runs-stale-tooling.md`: the state that produces
  this situation. Its recovery steps assume `git status --porcelain` is empty
  and stop short of the dirty case this memory covers.
- `git/git-absence-and-case-in-plumbing.md`: five more git plumbing commands
  that answer wrongly rather than failing. Section 1 states the general shape,
  that an answer meaning "nothing here" needs a reason it could not have been
  produced by failure or by deletion.
