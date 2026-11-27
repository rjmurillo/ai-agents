# A declared hook timeout sum overstates real gate latency by 26x to 600x

**Atomicity**: 90%
**Category**: Hook and gate latency
**Source**: Agent session sweep, sessions dated 2026-09. Sweep ids E018. State checked on main at 1be533c496 (2026-11-26).

## Question

Can the sum of declared lefthook timeouts stand in for real gate latency?

## Conventional answer

A declared timeout ceiling is a usable proxy for gate cost. A fall in the ceiling counts as a latency gain.

## First-principles position

The observed runs finished well below the sum of declared timeouts. The ceiling fell from 3,450s to 3,330s when a job was removed (2026-09-17). That change does not show how much faster a run finishes.

## Evidence with limits

- Measured 2026-09-17: worst observed pre-push time 128.21s against a declared 3,330s. Worst observed pre-commit time 9.82s against a declared 6,230s.
- That is about 26 times for pre-push and about 600 times for pre-commit.
- Limits: Pre-push n=2 and pre-commit n=3 on one 4-CPU container. A later 2026-11-10 run on a 48-CPU host gave pre-push p95 201.73s, so the ratio depends on the host and the job set. The ratio uses summed timeouts, which no run reaches.
- State on main at 1be533c496 (2026-11-26): fixed in metrics. .project-toolkit/metrics/gate-latency-2026-11-10/pre-push-python.md:24 has a "Declared vs measured" heading, and line 26 gives the declared budget of 3330.0 seconds. The report now separates the declared budget from observed times.

## Decision

Report latency from measured runs, never from summed timeout values. A drop in the declared ceiling from removing a job is not a latency gain.

## Related

- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
- `.serena/memories/decision-pre-push-suite-timeout-budget.md`
