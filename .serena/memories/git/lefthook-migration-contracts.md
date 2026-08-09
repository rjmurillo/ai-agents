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


## 2026-08-06 Performance Findings

- Lefthook 2.1.10 delivered identical 362604-byte pre-push stdin to three `use_stdin: true` jobs in a `piped: true` group across 5 of 5 runs. The same jobs under `parallel: true` corrupted delivery in 10 of 10 runs. Keep stdin consumers piped unless one producer captures immutable push-scoped input for all consumers.
- Function-scoped autouse fixture cost must be multiplied by the collected test count. The root HEAD guard paid two Git subprocesses per test across more than 23000 tests. Direct loose-ref reads preserve per-test attribution and use Git fallback for packed refs or unproven state.
- Main-suite statement coverage measured 438.91 seconds. Branch coverage measured 465.93 seconds and failed on mixed child-process coverage data. Keep the main partition statement-only; collect branch coverage only in the small pin partitions and project their lines before combining.

Evidence: issue #4710 and `.agents/sessions/2026-08-06-session-10003-profile-optimize-pre-submit-pre-commit-pre-push.json`.
