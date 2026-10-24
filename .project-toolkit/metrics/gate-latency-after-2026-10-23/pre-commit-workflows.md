# Gate latency: pre-commit (workflows)

- Commit: `c5fc0f5becf8d80666302d1c0708bbdec36fee6b`
- Captured at: `2026-10-23T22:25:24.991028+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 6.13, 9.35, 7.46 (1/5/15 min); 0.13 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class workflows --repetitions 20 --json ../perf-6734-after-out/pre-commit-workflows.json --markdown ../perf-6734-after-out/pre-commit-workflows.md
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
| __hook__ | hook wall clock | 20 | 4.415 | 4.540 | 4.277 | 4.548 |
| action-pin-policy | job | 20 | 0.250 | 0.280 | 0.230 | 0.280 |
| actionlint | job | 20 | 0.050 | 0.080 | 0.040 | 0.080 |
| agents-write-targets | job | 20 | 2.710 | 2.840 | 2.570 | 2.850 |
| branch-context-policy | job | 20 | 0.230 | 0.230 | 0.220 | 0.230 |
| branch-policy | job | 20 | 0.220 | 0.220 | 0.210 | 0.220 |
| conflict-marker-policy | job | 20 | 0.260 | 0.280 | 0.230 | 0.290 |
| context-output-check | job | 20 | 0.930 | 0.940 | 0.930 | 0.940 |
| group (14) | group total (sum) | 20 | 0.930 | 0.940 | 0.930 | 0.940 |
| group (6) | group total (sum) | 20 | 5.120 | 5.220 | 4.950 | 5.240 |
| infrastructure-advisory | job | 20 | 0.110 | 0.140 | 0.090 | 0.140 |
| push-lock-commit-guard | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| root-hygiene-policy | job | 20 | 0.240 | 0.270 | 0.220 | 0.280 |
| root-scratch-policy | job | 20 | 0.250 | 0.280 | 0.220 | 0.280 |
| security-suppressions-staged | job | 20 | 0.260 | 0.290 | 0.230 | 0.290 |
| taste-advisory | job | 20 | 0.300 | 0.340 | 0.290 | 0.350 |
| workflow-validation | job | 20 | 0.240 | 0.260 | 0.200 | 0.260 |
| yaml-advisory | job | 20 | 0.410 | 0.430 | 0.380 | 0.440 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 4.540 | 4.450 | 19 | False | 0 | 5.12 | 5.03 |
| 1 | 0 | complete | 4.344 | 4.250 | 19 | False | 0 | 5.03 | 5.35 |
| 2 | 0 | complete | 4.548 | 4.450 | 19 | False | 0 | 5.35 | 5.72 |
| 3 | 0 | complete | 4.446 | 4.350 | 19 | False | 0 | 5.72 | 6.06 |
| 4 | 0 | complete | 4.484 | 4.390 | 19 | False | 0 | 6.06 | 6.30 |
| 5 | 0 | complete | 4.404 | 4.310 | 19 | False | 0 | 6.30 | 5.95 |
| 6 | 0 | complete | 4.479 | 4.390 | 19 | False | 0 | 5.95 | 5.64 |
| 7 | 0 | complete | 4.277 | 4.180 | 19 | False | 0 | 5.64 | 5.64 |
| 8 | 0 | complete | 4.398 | 4.300 | 19 | False | 0 | 5.43 | 5.43 |
| 9 | 0 | complete | 4.528 | 4.430 | 19 | False | 0 | 5.43 | 5.15 |
| 10 | 0 | complete | 4.496 | 4.400 | 19 | False | 0 | 5.15 | 5.78 |
| 11 | 0 | complete | 4.363 | 4.270 | 19 | False | 0 | 5.78 | 5.64 |
| 12 | 0 | complete | 4.415 | 4.320 | 19 | False | 0 | 5.64 | 6.23 |
| 13 | 0 | complete | 4.279 | 4.190 | 19 | False | 0 | 6.23 | 6.45 |
| 14 | 0 | complete | 4.445 | 4.350 | 19 | False | 0 | 6.45 | 6.73 |
| 15 | 0 | complete | 4.429 | 4.330 | 19 | False | 0 | 6.73 | 6.84 |
| 16 | 0 | complete | 4.351 | 4.260 | 19 | False | 0 | 6.84 | 6.53 |
| 17 | 0 | complete | 4.345 | 4.250 | 19 | False | 0 | 6.53 | 6.53 |
| 18 | 0 | complete | 4.376 | 4.280 | 19 | False | 0 | 6.53 | 6.41 |
| 19 | 0 | complete | 4.422 | 4.330 | 19 | False | 0 | 6.41 | 6.13 |

