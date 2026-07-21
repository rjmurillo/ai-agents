# Lefthook Migration Contracts

As of branch `chore/lefthook-migration` on 2026-07-19, Lefthook 2.1.10 is the
repository's sole local Git hook manager.

## Authority

- `lefthook.yml` owns hook events, named jobs, filters, ordering, stdin, skips,
  and staging behavior.
- `scripts/validation/git_hook_policy.py` contains only Git object and index
  policies that Lefthook cannot express.
- No custom shell payload directory or SessionStart activation fallback exists.

## Installation

Human setup:

```bash
uv sync --frozen --extra dev
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

The native `--reset-hooks-path` option repairs old clones. Configuration changes
do not require another install.

## Runtime

- `commit-msg` receives the message path through `{1}`.
- Pre-push file jobs use Lefthook's native `{push_files}` selection.
- Raw pushed refs are parsed once by a sequential stdin group.
- Security scans read immutable blobs from pushed commits.
- Generator and staging jobs run sequentially. Failed generators cannot stage
  stale output.
- `SKIP_AUTOFIX=1` disables mutators but keeps check-only jobs active.

## Validation

Use `lefthook validate`, `lefthook check-install`, the behavioral integration
suite, `build/scripts/build_all.py --check`, and
`scripts/validation/pre_pr.py`.
