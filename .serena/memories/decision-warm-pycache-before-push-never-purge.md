# Warm `__pycache__` before pushing, never purge it

## Question

A pre-push run fails inside `build-all-check` or `python-tests` with an import
or stale-bytecode symptom. The reflex is to delete `__pycache__` and retry. Is
that right?

## Conventional answer

Purge `__pycache__` when bytecode looks stale. This is standard Python advice
and it is correct for a single-process run.

## First-principles position

It is wrong here, and it is actively harmful. `lefthook.yml` defines a
`parallel: true` group (line 339 at the time of measurement) whose jobs include
`python-tests` (line 351) and `build-all-check` (line 410). Both run
concurrently against the same working tree. With a cold cache, both processes
race to write the same `.pyc` files, and one reads a partially written entry.

Purging guarantees the cold-cache state that causes the race. Warming
guarantees it cannot happen, because every `.pyc` already exists and is valid
before either job starts.

## Evidence

The failure only ever reproduced after a purge, and never after a warm. The
two job names and the `parallel: true` marker are readable directly in
`lefthook.yml`; confirm the line numbers before citing them, since the file
moves.

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
