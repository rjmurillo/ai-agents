# Gate latency: pre-commit (workflows)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-23T04:56:05.717266+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 4.31, 4.23, 3.91 (1/5/15 min); 0.09 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class workflows --repetitions 20 --json ../perf-6734-out/pre-commit-workflows.json --markdown ../perf-6734-out/pre-commit-workflows.md
```

## Change class

- `workflows`: `.github/workflows/pytest.yml`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 5815.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 20 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 20 | 25.533 | 25.760 | 25.358 | 26.197 |
| action-pin-policy | job | 20 | 0.270 | 0.290 | 0.230 | 0.290 |
| actionlint | job | 20 | 0.050 | 0.060 | 0.040 | 0.070 |
| agents-write-targets | job | 20 | 23.820 | 24.060 | 23.660 | 24.490 |
| branch-context-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| branch-policy | job | 20 | 0.220 | 0.220 | 0.220 | 0.220 |
| conflict-marker-policy | job | 20 | 0.250 | 0.280 | 0.230 | 0.300 |
| context-output-check | job | 20 | 0.930 | 0.940 | 0.920 | 0.940 |
| group (14) | group total (sum) | 20 | 0.930 | 0.940 | 0.920 | 0.940 |
| group (6) | group total (sum) | 20 | 26.210 | 26.510 | 26.090 | 26.950 |
| infrastructure-advisory | job | 20 | 0.120 | 0.150 | 0.090 | 0.150 |
| push-lock-commit-guard | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| root-hygiene-policy | job | 20 | 0.240 | 0.280 | 0.220 | 0.290 |
| root-scratch-policy | job | 20 | 0.260 | 0.280 | 0.220 | 0.280 |
| security-suppressions-staged | job | 20 | 0.270 | 0.280 | 0.230 | 0.280 |
| taste-advisory | job | 20 | 0.310 | 0.340 | 0.290 | 0.350 |
| workflow-validation | job | 20 | 0.240 | 0.260 | 0.210 | 0.260 |
| yaml-advisory | job | 20 | 0.400 | 0.430 | 0.380 | 0.440 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 25.478 | 25.380 | 19 | False | 0 | 3.49 | 3.11 |
| 1 | 0 | complete | 25.406 | 25.310 | 19 | False | 0 | 3.11 | 3.14 |
| 2 | 0 | complete | 25.412 | 25.320 | 19 | False | 0 | 3.14 | 2.83 |
| 3 | 0 | complete | 25.543 | 25.450 | 19 | False | 0 | 2.83 | 2.91 |
| 4 | 0 | complete | 25.496 | 25.400 | 19 | False | 0 | 2.91 | 3.07 |
| 5 | 0 | complete | 25.625 | 25.530 | 19 | False | 0 | 3.07 | 3.05 |
| 6 | 0 | complete | 25.452 | 25.360 | 19 | False | 0 | 3.05 | 3.13 |
| 7 | 0 | complete | 25.411 | 25.320 | 19 | False | 0 | 3.13 | 2.88 |
| 8 | 0 | complete | 25.430 | 25.340 | 19 | False | 0 | 2.88 | 3.10 |
| 9 | 0 | complete | 25.447 | 25.350 | 19 | False | 0 | 3.10 | 3.82 |
| 10 | 0 | complete | 25.358 | 25.260 | 19 | False | 0 | 3.82 | 3.26 |
| 11 | 0 | complete | 25.533 | 25.440 | 19 | False | 0 | 3.26 | 3.20 |
| 12 | 0 | complete | 25.596 | 25.500 | 19 | False | 0 | 3.20 | 3.46 |
| 13 | 0 | complete | 26.197 | 26.100 | 19 | False | 0 | 3.46 | 5.13 |
| 14 | 0 | complete | 25.658 | 25.560 | 19 | False | 0 | 5.13 | 4.54 |
| 15 | 0 | complete | 25.720 | 25.630 | 19 | False | 0 | 4.54 | 5.67 |
| 16 | 0 | complete | 25.649 | 25.550 | 19 | False | 0 | 5.67 | 5.77 |
| 17 | 0 | complete | 25.571 | 25.480 | 19 | False | 0 | 5.79 | 5.17 |
| 18 | 0 | complete | 25.760 | 25.670 | 19 | False | 0 | 5.17 | 4.78 |
| 19 | 0 | complete | 25.637 | 25.540 | 19 | False | 0 | 4.78 | 4.31 |

