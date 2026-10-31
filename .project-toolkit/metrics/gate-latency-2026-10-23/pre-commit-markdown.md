# Gate latency: pre-commit (markdown)

- Commit: `0e98cb2d125635c1a7f71c7a89f70df0293a94ff`
- Captured at: `2026-10-23T04:38:58.985121+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 4.87, 4.93, 3.88 (1/5/15 min); 0.10 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class markdown --repetitions 20 --json ../perf-6734-out/pre-commit-markdown.json --markdown ../perf-6734-out/pre-commit-markdown.md
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
| __hook__ | hook wall clock | 20 | 27.851 | 28.074 | 27.596 | 28.098 |
| agents-write-targets | job | 20 | 23.980 | 24.240 | 23.750 | 24.270 |
| branch-context-policy | job | 20 | 0.230 | 0.240 | 0.230 | 0.260 |
| branch-policy | job | 20 | 0.220 | 0.220 | 0.210 | 0.250 |
| conflict-marker-policy | job | 20 | 0.250 | 0.270 | 0.230 | 0.270 |
| context-output-check | job | 20 | 0.940 | 0.950 | 0.920 | 0.950 |
| group (14) | group total (sum) | 20 | 0.940 | 0.950 | 0.920 | 0.950 |
| group (5) | group total (sum) | 20 | 2.130 | 2.180 | 2.090 | 2.270 |
| group (6) | group total (sum) | 20 | 25.430 | 25.680 | 25.200 | 25.720 |
| infrastructure-advisory | job | 20 | 0.100 | 0.130 | 0.090 | 0.130 |
| markdown-autofix | job | 20 | 1.080 | 1.100 | 1.050 | 1.120 |
| markdown-check | job | 20 | 1.060 | 1.100 | 1.020 | 1.150 |
| push-lock-commit-guard | job | 20 | 0.080 | 0.080 | 0.070 | 0.080 |
| python-format | job | 20 | 0.040 | 0.070 | 0.030 | 0.080 |
| repair-packed-refs | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.080 |
| root-hygiene-policy | job | 20 | 0.240 | 0.270 | 0.230 | 0.280 |
| root-scratch-policy | job | 20 | 0.240 | 0.260 | 0.230 | 0.270 |
| staged-dash-policy | job | 20 | 0.250 | 0.270 | 0.230 | 0.270 |
| taste-advisory | job | 20 | 0.300 | 0.320 | 0.280 | 0.330 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 28.049 | 27.950 | 19 | False | 0 | 2.80 | 3.02 |
| 1 | 0 | complete | 27.970 | 27.880 | 19 | False | 0 | 3.02 | 3.34 |
| 2 | 0 | complete | 27.762 | 27.670 | 19 | False | 0 | 3.34 | 3.55 |
| 3 | 0 | complete | 27.796 | 27.700 | 19 | False | 0 | 3.55 | 3.33 |
| 4 | 0 | complete | 28.098 | 28.000 | 19 | False | 0 | 3.33 | 3.84 |
| 5 | 0 | complete | 27.596 | 27.490 | 19 | False | 0 | 3.84 | 3.76 |
| 6 | 0 | complete | 27.913 | 27.820 | 19 | False | 0 | 3.76 | 4.25 |
| 7 | 0 | complete | 27.711 | 27.620 | 19 | False | 0 | 4.25 | 4.21 |
| 8 | 0 | complete | 27.743 | 27.650 | 19 | False | 0 | 4.21 | 4.04 |
| 9 | 0 | complete | 27.984 | 27.890 | 19 | False | 0 | 4.04 | 3.67 |
| 10 | 0 | complete | 27.605 | 27.510 | 19 | False | 0 | 3.67 | 3.36 |
| 11 | 0 | complete | 28.074 | 27.980 | 19 | False | 0 | 3.36 | 5.75 |
| 12 | 0 | complete | 28.027 | 27.930 | 19 | False | 0 | 5.75 | 5.70 |
| 13 | 0 | complete | 27.962 | 27.870 | 19 | False | 0 | 5.70 | 5.66 |
| 14 | 0 | complete | 27.843 | 27.750 | 19 | False | 0 | 5.66 | 6.40 |
| 15 | 0 | complete | 27.948 | 27.850 | 19 | False | 0 | 6.40 | 6.73 |
| 16 | 0 | complete | 27.851 | 27.760 | 19 | False | 0 | 6.73 | 6.36 |
| 17 | 0 | complete | 27.916 | 27.820 | 19 | False | 0 | 6.36 | 5.55 |
| 18 | 0 | complete | 27.713 | 27.620 | 19 | False | 0 | 5.55 | 5.98 |
| 19 | 0 | complete | 27.737 | 27.640 | 19 | False | 0 | 5.98 | 4.87 |

