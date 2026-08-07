# `git stash push -m` after `--` is parsed as a pathspec

`git stash push -- <path> -m <message>` does not stash anything. Everything
after `--` is a pathspec, so git looks for files literally named `-m` and
`<message>`, finds neither, and exits non-zero without creating a stash.

The flag order is not stylistic. `-m` has to come before `--`.

```bash
# correct
git stash push -m scopetests -- tests/test_thing.py

# silently saves nothing
git stash push -- tests/test_thing.py -m scopetests
```

## What it actually prints

```
error: pathspec ':(,prefix:0)-m' did not match any file(s) known to git
error: pathspec ':(,prefix:0)scopetests' did not match any file(s) known to git
Did you forget to 'git add'?
```

Reproduced 2026-08-07 in this repo. The `:(,prefix:0)` wrapper is git echoing
its own pathspec normalization, which is why the message does not read like a
flag-order complaint.

## Why it destroys work

The failure is loud only if you are watching. Three things hide it:

1. The stash command is usually one link in a chain, and a following
   `git checkout <path>` runs regardless.
2. `2>/dev/null` on the stash call hides both error lines.
3. `git stash list` afterwards still shows entries, from older stashes on
   other branches, because the stash stack is shared across every worktree
   (see `git-stash-is-shared-across-every-worktree`). A non-empty list reads
   as success.

Measured cost this session: 302 lines of new tests written, stashed with the
wrong flag order, then discarded by the `git checkout` on the next line. The
work was recoverable only because the text still existed in the conversation.

## The check that catches it

Compare the stash top before and after. A successful `stash push` always
changes it.

```bash
before=$(git rev-parse --quiet --verify refs/stash || echo none)
git stash push -m "$MSG" -- "$@" || echo "stash failed"
after=$(git rev-parse --quiet --verify refs/stash || echo none)
[ "$before" = "$after" ] && echo "NOTHING WAS STASHED, do not checkout" && exit 1
```

`git stash list | head -1` is not a substitute. It matches an older stash from
another worktree just as readily.

## The rule

Never pair a stash with a destructive follow-up in one chain. Verify the stash
landed first, by ref, then destroy. If a stash is only a backup, prefer `cp` to
a path outside the tree: it has no flag-order trap and no shared stack.

## Related

- `git-stash-is-shared-across-every-worktree`, why `git stash list` is not
  evidence your own stash exists.
