# The worktree report ran about ten times slower during real pushes than on its own

**Atomicity**: 90%
**Category**: CI pre-push timing
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E063. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a script's standalone speedup carry over to its time inside the pre-push hook?

## Conventional answer

A standalone speedup carries over to the hook. Hook-time budgets follow standalone timing. An earlier claim said an 11x standalone speedup unblocked the fleet.

## First-principles position

The same input ran in two idle runs and four real pushes. Idle runs took 6.83 and 11.47 seconds. Four consecutive pushes took 92.87 to 101.33 seconds, with the python-tests job running at the same time. The 11x claim was an idle-only artifact. A standalone timing does not predict hook time.

## Evidence with limits

- With 288 registered worktrees and 0 removal candidates (2026-08-02), two idle runs took 11.47s and 6.83s.
- Four consecutive real pushes ran the same job in 92.87, 94.45, 99.48 and 101.33 seconds while python-tests ran concurrently (2026-08-02).
- The gap is about 10x on identical input.
- Limits: One machine, one date (2026-08-02), four pushes. The cause is not measured: no CPU, disk or git-lock telemetry. Do not reuse the 9 to 15x ratio as a planning number. The rule file already records the figures as a repo rule, and only the memory tree lacked them.
- State on main at 1be533c496 (2026-11-26): guidance updated, timeout not validated. `rule-ci-scripts.md:38` MUST-16 says to size a pre-push job's timeout for a loaded machine, and records 6.83s and 11.47s standalone against 92.87 to 101.33s in four pushes. `lefthook.yml:752` sets `--timeout 100`, which is below the 101.33s peak those pushes measured.

## Decision

Measure a pre-push job inside the real parallel hook before claiming a speedup or setting its timeout. A standalone timing does not predict hook time.

## Related

- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
- `.serena/memories/ci/tracking-branch-push-retries-under-fleet-cpu-load.md`
