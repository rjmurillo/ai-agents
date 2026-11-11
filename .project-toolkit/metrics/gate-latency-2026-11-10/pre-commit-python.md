# Gate latency: pre-commit (python)

- Commit: `5fbdfd238bd4eb64b6adfa3791b2fff3554db060`
- Captured at: `2026-11-10T01:35:40.609052+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-43-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 20.72, 26.84, 26.60 (1/5/15 min); 0.43 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class python --repetitions 20 --json .project-toolkit/metrics/gate-latency-2026-11-10/pre-commit-python.json --markdown .project-toolkit/metrics/gate-latency-2026-11-10/pre-commit-python.md
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
| __hook__ | hook wall clock | 20 | 5.562 | 5.917 | 5.383 | 6.015 |
| agents-write-targets | job | 20 | 2.180 | 2.320 | 2.010 | 2.380 |
| branch-context-policy | job | 20 | 0.180 | 0.190 | 0.170 | 0.190 |
| branch-policy | job | 20 | 0.170 | 0.190 | 0.160 | 0.200 |
| conflict-marker-policy | job | 20 | 0.220 | 0.270 | 0.180 | 0.270 |
| context-output-check | job | 20 | 0.990 | 1.040 | 0.960 | 1.050 |
| group (14) | group total (sum) | 20 | 0.990 | 1.040 | 0.960 | 1.050 |
| group (6) | group total (sum) | 20 | 8.080 | 8.560 | 7.790 | 8.620 |
| infrastructure-advisory | job | 20 | 0.120 | 0.170 | 0.100 | 0.200 |
| push-lock-commit-guard | job | 20 | 0.060 | 0.070 | 0.060 | 0.070 |
| python-autofix | job | 20 | 0.220 | 0.250 | 0.190 | 0.260 |
| python-check | job | 20 | 0.200 | 0.240 | 0.140 | 0.240 |
| python-format | job | 20 | 0.080 | 0.140 | 0.040 | 0.150 |
| repair-packed-refs | job | 20 | 0.060 | 0.080 | 0.060 | 0.080 |
| repo-health | job | 20 | 0.060 | 0.070 | 0.060 | 0.070 |
| root-hygiene-policy | job | 20 | 0.200 | 0.250 | 0.170 | 0.260 |
| root-scratch-policy | job | 20 | 0.230 | 0.280 | 0.180 | 0.290 |
| security-suppressions-staged | job | 20 | 0.250 | 0.280 | 0.180 | 0.320 |
| staged-dash-policy | job | 20 | 0.230 | 0.290 | 0.170 | 0.300 |
| subprocess-encoding | job | 20 | 3.850 | 4.250 | 3.710 | 4.370 |
| taste-advisory | job | 20 | 0.280 | 0.320 | 0.230 | 0.330 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 5.579 | 5.450 | 20 | False | 0 | 22.30 | 23.31 |
| 1 | 0 | complete | 5.562 | 5.440 | 20 | False | 0 | 23.31 | 22.44 |
| 2 | 0 | complete | 5.537 | 5.410 | 20 | False | 0 | 22.44 | 21.68 |
| 3 | 0 | complete | 5.562 | 5.430 | 20 | False | 0 | 21.68 | 20.99 |
| 4 | 0 | complete | 5.452 | 5.300 | 20 | False | 0 | 20.99 | 20.35 |
| 5 | 0 | complete | 5.488 | 5.360 | 20 | False | 0 | 20.35 | 20.24 |
| 6 | 0 | complete | 5.446 | 5.320 | 20 | False | 0 | 20.24 | 20.22 |
| 7 | 0 | complete | 5.609 | 5.470 | 20 | False | 0 | 20.22 | 24.05 |
| 8 | 0 | complete | 5.917 | 5.790 | 20 | False | 0 | 24.05 | 23.65 |
| 9 | 0 | complete | 5.811 | 5.660 | 20 | False | 0 | 23.65 | 23.52 |
| 10 | 0 | complete | 5.520 | 5.390 | 20 | False | 0 | 23.52 | 23.00 |
| 11 | 0 | complete | 6.015 | 5.890 | 20 | False | 0 | 23.00 | 22.52 |
| 12 | 0 | complete | 5.477 | 5.340 | 20 | False | 0 | 22.52 | 22.47 |
| 13 | 0 | complete | 5.693 | 5.560 | 20 | False | 0 | 22.47 | 22.44 |
| 14 | 0 | complete | 5.518 | 5.390 | 20 | False | 0 | 22.08 | 21.35 |
| 15 | 0 | complete | 5.568 | 5.440 | 20 | False | 0 | 21.35 | 20.76 |
| 16 | 0 | complete | 5.584 | 5.460 | 20 | False | 0 | 20.76 | 21.82 |
| 17 | 0 | complete | 5.816 | 5.690 | 20 | False | 0 | 21.82 | 21.04 |
| 18 | 0 | complete | 5.404 | 5.280 | 20 | False | 0 | 21.04 | 20.87 |
| 19 | 0 | complete | 5.383 | 5.250 | 20 | False | 0 | 20.87 | 20.72 |

