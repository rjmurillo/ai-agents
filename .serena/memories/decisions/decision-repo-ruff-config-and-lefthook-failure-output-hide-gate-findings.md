# Repo ruff config and lefthook failure only output hid gate findings

**Atomicity**: 90%
**Category**: Gate design, linter wrappers
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E037. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a gate that wraps ruff and runs under lefthook hide findings or warnings from the operator?

## Conventional answer

The docstring named only two exceptions: arguments prefixed with `_` and findings in the baseline. A comment and the PR body implied operators see "baseline growth NOT CHECKED".

## First-principles position

Both claims were false in fixtures. The repo ruff config (per-file-ignores and extend-exclude) hid new findings. Lefthook with output set to failure dropped the stdout of a passing job, so the warning never appeared.

## Evidence with limits

- Fixtures dated 2026-11-05: per-file-ignores or extend-exclude gave exit 0 with "Scanned 2 Python file(s); 1 finding(s)", while the control exited 1.
- A lefthook 2.2.2 fixture with output set to failure dropped a passing job's stdout.
- Running Ruff with `--isolated` gave the same 82 findings (2026-11-05).
- Limits: The fixtures used Lefthook 2.2.2 and one Ruff version. The sweep did not check whether the warning now appears during passing runs.
- State on main at 1be533c496 (2026-11-26): fixed for Ruff isolation. `scripts/validation/check_unused_arguments.py:4` describes `--isolated`, and `tests/validation/test_check_unused_arguments_isolation.py` covers it. `lefthook.yml:6` documents failure only output.

## Decision

For the unused-argument gate, pass `--isolated` to Ruff and keep one fixture per config path that could hide a finding. The fixtures cover that one Ruff wrapper, not every linter wrapper. Under failure only Lefthook output, a warning on the stdout of a passing job does not appear.

## Related

- `.serena/memories/linting/ruff-mypy-cleanup-gate-coupling.md`
- `.serena/memories/decision-lefthook-no-finally-cleanup.md`
