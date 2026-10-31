# Gate latency: pre-commit (python)

- Commit: `90af99ede2f77057edaa885d0d64d19a62cda634`
- Captured at: `2026-10-20T14:24:19.119965+00:00`
- Repetitions: 21
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v139-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7
- Load average: 1.42, 1.58, 1.47 (1/5/15 min); 0.36 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --repo <repo> --hook pre-commit --change-class python --repetitions 21 --json <scratch>/full-pre-commit-python.json --markdown <scratch>/full-pre-commit-python.md
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 5815.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 21 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 21 | 30.147 | 32.755 | 27.572 | 35.008 |
| agents-write-targets | job | 21 | 27.690 | 30.170 | 25.250 | 32.520 |
| branch-context-policy | job | 21 | 0.310 | 0.350 | 0.250 | 0.380 |
| branch-policy | job | 21 | 0.310 | 0.380 | 0.250 | 0.410 |
| conflict-marker-policy | job | 21 | 0.730 | 0.900 | 0.550 | 0.910 |
| context-output-check | job | 21 | 1.300 | 1.420 | 1.200 | 1.440 |
| group (14) | group total (sum) | 21 | 1.300 | 1.420 | 1.200 | 1.440 |
| group (6) | group total (sum) | 21 | 50.210 | 53.010 | 45.060 | 58.690 |
| infrastructure-advisory | job | 21 | 0.400 | 0.560 | 0.260 | 0.580 |
| push-lock-commit-guard | job | 21 | 0.110 | 0.140 | 0.090 | 0.150 |
| python-autofix | job | 21 | 0.660 | 0.810 | 0.440 | 0.820 |
| python-check | job | 21 | 0.560 | 0.660 | 0.340 | 0.720 |
| python-format | job | 21 | 0.250 | 0.380 | 0.080 | 0.390 |
| repair-packed-refs | job | 21 | 0.110 | 0.140 | 0.090 | 0.140 |
| repo-health | job | 21 | 0.100 | 0.140 | 0.090 | 0.240 |
| root-hygiene-policy | job | 21 | 0.730 | 0.890 | 0.520 | 1.000 |
| root-scratch-policy | job | 21 | 0.740 | 0.920 | 0.540 | 0.970 |
| security-suppressions-staged | job | 21 | 0.800 | 0.980 | 0.730 | 1.010 |
| staged-dash-policy | job | 21 | 0.780 | 0.910 | 0.650 | 0.950 |
| subprocess-encoding | job | 21 | 15.350 | 17.290 | 13.550 | 18.840 |
| taste-advisory | job | 21 | 0.890 | 0.980 | 0.740 | 0.990 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 29.367 | 29.230 | 20 | False | 0 | 1.22 | 1.48 |
| 1 | 0 | complete | 27.572 | 27.460 | 20 | False | 0 | 1.48 | 1.63 |
| 2 | 0 | complete | 30.860 | 30.710 | 20 | False | 0 | 1.63 | 1.55 |
| 3 | 0 | complete | 29.972 | 29.840 | 20 | False | 0 | 1.55 | 1.51 |
| 4 | 0 | complete | 32.142 | 32.000 | 20 | False | 0 | 1.51 | 1.44 |
| 5 | 0 | complete | 30.395 | 30.270 | 20 | False | 0 | 1.44 | 1.46 |
| 6 | 0 | complete | 35.008 | 34.840 | 20 | False | 0 | 1.46 | 1.43 |
| 7 | 0 | complete | 31.179 | 31.010 | 20 | False | 0 | 1.43 | 1.55 |
| 8 | 0 | complete | 30.985 | 30.860 | 20 | False | 0 | 1.55 | 1.50 |
| 9 | 0 | complete | 32.224 | 32.100 | 20 | False | 0 | 1.50 | 1.48 |
| 10 | 0 | complete | 29.127 | 28.980 | 20 | False | 0 | 1.48 | 1.41 |
| 11 | 0 | complete | 29.894 | 29.760 | 20 | False | 0 | 1.41 | 1.95 |
| 12 | 0 | complete | 31.083 | 30.970 | 20 | False | 0 | 1.95 | 2.22 |
| 13 | 0 | complete | 29.800 | 29.650 | 20 | False | 0 | 2.22 | 1.93 |
| 14 | 0 | complete | 32.755 | 32.620 | 20 | False | 0 | 1.93 | 1.74 |
| 15 | 0 | complete | 29.313 | 29.170 | 20 | False | 0 | 1.74 | 1.62 |
| 16 | 0 | complete | 29.846 | 29.710 | 20 | False | 0 | 1.62 | 1.55 |
| 17 | 0 | complete | 29.194 | 29.070 | 20 | False | 0 | 1.55 | 1.50 |
| 18 | 0 | complete | 29.639 | 29.480 | 20 | False | 0 | 1.50 | 1.40 |
| 19 | 0 | complete | 30.147 | 30.020 | 20 | False | 0 | 1.40 | 1.41 |
| 20 | 0 | complete | 30.451 | 30.320 | 20 | False | 0 | 1.41 | 1.42 |

