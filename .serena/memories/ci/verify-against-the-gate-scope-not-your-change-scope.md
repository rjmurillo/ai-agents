# Verify against the gate's scope, not your change's scope

## The 18 minute mistake

I changed three files: two under `scripts/validation/` and one test file. I ran
mypy on the two source files, saw clean, and pushed. The pre-push hook ran mypy
across **all** changed files, found one error in the test file, and failed the
push after the 1007 second Python test job had already passed.

Cost: one full push cycle, roughly 18 minutes, plus the queueing wait.

The error was real and worth catching. The waste was entirely in checking a
narrower set than the gate checks.

## Rule

Before pushing, run each gate over the same file set the gate will use, which is
your whole diff, not the subset you think is interesting. Tests are changed files.
So are fixtures, workflow YAML, and markdown.

```bash
CHANGED=$(git diff --name-only origin/main...HEAD)
PY=$(echo "$CHANGED" | grep '\.py$' | tr '\n' ' ')
[ -n "$PY" ] && uv run --frozen --extra dev mypy $PY
[ -n "$PY" ] && uv run --frozen --extra dev ruff check $PY
```

The generalization is not about mypy. It is that a local pre-check whose scope is
chosen by you rather than derived from the diff will diverge from the gate at
exactly the moment it matters, and the divergence is invisible until the gate
runs. Derive the scope; do not pick it.

## Related tell

This failure looks nothing like the stale-branch signature. A stale branch fails
FOUR gates at once (python-lint-count-ratchet, taste-count-ratchet,
python-type-check, pre-pr-validation) and the named files have nothing to do with
your diff. A scope-mismatch failure fails exactly ONE gate and names a file you
actually changed. Read the boxing-glove job summary at the tail of the push log
and count the failures before you start diagnosing: one failure and four failures
have completely different causes.
