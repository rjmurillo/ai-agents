# A line-swap mutation reuses stale bytecode, so a mutation harness must purge `__pycache__` between mutants

## Question

A mutation harness rewrites a source file, runs the test suite, restores the
file from a backup, and moves to the next mutant. Is the restore enough to
guarantee the next run grades the restored code?

## Conventional answer

Yes. The file is byte-identical to the baseline after the restore, and CPython
recompiles a module whenever its source changes. Nothing else is needed.

## First-principles position

No. CPython's default `.pyc` invalidation compares two things recorded in the
`.pyc` header against the source file: the source's **mtime in whole seconds**
and its **size in bytes**. It does not hash the content.

A mutation that swaps or reorders whole lines leaves the file size **exactly
unchanged**. If the restore lands in the same wall-clock second as the mutated
compile, both fields match and CPython reuses the **mutated** bytecode. The
next test run grades code that is not on disk.

The failure is silent and it lies in the confusing direction: the source looks
clean, `cmp` against the backup passes, `git diff` is empty, and the tests fail
anyway. The natural reading is that the production change is broken.

## Evidence

Observed 2026-08-02 while mutation-proving the `pre_pr_sequence` registry
guard for issue #4285.

1. A parity harness confirmed the rewritten module emitted a gate order
   byte-identical to `origin/main`.
2. A negative-control mutation swapped two adjacent `_Gate(...)` lines. The
   harness caught it. The file was then restored and `cmp -s` against the
   backup reported identical.
3. The very next pytest invocation failed with
   `assert 'Nested Test Detection' == 'Count Ratchets'`, the exact symptom of
   the swap that had just been reverted.
4. `find . -name __pycache__ -type d -exec rm -rf {} +` followed by the same
   pytest invocation: 2 passed.

The swap changed no bytes of total length, and the mutate-test-restore cycle
completed inside one second.

## Decision

In any mutation harness, purge `__pycache__` after writing each mutant and
again after the final restore:

```python
subprocess.run(["find", str(ROOT), "-name", "__pycache__", "-type", "d",
                "-exec", "rm", "-rf", "{}", "+"], capture_output=True)
```

Do not rely on `cmp -s` alone. It proves the source was restored; it says
nothing about which bytecode the interpreter will load.

## Boundary against the opposite rule

`decision-warm-pycache-before-push-never-purge.md` says never purge
`__pycache__` and warm it instead. That rule is correct and this one does not
overturn it. The two apply to different situations, and the discriminator is
concurrency:

| Situation | Rule | Why |
|---|---|---|
| `pre-push` lefthook, `parallel: true` group, several jobs sharing one tree | warm, never purge | a cold cache lets two processes race to write the same `.pyc` |
| mutation harness, one process, source rewritten repeatedly in place | purge between mutants | same-second, same-size rewrites defeat mtime and size invalidation |

Read the rule as: purge when a single process rewrites source faster than the
clock resolves, warm when several processes share a tree.
