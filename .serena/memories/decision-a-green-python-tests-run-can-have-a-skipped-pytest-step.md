# A green Python test run can have a skipped pytest step

**Atomicity**: 90%
**Category**: CI check semantics
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E110. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a successful run or job prove that pytest ran?

## Conventional answer

A green run or job conclusion was treated as proof that the tests ran and passed.

## First-principles position

A GitHub Actions run and its jobs reported success without running pytest. The proposed resolver would have read those success values as a test pass. The pytest step conclusion distinguishes an actual pass from a skip.

## Evidence with limits

- Run 31360441685 concluded `success` (2026-08-10).
- Both `Run Python Tests` jobs concluded `success` (2026-08-10). One had no `Run pytest` result, and the other reported `skipped`.
- Limits: One run observed on 2026-08-10. The workflow intentionally skips pytest when no Python inputs change. The resolver that would misread it was a draft in PR 4822.
- State on main at 1be533c496 (2026-11-26): superseded. The draft `consume_pytest_signal.py` is absent. `scripts/quality_gate/external_signal_gate.py` and `scripts/quality_gate/run_pytest.py` map `SKIPPED` to `UNKNOWN`.

## Decision

Read the `Run pytest` step conclusion when the verdict must certify test execution. Treat a skipped step as `UNKNOWN`.

## Related

- `.serena/memories/decision-local-pass-does-not-clear-red-ci.md`
- `.serena/memories/decision-a-whole-corpus-gate-cannot-be-path-filtered.md`
- `.serena/memories/pr-review/use-get-pr-checks-not-raw-rollup.md`
