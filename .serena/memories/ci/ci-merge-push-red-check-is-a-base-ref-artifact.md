# A Red Required Check On A Merge Push Is Usually A Base-Ref Artifact

**Atomicity**: 95%
**Category**: CI
**Source**: 2026-08-04 fleet session, PR #4515 (issue #4553)

## Statement

`Run Python Tests` going red immediately after you push a `git merge
origin/main` resolution is, most of the time, not a real test failure. The
ruff ratchet inside that job diffs against `github.event.before` on push
events, which is the branch's **pre-merge head**, so every file the merge
carried in counts as a file your branch changed.

The remedy is to merge **current** `main` and push again. That fixes the
inherited violations and advances `github.event.before` to the old head, so
the next run's changed set is small. Re-running the failed job does not work:
`github.event.before` is fixed for that event.

## Context

`.github/workflows/pytest.yml` picks the base with:

```yaml
RUFF_RATCHET_BASE_REF: ${{ github.event.pull_request.base.sha || github.event.before || 'HEAD~1' }}
```

The workflow runs on both `push` and `pull_request`, so one head SHA produces
two rows named `Run Python Tests`. That name is a **required** context, and
GitHub ORs every row bearing a required name. The `pull_request` row uses the
real merge base and passes; the `push` row uses `event.before` and fails; the
rollup reports `FAILURE` and the PR will not merge.

Because step 9 fails, every later step is skipped, so pytest never runs. A
base-ref artifact suppresses the signal the check exists to provide.

## Evidence

PR #4515, head `09506b4cc`, a merge of `main` into the branch. Same SHA, same
workflow, same step number, only the trigger differs:

| job | trigger | base | step 9 |
|---|---|---|---|
| 91970285221 | `pull_request` | `base.sha` | success |
| 91969707666 | `push` | `event.before` = `eb00359e4` | failure |

```text
gh pr diff 4515 --name-only | grep -c '\.py$'   ->    0   real Python scope
job log                                          ->  311   "changed" Python files
```

It failed on `RUF100` in four test files the PR never touched. Those were real
in the `main` the branch merged (`5cc4a4f52`) and already fixed on current
`main`. Merging current `main` and simulating the next push's base confirmed
the fix before spending a push:

```bash
RUFF_RATCHET_BASE_REF=<current remote head> uv run --frozen python scripts/ci/ruff_ratchet.py
# Ruff ratchet passed for 53 changed Python file(s).
```

Run that locally before pushing. It costs seconds and tells you whether the
next push clears the row.

## The Detection Trap

Reducing `statusCheckRollup` to the latest row per context name reports this
PR **green**, because the `pull_request` row starts about 40 seconds after the
`push` row. Only `statusCheckRollup.state` shows `FAILURE`. A PR that looks
healthy but will not merge, with no red check visible, is this shape. Trust
the server's rollup over any local reduction.

## Related

- Issue #4553 tracks the fix.
- Issue #4544 is the same defect class in `detect_scope_explosion.py`: a local
  pre-commit hook counting merge-brought files, keyed on `MERGE_HEAD`. That
  one has a documented override; this one does not.
