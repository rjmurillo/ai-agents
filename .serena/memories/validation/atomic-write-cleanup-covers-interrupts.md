# Skill: Atomic Write Cleanup Must Cover Interrupts and Flush Before Rename

## Statement

A temporary-file-plus-`os.replace` write must clean up after interrupts and
flush the temporary before the rename.

## Trigger

Any `tempfile.mkstemp` plus `os.replace` write, and any review of one.

## Action

1. Attach the temporary cleanup to `except BaseException`, not `except OSError`.
2. `handle.flush()` then `os.fsync(handle.fileno())` before `os.replace`. This
   flushes the payload but does not make the directory entry crash-durable.
3. Pass `prefix=f".{path.name}."` to `mkstemp` so a leaked temporary names the
   file it failed to replace.
4. Close before unlinking, because Windows cannot unlink an open file.
5. Preserve cleanup failures beside the primary error. For interrupts, report
   cleanup failures before re-raising the interrupt.

## Evidence

`_atomic_write_text` in `scripts/validation/merge_causal_graph.py` (deleted by ADR-088; reachable in git history) landed in
PR #3359 with cleanup attached to `except OSError`. Probe against `3d1f3b30d2`,
forcing a `BaseException` out of the write:

```
main leaks on BaseException: ['tmpzh8km2lu.tmp']
destination intact: {"a":1}
```

The destination survived; the temporary did not get removed, and `mkstemp`'s
default name carried no link to what wrote it. A merge driver runs inside an
interactive `git merge`, so `KeyboardInterrupt` is the realistic failure, not
`ENOSPC`. Fixed in #3368.

`mem:validation/atomic-replace-preserve-metadata` already listed "temporary
cleanup" as a required test for exactly this pattern; #3359 shipped without it,
which is how the gap survived review.

## Failure Mode

Tests that only assert the destination is intact pass while the temporary leaks.
The leak lands in a tracked directory and is one `git add -A` from being
committed, under a name nobody can attribute.

## Category

validation
