# Warm `__pycache__` before pushing, never purge it

## Question

A pre-push run fails inside `build-all-check` or `python-tests` with an import
or stale-bytecode symptom. The reflex is to delete `__pycache__` and retry. Is
that right?

## Conventional answer

Purge `__pycache__` when bytecode looks stale. This is standard Python advice
and it is correct for a single-process run.

## First-principles position

It is wrong here, and it is actively harmful. `lefthook.yml` runs its `pre-push`
stage through a `parallel: true` group whose jobs include `python-tests` and
`build-all-check`. Both run concurrently against the same working tree. With a
cold cache, both processes race to write the same `.pyc` files, and one reads a
partially written entry.

Purging guarantees the cold-cache state that causes the race. Warming
guarantees it cannot happen, because every `.pyc` already exists and is valid
before either job starts.

## Evidence

The failure only ever reproduced after a purge, and never after a warm. To
re-derive the two job names and the group marker, grep `lefthook.yml` for
`parallel: true`, `python-tests`, and `build-all-check`; all three sit under the
`pre-push` key. Line numbers are omitted on purpose. The file moves often, and a
stale number reads as authority long after it stops pointing anywhere useful.

## Decision

Before any push, run:

```
uv run --frozen python -c "import compileall; compileall.compile_dir('scripts', quiet=1)"
```

Do not delete `__pycache__` as a remedy. If a push fails with a stale-bytecode
symptom, warm the cache and retry rather than clearing it.

Note the second-order lesson: standard single-process advice inverts under a
parallel hook runner. Check whether a hook group is parallel before applying
any "clear the cache and retry" reflex.

## Boundary

This rule is about a shared tree under concurrent jobs. It does not apply to a
single-process mutation harness that rewrites one source file repeatedly. There
a purge is mandatory, because a line-swap mutation leaves file size unchanged
and a same-second restore defeats CPython's (mtime, size) invalidation. See
`ci/ci-line-swap-mutations-reuse-stale-bytecode.md`.

## Vendored fixture boundary

Vendored fixture builders must not copy runtime caches from the live tree.
Under pytest-xdist, another worker can remove a cache entry after `copytree`
enumerates it and before the copy opens it. The result is `shutil.Error` with
`Errno 2`, even though product files are stable.

Issue #4923 fixed both vendored review fixtures by routing copies through
`tests/lib/vendored_copy.py`, which excludes Python bytecode and test-tool
caches. This preserves warm-cache push behavior while removing caches from the
fixture input contract.
