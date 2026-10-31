# Gate latency: pre-commit (python)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-23T04:47:32.384589+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 3.49, 3.88, 3.79 (1/5/15 min); 0.07 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class python --repetitions 20 --json ../perf-6734-out/pre-commit-python.json --markdown ../perf-6734-out/pre-commit-python.md
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 5815.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 20 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 20 | 25.550 | 25.796 | 25.294 | 26.073 |
| agents-write-targets | job | 20 | 23.840 | 24.090 | 23.580 | 24.370 |
| branch-context-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| branch-policy | job | 20 | 0.220 | 0.220 | 0.220 | 0.220 |
| conflict-marker-policy | job | 20 | 0.260 | 0.290 | 0.230 | 0.290 |
| context-output-check | job | 20 | 0.940 | 0.940 | 0.930 | 0.940 |
| group (14) | group total (sum) | 20 | 0.940 | 0.940 | 0.930 | 0.940 |
| group (6) | group total (sum) | 20 | 39.250 | 39.530 | 38.950 | 39.910 |
| infrastructure-advisory | job | 20 | 0.120 | 0.150 | 0.090 | 0.160 |
| push-lock-commit-guard | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| python-autofix | job | 20 | 0.210 | 0.220 | 0.170 | 0.220 |
| python-check | job | 20 | 0.180 | 0.210 | 0.140 | 0.210 |
| python-format | job | 20 | 0.060 | 0.090 | 0.030 | 0.100 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.080 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| root-hygiene-policy | job | 20 | 0.240 | 0.270 | 0.220 | 0.290 |
| root-scratch-policy | job | 20 | 0.250 | 0.280 | 0.220 | 0.290 |
| security-suppressions-staged | job | 20 | 0.270 | 0.300 | 0.240 | 0.300 |
| staged-dash-policy | job | 20 | 0.250 | 0.280 | 0.230 | 0.280 |
| subprocess-encoding | job | 20 | 13.230 | 13.380 | 13.110 | 13.400 |
| taste-advisory | job | 20 | 0.330 | 0.350 | 0.300 | 0.360 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 25.660 | 25.570 | 20 | False | 0 | 4.87 | 4.42 |
| 1 | 0 | complete | 25.607 | 25.510 | 20 | False | 0 | 4.42 | 4.41 |
| 2 | 0 | complete | 25.550 | 25.460 | 20 | False | 0 | 4.41 | 4.30 |
| 3 | 0 | complete | 25.579 | 25.480 | 20 | False | 0 | 4.30 | 3.97 |
| 4 | 0 | complete | 25.796 | 25.700 | 20 | False | 0 | 3.97 | 3.88 |
| 5 | 0 | complete | 25.613 | 25.520 | 20 | False | 0 | 3.88 | 3.63 |
| 6 | 0 | complete | 26.073 | 25.980 | 20 | False | 0 | 3.63 | 3.32 |
| 7 | 0 | complete | 25.430 | 25.340 | 20 | False | 0 | 3.32 | 3.56 |
| 8 | 0 | complete | 25.495 | 25.400 | 20 | False | 0 | 3.56 | 3.85 |
| 9 | 0 | complete | 25.565 | 25.470 | 20 | False | 0 | 3.85 | 4.28 |
| 10 | 0 | complete | 25.454 | 25.360 | 20 | False | 0 | 4.28 | 3.83 |
| 11 | 0 | complete | 25.555 | 25.460 | 20 | False | 0 | 3.83 | 3.65 |
| 12 | 0 | complete | 25.481 | 25.390 | 20 | False | 0 | 3.65 | 3.69 |
| 13 | 0 | complete | 25.294 | 25.200 | 20 | False | 0 | 3.69 | 3.46 |
| 14 | 0 | complete | 25.491 | 25.400 | 20 | False | 0 | 3.46 | 3.15 |
| 15 | 0 | complete | 25.501 | 25.410 | 20 | False | 0 | 3.15 | 3.57 |
| 16 | 0 | complete | 25.712 | 25.620 | 20 | False | 0 | 3.57 | 3.68 |
| 17 | 0 | complete | 25.425 | 25.330 | 20 | False | 0 | 3.68 | 3.84 |
| 18 | 0 | complete | 25.661 | 25.570 | 20 | False | 0 | 3.84 | 3.77 |
| 19 | 0 | complete | 25.511 | 25.420 | 20 | False | 0 | 3.77 | 3.49 |

