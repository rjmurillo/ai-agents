# Count Ratchet Commands and Their Scope

The count ratchets block a push when a tracked count rises. Running them by hand
before pushing saves a ten minute round trip, because the pre-push hook runs the
full test suite first and only then reports the ratchet failure.

## Where they actually live

They are under `scripts/ci/`, not `scripts/validation/`. Guessing the latter
produces `Errno 2`, which is easy to misread as "no such check exists."

```bash
uv run --frozen --extra dev python scripts/ci/ruff_ratchet.py
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main
```

Canonical source for these invocations is `lefthook.yml` under the pre-push
group. Read it there rather than trusting any copy, including this one.

Note `ruff_ratchet.py` takes no `--base-ref`; the other three do. The underlying
`taste_lints.py` also rejects `--base-ref`. Only the `*_count_ratchet.py`
wrappers accept it.

## The scope trap

**A ratchet run without `--base-ref origin/main` is a different check.**
Standalone, it compares against the baseline file in the working tree. With the
flag, it additionally rejects a baseline that has been *raised* relative to the
ref. A change that lifts the baseline to accommodate new debt passes the first
form and fails the second, which is the form the hook runs.

Always pass `--base-ref origin/main` when the question is "will this push
succeed."

**A tracked-file ratchet cannot see a new file until you `git add` it.** Run
`git add -A` before the ratchet, or a newly created file contributes zero and
the local run disagrees with the hook.

## Reading a failure

The taste ratchet reports only the delta, for example
`602 violations > baseline 601 (+1)`. To find which file moved, run the linter
directly on the files you changed:

```bash
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py <files>
```

The script is inside the skill, not in `scripts/`. File size is the usual
culprit: an ERROR fires above 500 lines, a WARNING at 400. Exactly 500 passes.
Adding a handful of tests to an existing 470 line test file is enough to trip
it, and the fix is a split along a seam that already exists rather than a
suppression.
