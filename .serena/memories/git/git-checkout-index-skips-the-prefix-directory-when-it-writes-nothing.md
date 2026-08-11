# checkout-index creates its prefix directory only when it writes a file

`git checkout-index -a --prefix=DIR/` creates `DIR` as a side effect of writing
into it. When it writes nothing it exits 0 and `DIR` does not exist.

That combination is worse than it sounds, because the two cases where it writes
nothing are exactly the two cases where a caller most needs the fallback:

- **Unmerged stages.** A conflicted index holds stages 1, 2, and 3 and no stage
  0. `checkout-index -a` skips every one, exits 0, and reports nothing.
- **Gitlink (`160000`).** Exports as an empty directory. The recorded commit is
  absent.

So a recovery chain shaped like

```bash
GIT_INDEX_FILE=... git checkout-index -a --prefix=DIR/ && cp "$INDEX" DIR/index
```

fails at the `cp` with `No such file or directory` in precisely the situations
the `cp` was added to handle. Prepend `mkdir -p DIR &&`.

Also pass `git -C <repo>`: `checkout-index` needs a repository, and a reader
pasting a recovery command is often not standing in one.

## The test trap that hid this

A pytest test substituted `tmp_path` for the `DIR` placeholder. `tmp_path`
already exists, because the fixture creates it. The fixture supplied the
precondition the command was supposed to establish, so the test passed against
a command that could not work.

Substitute a path that does not exist yet, and assert that it does not exist
before running. `command_of` in `tests/gc_real_git.py` enforces this.
