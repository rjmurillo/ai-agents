# Gate latency: pre-commit (python)

- Commit: `c5fc0f5becf8d80666302d1c0708bbdec36fee6b`
- Captured at: `2026-10-23T22:23:34.443505+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 6.57, 10.95, 7.68 (1/5/15 min); 0.14 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class python --repetitions 20 --json ../perf-6734-after-out/pre-commit-python.json --markdown ../perf-6734-after-out/pre-commit-python.md
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
| __hook__ | hook wall clock | 20 | 7.112 | 7.185 | 7.088 | 7.219 |
| agents-write-targets | job | 20 | 2.660 | 2.840 | 2.540 | 3.020 |
| branch-context-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| branch-policy | job | 20 | 0.220 | 0.220 | 0.210 | 0.220 |
| conflict-marker-policy | job | 20 | 0.270 | 0.290 | 0.220 | 0.290 |
| context-output-check | job | 20 | 0.930 | 0.940 | 0.930 | 0.940 |
| group (14) | group total (sum) | 20 | 0.930 | 0.940 | 0.930 | 0.940 |
| group (6) | group total (sum) | 20 | 10.260 | 10.470 | 10.080 | 10.540 |
| infrastructure-advisory | job | 20 | 0.110 | 0.150 | 0.090 | 0.150 |
| push-lock-commit-guard | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| python-autofix | job | 20 | 0.210 | 0.220 | 0.160 | 0.220 |
| python-check | job | 20 | 0.180 | 0.200 | 0.130 | 0.200 |
| python-format | job | 20 | 0.060 | 0.090 | 0.030 | 0.100 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.080 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| root-hygiene-policy | job | 20 | 0.240 | 0.270 | 0.230 | 0.280 |
| root-scratch-policy | job | 20 | 0.260 | 0.280 | 0.220 | 0.290 |
| security-suppressions-staged | job | 20 | 0.270 | 0.290 | 0.240 | 0.300 |
| staged-dash-policy | job | 20 | 0.240 | 0.280 | 0.230 | 0.290 |
| subprocess-encoding | job | 20 | 5.400 | 5.480 | 5.380 | 5.500 |
| taste-advisory | job | 20 | 0.320 | 0.340 | 0.280 | 0.340 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 7.099 | 7.000 | 20 | False | 0 | 24.94 | 21.49 |
| 1 | 0 | complete | 7.103 | 7.010 | 20 | False | 0 | 21.49 | 20.01 |
| 2 | 0 | complete | 7.094 | 7.000 | 20 | False | 0 | 20.01 | 18.13 |
| 3 | 0 | complete | 7.112 | 7.020 | 20 | False | 0 | 18.13 | 16.92 |
| 4 | 0 | complete | 7.088 | 6.990 | 20 | False | 0 | 16.92 | 15.43 |
| 5 | 0 | complete | 7.090 | 7.000 | 20 | False | 0 | 15.43 | 14.44 |
| 6 | 0 | complete | 7.180 | 7.090 | 20 | False | 0 | 14.44 | 14.24 |
| 7 | 0 | complete | 7.104 | 7.010 | 20 | False | 0 | 14.24 | 12.36 |
| 8 | 0 | complete | 7.113 | 7.020 | 20 | False | 0 | 12.36 | 11.93 |
| 9 | 0 | complete | 7.109 | 7.010 | 20 | False | 0 | 11.93 | 10.77 |
| 10 | 0 | complete | 7.096 | 7.000 | 20 | False | 0 | 10.77 | 10.07 |
| 11 | 0 | complete | 7.126 | 7.030 | 20 | False | 0 | 10.07 | 9.86 |
| 12 | 0 | complete | 7.219 | 7.130 | 20 | False | 0 | 9.86 | 9.31 |
| 13 | 0 | complete | 7.106 | 7.010 | 20 | False | 0 | 9.31 | 9.53 |
| 14 | 0 | complete | 7.185 | 7.090 | 20 | False | 0 | 8.92 | 8.45 |
| 15 | 0 | complete | 7.127 | 7.030 | 20 | False | 0 | 8.45 | 8.57 |
| 16 | 0 | complete | 7.128 | 7.030 | 20 | False | 0 | 8.57 | 7.64 |
| 17 | 0 | complete | 7.122 | 7.030 | 20 | False | 0 | 7.64 | 7.34 |
| 18 | 0 | complete | 7.123 | 7.030 | 20 | False | 0 | 7.34 | 6.97 |
| 19 | 0 | complete | 7.135 | 7.040 | 20 | False | 0 | 6.97 | 6.57 |

