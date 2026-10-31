# Gate latency: pre-commit (markdown)

- Commit: `c5fc0f5becf8d80666302d1c0708bbdec36fee6b`
- Captured at: `2026-10-23T22:20:49.810600+00:00`
- Repetitions: 20
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-7.0.0-38-generic-x86_64-with-glibc2.43, 48 CPUs, Python 3.14.8
- Load average: 33.60, 15.44, 8.24 (1/5/15 min); 0.70 per CPU. A loaded machine measures slower for reasons other than the gate itself (ci-scripts.md MUST-16).

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class markdown --repetitions 20 --json ../perf-6734-after-out/pre-commit-markdown.json --markdown ../perf-6734-after-out/pre-commit-markdown.md
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
| __hook__ | hook wall clock | 20 | 6.555 | 6.657 | 6.406 | 6.776 |
| agents-write-targets | job | 20 | 2.660 | 2.800 | 2.550 | 2.910 |
| branch-context-policy | job | 20 | 0.230 | 0.230 | 0.230 | 0.230 |
| branch-policy | job | 20 | 0.220 | 0.220 | 0.210 | 0.220 |
| conflict-marker-policy | job | 20 | 0.250 | 0.270 | 0.230 | 0.270 |
| context-output-check | job | 20 | 0.940 | 0.950 | 0.930 | 0.950 |
| group (14) | group total (sum) | 20 | 0.940 | 0.950 | 0.930 | 0.950 |
| group (5) | group total (sum) | 20 | 2.160 | 2.200 | 2.130 | 2.210 |
| group (6) | group total (sum) | 20 | 4.120 | 4.230 | 4.000 | 4.350 |
| infrastructure-advisory | job | 20 | 0.100 | 0.130 | 0.090 | 0.130 |
| markdown-autofix | job | 20 | 1.090 | 1.110 | 1.050 | 1.130 |
| markdown-check | job | 20 | 1.080 | 1.100 | 1.050 | 1.100 |
| push-lock-commit-guard | job | 20 | 0.070 | 0.080 | 0.070 | 0.080 |
| python-format | job | 20 | 0.060 | 0.070 | 0.030 | 0.070 |
| repair-packed-refs | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| repo-health | job | 20 | 0.070 | 0.070 | 0.070 | 0.070 |
| root-hygiene-policy | job | 20 | 0.240 | 0.260 | 0.220 | 0.270 |
| root-scratch-policy | job | 20 | 0.240 | 0.260 | 0.220 | 0.270 |
| staged-dash-policy | job | 20 | 0.240 | 0.260 | 0.220 | 0.270 |
| taste-advisory | job | 20 | 0.310 | 0.320 | 0.280 | 0.320 |

## Per-repetition runs

| repetition | exit_code | status | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count | load_before | load_after |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | complete | 6.574 | 6.480 | 19 | False | 0 | 4.59 | 5.02 |
| 1 | 0 | complete | 6.527 | 6.430 | 19 | False | 0 | 5.02 | 4.86 |
| 2 | 0 | complete | 6.635 | 6.540 | 19 | False | 0 | 4.86 | 4.50 |
| 3 | 0 | complete | 6.427 | 6.330 | 19 | False | 0 | 4.50 | 4.86 |
| 4 | 0 | complete | 6.507 | 6.410 | 19 | False | 0 | 4.86 | 4.63 |
| 5 | 0 | complete | 6.594 | 6.500 | 19 | False | 0 | 4.63 | 4.45 |
| 6 | 0 | complete | 6.657 | 6.560 | 19 | False | 0 | 4.45 | 4.98 |
| 7 | 0 | complete | 6.434 | 6.340 | 19 | False | 0 | 4.98 | 4.66 |
| 8 | 0 | complete | 6.575 | 6.480 | 19 | False | 0 | 4.66 | 4.25 |
| 9 | 0 | complete | 6.436 | 6.340 | 19 | False | 0 | 4.25 | 4.79 |
| 10 | 0 | complete | 6.608 | 6.510 | 19 | False | 0 | 4.79 | 4.73 |
| 11 | 0 | complete | 6.454 | 6.360 | 19 | False | 0 | 4.73 | 4.39 |
| 12 | 0 | complete | 6.617 | 6.520 | 19 | False | 0 | 4.39 | 64.98 |
| 13 | 0 | complete | 6.515 | 6.420 | 19 | False | 0 | 64.98 | 60.01 |
| 14 | 0 | complete | 6.571 | 6.480 | 19 | False | 0 | 60.01 | 51.17 |
| 15 | 0 | complete | 6.566 | 6.470 | 19 | False | 0 | 51.17 | 47.79 |
| 16 | 0 | complete | 6.406 | 6.310 | 19 | False | 0 | 47.79 | 44.52 |
| 17 | 0 | complete | 6.555 | 6.460 | 19 | False | 0 | 44.52 | 38.36 |
| 18 | 0 | complete | 6.776 | 6.680 | 19 | False | 0 | 38.36 | 36.09 |
| 19 | 0 | complete | 6.512 | 6.420 | 19 | False | 0 | 36.09 | 33.60 |

