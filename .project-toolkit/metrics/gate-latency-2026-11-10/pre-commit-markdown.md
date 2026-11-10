# Gate latency: pre-commit (markdown)

- Commit: `5fbdfd238bd4eb64b6adfa3791b2fff3554db060`
- Captured at: `2026-11-10T01:37:48.870884+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-43-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 27.29, 28.23, 27.20 (1/5/15 min); 0.57 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class markdown --repetitions 20 --json .project-toolkit/metrics/gate-latency-2026-11-10/pre-commit-markdown.json --markdown .project-toolkit/metrics/gate-latency-2026-11-10/pre-commit-markdown.md
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 5815.0 seconds

## Latency by scope

Hook `piped` flag: true. A non-zero exit is treated as truncation (lefthook's piped semantics: a failed job skips the remainder), even at n=1. This is a deliberate conservative false positive: a piped hook whose LAST job fails ran every job and is still classified `truncated`, because excluding one valid sample costs less than including one invalid one.

The summaries below cover all 20 repetitions.

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | p50 | p95 | min | max |
|---|---|---|---|---|---|---|
| __hook__ | hook wall clock | 20 | 6.134 | 6.844 | 5.744 | 7.229 |
| agents-write-targets | job | 20 | 2.230 | 2.410 | 1.960 | 2.800 |
| branch-context-policy | job | 20 | 0.180 | 0.210 | 0.170 | 0.250 |
| branch-policy | job | 20 | 0.180 | 0.190 | 0.170 | 0.200 |
| conflict-marker-policy | job | 20 | 0.230 | 0.300 | 0.180 | 0.300 |
| context-output-check | job | 20 | 1.010 | 1.120 | 0.950 | 1.150 |
| group (14) | group total (sum) | 20 | 1.010 | 1.120 | 0.950 | 1.150 |
| group (5) | group total (sum) | 20 | 2.210 | 2.640 | 2.040 | 2.800 |
| group (6) | group total (sum) | 20 | 3.560 | 4.070 | 3.240 | 4.240 |
| infrastructure-advisory | job | 20 | 0.090 | 0.140 | 0.070 | 0.190 |
| markdown-autofix | job | 20 | 1.080 | 1.330 | 1.040 | 1.400 |
| markdown-check | job | 20 | 1.050 | 1.470 | 0.990 | 1.560 |
| push-lock-commit-guard | job | 20 | 0.070 | 0.070 | 0.060 | 0.080 |
| python-format | job | 20 | 0.080 | 0.100 | 0.050 | 0.100 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.060 | 0.070 |
| repo-health | job | 20 | 0.060 | 0.070 | 0.060 | 0.080 |
| root-hygiene-policy | job | 20 | 0.210 | 0.290 | 0.180 | 0.330 |
| root-scratch-policy | job | 20 | 0.220 | 0.300 | 0.180 | 0.330 |
| staged-dash-policy | job | 20 | 0.210 | 0.320 | 0.190 | 0.330 |
| taste-advisory | job | 20 | 0.280 | 0.320 | 0.230 | 0.320 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 6.844 | 6.720 | 19 | False | 0 | 20.72 | 22.35 |
| 1 | 0 | complete | 7.229 | 7.100 | 19 | False | 0 | 22.35 | 23.36 |
| 2 | 0 | complete | 6.129 | 5.960 | 19 | False | 0 | 23.36 | 24.36 |
| 3 | 0 | complete | 6.251 | 6.120 | 19 | False | 0 | 24.36 | 24.82 |
| 4 | 0 | complete | 6.079 | 5.950 | 19 | False | 0 | 24.82 | 25.39 |
| 5 | 0 | complete | 6.212 | 6.030 | 19 | False | 0 | 25.39 | 25.28 |
| 6 | 0 | complete | 6.061 | 5.930 | 19 | False | 0 | 25.28 | 28.78 |
| 7 | 0 | complete | 6.082 | 5.950 | 19 | False | 0 | 28.78 | 30.40 |
| 8 | 0 | complete | 6.106 | 5.980 | 19 | False | 0 | 30.40 | 36.13 |
| 9 | 0 | complete | 6.261 | 6.130 | 19 | False | 0 | 36.13 | 35.32 |
| 10 | 0 | complete | 5.997 | 5.870 | 19 | False | 0 | 35.32 | 33.27 |
| 11 | 0 | complete | 6.175 | 6.050 | 19 | False | 0 | 33.27 | 32.76 |
| 12 | 0 | complete | 6.218 | 6.090 | 19 | False | 0 | 32.76 | 31.82 |
| 13 | 0 | complete | 6.624 | 6.490 | 19 | False | 0 | 31.82 | 30.23 |
| 14 | 0 | complete | 6.134 | 6.000 | 19 | False | 0 | 30.23 | 30.21 |
| 15 | 0 | complete | 6.227 | 6.090 | 19 | False | 0 | 30.21 | 29.88 |
| 16 | 0 | complete | 6.228 | 6.100 | 19 | False | 0 | 29.88 | 29.32 |
| 17 | 0 | complete | 5.964 | 5.820 | 19 | False | 0 | 29.32 | 27.88 |
| 18 | 0 | complete | 5.767 | 5.640 | 19 | False | 0 | 27.88 | 27.57 |
| 19 | 0 | complete | 5.744 | 5.610 | 19 | False | 0 | 27.57 | 27.29 |

