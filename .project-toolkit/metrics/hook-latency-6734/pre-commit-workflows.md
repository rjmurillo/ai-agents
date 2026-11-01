# Gate latency: pre-commit (workflows)

- Commit: `d44913c9aa60a9de7f2346e0db953e2c1674aec6`
- Captured at: `2026-10-20T14:35:08.650637+00:00`
- Repetitions: 21
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 1.19, 1.16, 1.28 (1/5/15 min); 0.30 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-commit --change-class workflows --repetitions 21 --json <scratch>/full-pre-commit-workflows.json --markdown <scratch>/full-pre-commit-workflows.md
```

## Change class

- `workflows`: `.github/workflows/pytest.yml`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 5815.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 21 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 21 | 30.472 | 33.058 | 28.260 | 33.362 |
| action-pin-policy | job | 21 | 0.780 | 0.980 | 0.510 | 1.000 |
| agents-write-targets | job | 21 | 28.010 | 30.680 | 25.930 | 31.000 |
| branch-context-policy | job | 21 | 0.310 | 0.390 | 0.250 | 0.400 |
| branch-policy | job | 21 | 0.300 | 0.370 | 0.250 | 0.370 |
| conflict-marker-policy | job | 21 | 0.760 | 0.880 | 0.540 | 0.890 |
| context-output-check | job | 21 | 1.340 | 1.390 | 1.230 | 1.420 |
| group (14) | group total (sum) | 21 | 1.340 | 1.390 | 1.230 | 1.420 |
| group (6) | group total (sum) | 21 | 34.480 | 37.380 | 31.580 | 37.620 |
| infrastructure-advisory | job | 21 | 0.410 | 0.550 | 0.180 | 0.580 |
| push-lock-commit-guard | job | 21 | 0.110 | 0.140 | 0.090 | 0.140 |
| repair-packed-refs | job | 21 | 0.110 | 0.130 | 0.090 | 0.130 |
| repo-health | job | 21 | 0.110 | 0.120 | 0.090 | 0.130 |
| root-hygiene-policy | job | 21 | 0.680 | 0.830 | 0.460 | 0.940 |
| root-scratch-policy | job | 21 | 0.750 | 0.890 | 0.620 | 0.920 |
| security-suppressions-staged | job | 21 | 0.750 | 0.880 | 0.520 | 0.880 |
| taste-advisory | job | 21 | 0.830 | 1.030 | 0.670 | 1.040 |
| workflow-validation | job | 21 | 0.670 | 0.830 | 0.360 | 0.850 |
| yaml-advisory | job | 21 | 0.770 | 0.900 | 0.520 | 0.970 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 32.762 | 32.610 | 18 | False | 0 | 1.42 | 1.26 |
| 1 | 0 | complete | 30.472 | 30.340 | 18 | False | 0 | 1.26 | 1.20 |
| 2 | 0 | complete | 33.058 | 32.920 | 18 | False | 0 | 1.20 | 1.23 |
| 3 | 0 | complete | 31.415 | 31.280 | 18 | False | 0 | 1.23 | 1.68 |
| 4 | 0 | complete | 32.386 | 32.230 | 18 | False | 0 | 1.54 | 1.33 |
| 5 | 0 | complete | 33.362 | 33.230 | 18 | False | 0 | 1.33 | 1.18 |
| 6 | 0 | complete | 29.635 | 29.510 | 18 | False | 0 | 1.18 | 1.03 |
| 7 | 0 | complete | 32.059 | 31.930 | 18 | False | 0 | 1.03 | 1.02 |
| 8 | 0 | complete | 29.977 | 29.840 | 18 | False | 0 | 1.02 | 1.01 |
| 9 | 0 | complete | 31.045 | 30.890 | 18 | False | 0 | 1.01 | 1.22 |
| 10 | 0 | complete | 31.573 | 31.440 | 18 | False | 0 | 1.22 | 1.12 |
| 11 | 0 | complete | 28.260 | 28.140 | 18 | False | 0 | 1.12 | 1.08 |
| 12 | 0 | complete | 30.094 | 29.910 | 18 | False | 0 | 1.08 | 1.05 |
| 13 | 0 | complete | 30.238 | 30.090 | 18 | False | 0 | 1.05 | 1.03 |
| 14 | 0 | complete | 30.192 | 30.050 | 18 | False | 0 | 1.03 | 1.02 |
| 15 | 0 | complete | 29.454 | 29.300 | 18 | False | 0 | 1.01 | 1.01 |
| 16 | 0 | complete | 31.162 | 31.020 | 18 | False | 0 | 1.01 | 1.00 |
| 17 | 0 | complete | 28.629 | 28.500 | 18 | False | 0 | 1.00 | 1.00 |
| 18 | 0 | complete | 29.985 | 29.840 | 18 | False | 0 | 1.00 | 1.00 |
| 19 | 0 | complete | 28.860 | 28.710 | 18 | False | 0 | 1.00 | 1.00 |
| 20 | 0 | complete | 31.732 | 31.590 | 18 | False | 0 | 1.00 | 1.19 |

