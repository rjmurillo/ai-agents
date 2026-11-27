# Turning on branch coverage for the full pytest run cost 27 seconds and made the coverage combine fail

**Atomicity**: 90%
**Category**: CI coverage, pytest runtime
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E046. State checked on main at 1be533c496 (2026-11-26).

## Question

Should the main pytest run use branch tracing so the duplicate pin test step can be removed?

## Conventional answer

Running branch tracing across the full suite would let CI drop the duplicate pin test step. The change would keep CI runtime flat or reduce it.

## First-principles position

It did neither. Branch tracing on the whole suite added runtime and left child data in mixed mode. The coverage combine then failed. Branch coverage belongs on isolated pin steps only.

## Evidence with limits

- A benchmark (2026-08-06) flagged --cov-branch on the main run at +27.02s, or +6.2 percent, with internally mixed mode child data.
- Branch tracing on the 301 pin tests (2026-08-06) measured 1.01s against 0.86s line only, about 18 percent slower.
- Coverage raised `DataError` when it tried to combine branch and statement data. Elapsed time was 465.93s with branch coverage versus 438.91s with line coverage (2026-08-06).
- Limits: One run per arm on a local machine, 2026-08-06, so the 6.2 percent has no variance estimate. The CI runner was not measured.
- State on main at 1be533c496 (2026-11-26): fixed. `.github/workflows/pytest.yml:589` and line 606 run `--cov-branch` only on isolated pin steps. Each step has its own `COVERAGE_FILE`. Lines 666 to 667 describe turning branch traces into executed lines before combining. The main run uses statement coverage.

## Decision

Keep branch coverage on isolated pin steps and combine by projecting arcs to lines. Do not enable --cov-branch on the whole suite to save a duplicate step.
