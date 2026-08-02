# Git Plumbing: Proving Absence and Resolving Case

Two git behaviors that contradict the idioms most code reaches for. Both were
found by probing rather than reading docs, and both silently produced a wrong
answer instead of an error. Measured on git 2.x, Linux, 2026-08-01, while
hardening the portability ratchets (PR #4233).

## 1. `rev-parse --verify --quiet HEAD` cannot prove a repository is unborn

The idiom for "does this repository have any commits" is
`git rev-parse --verify --quiet HEAD`, treating a non-zero exit as "no commits."
That reading is wrong. Two very different states produce the identical result.

| State | `rev-parse --verify --quiet HEAD` | `rev-list --all --max-count=1` | `for-each-ref --count=1` |
|-------|-----------------------------------|--------------------------------|--------------------------|
| Fresh `git init`, genuinely unborn | rc=1, empty | rc=0, empty | rc=0, empty |
| `.git/HEAD` contains garbage | rc=128, empty | rc=128 | rc=128 |
| `HEAD` names a deleted branch | **rc=1, empty** | rc=0, **non-empty** | rc=0, **non-empty** |

Row 1 and row 3 are byte-identical on the first probe. Anyone can produce row 3
with one line: `echo 'ref: refs/heads/nope' > .git/HEAD`. History is fully
intact; only the pointer is broken.

This matters wherever "no commits exist" grants permission. In the ratchets it
meant the committed floor read as absent, so the working tree copy became the
only witness, and that copy is exactly what a run asking for a lower number
rewrites first.

**Use `git for-each-ref --format=%(objectname) --count=1`.** Both `rev-list
--all` and `for-each-ref` discriminate all three states. Prefer `for-each-ref`
because it *answers* on a genuinely fresh repository (rc=0, empty output) rather
than failing. Absence should be proven by the tool answering, never inferred
from the tool failing, or a broken tool reads as an empty world.

Note that a garbage `.git/HEAD` is already caught earlier by `git rev-parse
--git-dir`, which fails outright in that state. Only the deleted-branch case
needs the stronger probe.

### `for-each-ref` empty is still not proof of an unborn repository

The table above is incomplete, and the missing row was found the same day. Delete
every ref, not just the one `HEAD` names, and `for-each-ref` returns rc=0 with
empty output: identical to row 1. The commits are untouched; they sit in the
object database and stay reachable through pseudorefs such as `ORIG_HEAD`,
`refs/stash`, and the reflog.

| State | `for-each-ref --count=1` | `cat-file --batch-all-objects` |
|-------|--------------------------|--------------------------------|
| Fresh `git init`, genuinely unborn | rc=0, empty | no commit objects |
| Every ref deleted, history intact | rc=0, **empty** | **commit objects present** |

So a guard that grants permission on "no commits exist" needs the object database
as the final witness:

```
git cat-file --batch-check='%(objecttype)' --batch-all-objects
```

If any line reads `commit`, the repository has history and the empty ref list is
damage, not a fresh start. This walks every object, so gate it: only reach for it
when `HEAD` will not resolve *and* no ref survives, a combination no healthy
repository reaches.

The general shape: a tool that answers can still lie. An answer shaped like
"nothing here" needs a reason it could not have been produced by failure or by
deletion.

## 2. `ls-tree` pathspecs match case-sensitively

`git ls-tree -z HEAD -- some/dir/` matches the pathspec case-sensitively, even
on a case-insensitive filesystem, and even if your own comparison of the final
filename is case-folded. A lookup written as "pathspec for the parent, folded
compare for the leaf" is running two different rules on two halves of one path.

Consequence: a parent spelled `Scripts` instead of `scripts` lists nothing.
Nothing reads as "git does not track this," while the filesystem underneath
happily opens the real file. Windows CI runs on such a filesystem.

**Walk the tree one component at a time.** `git ls-tree <tree-oid>` at each
level puts both halves under the same rule. It costs O(depth) cheap git calls,
which is nothing next to a wrong answer.

Second trap in the same code: when folding case, do not decide on the first
match. Git sorts `B.json` before `b.json`, so an exact request for `b.json`
hits the twin first. Collect every folded candidate, then prefer the exact one.
A git tree cannot hold duplicate names, so at most one exact match exists.

## 3. `ls-tree` applies the current-directory prefix to *any* tree-ish

`git -C sub ls-tree <tree-oid>` does not list that tree. It lists the part of it
under `sub/`. Descending a tree by OID therefore re-applies a prefix that the
subtree does not contain, prints nothing, and **exits 0**. A walk reads the empty
output as "this directory is empty" and concludes the file was never committed.

The fix is two changes that only work together:

- pass `--full-tree`, and
- resolve the relative path against `git rev-parse --show-toplevel`, not against
  whatever root the caller handed in.

`--full-tree` alone breaks the top-level case, because the path is still being
made relative to the wrong base. Change one without the other and a passing test
suite hides the regression.

Related: **git never stores an empty subtree.** Only the root tree of an empty
commit can honestly be empty. So an empty listing for a subtree OID is by
definition a lookup that failed, and treating it as one converts a silent loss
into a refusal.

## 4. `refs/replace` is honored by default and leaves no diff

`git replace <real> <forged>` makes every later command serve the forged object
when asked for the real id. The ref lives in `.git/refs/replace/`, is not pushed
by default, and never appears in a diff or a review.

Scrubbing `GIT_*` from the environment does not help. It makes things worse: the
only relevant variable is `GIT_NO_REPLACE_OBJECTS=1`, which *disables*
replacement, so removing it re-enables the substitution. Pass the flag on the
command line instead:

```
git --no-replace-objects -C <root> ...
```

## 5. A committed symlink is a blob whose content is the target path

`kind == "blob"` does not mean "regular file". Git stores a symlink as a blob
holding the text of its target; the discriminator is the mode, `120000` versus
`100644` / `100755`. Read a committed symlink as a file and you parse a pathname
as content while every other reader follows the link to something else. That is
the same "check one path, return another" split as `security-015`.

## 6. Tree names and argv paths are decoded differently

`stdout.decode("utf-8", "replace")` maps an invalid byte to U+FFFD. Python's argv
carries the same byte as a surrogate escape. So a committed `baseline-\xff.json`
becomes `'baseline-\ufffd.json'` from the tree and `'baseline-\udcff.json'` from
the path, and the two never compare equal: the file reads as untracked.

Split `ls-tree -z` output as **bytes** (`stdout.split(b"\0")`) and decode names
with `os.fsdecode`, which produces the same surrogate escapes as argv.

## Related

- `scripts/validation/portability_git.py`: `run_git`, `tree_entries`,
  `tracked_blob`, `committed_blob`, `_no_commits_or_refuse`
- `scripts/validation/portability_floor.py`: `read_previous_sections`
- `tests/validation/test_portability_git_lookup.py`: every behavior above pinned
  with its own control, each mutation-verified
- `tests/validation/test_portability_floor_lookup.py`: the JSON-side floor rules
