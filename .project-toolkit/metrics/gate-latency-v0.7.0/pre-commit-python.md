# Gate latency: pre-commit (python)

- Commit: `1251644ddfce00e9d6ab2a2025ebab977089e305`
- Captured at: `2026-09-16T07:29:52.668380+00:00`
- Repetitions: 3
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class python --repetitions 3 --json .project-toolkit/metrics/gate-latency-v0.7.0/pre-commit-python.json --markdown .project-toolkit/metrics/gate-latency-v0.7.0/pre-commit-python.md --allow-dirty
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 6230.0 seconds

n=3 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 3 | 7.216 | 7.215 | 7.129 |
| branch-context-policy | job | 3 | 0.210 | 0.200 | 0.200 |
| branch-policy | job | 3 | 0.210 | 0.200 | 0.190 |
| commit-file-count | job | 3 | 0.200 | 0.200 | 0.200 |
| conflict-marker-policy | job | 3 | 0.380 | 0.340 | 0.240 |
| group (6) | group total (sum) | 3 | 8.360 | 8.190 | 8.170 |
| infrastructure-advisory | job | 3 | 0.210 | 0.160 | 0.110 |
| push-lock-commit-guard | job | 3 | 0.080 | 0.080 | 0.080 |
| python-autofix | job | 3 | 0.130 | 0.130 | 0.100 |
| python-check | job | 3 | 0.140 | 0.110 | 0.100 |
| repair-packed-refs | job | 3 | 0.090 | 0.080 | 0.080 |
| repo-health | job | 3 | 0.080 | 0.080 | 0.080 |
| root-hygiene-policy | job | 3 | 0.410 | 0.340 | 0.290 |
| root-scratch-policy | job | 3 | 0.350 | 0.310 | 0.300 |
| scope-policy | job | 3 | 0.160 | 0.150 | 0.150 |
| security-suppressions-staged | job | 3 | 0.390 | 0.370 | 0.280 |
| subprocess-encoding | job | 3 | 6.150 | 6.130 | 6.060 |
| taste-advisory | job | 3 | 0.430 | 0.400 | 0.340 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 7.215 | 7.160 | 17 | False | 0 |
| 1 | 0 | 7.216 | 7.160 | 17 | False | 0 |
| 2 | 0 | 7.129 | 7.070 | 17 | False | 0 |

