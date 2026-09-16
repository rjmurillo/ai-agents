# Gate latency: pre-commit (markdown)

- Commit: `610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af`
- Captured at: `2026-09-16T06:49:50.651500+00:00`
- Repetitions: 3
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class markdown --repetitions 3 --json .agents/metrics/gate-latency-v0.7.0/pre-commit-markdown.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-commit-markdown.md --allow-dirty
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 6230.0 seconds

n=3 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

| scope | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|
| __hook__ | 3 | 3.768 | 3.744 | 3.629 |
| branch-context-policy | 3 | 0.210 | 0.200 | 0.180 |
| branch-policy | 3 | 0.200 | 0.200 | 0.190 |
| commit-file-count | 3 | 0.200 | 0.190 | 0.190 |
| conflict-marker-policy | 3 | 0.320 | 0.310 | 0.270 |
| group (5) | 3 | 2.400 | 2.370 | 2.300 |
| group (6) | 3 | 1.510 | 1.510 | 1.500 |
| infrastructure-advisory | 3 | 0.140 | 0.110 | 0.100 |
| markdown-autofix | 3 | 1.190 | 1.180 | 1.160 |
| markdown-check | 3 | 1.210 | 1.190 | 1.150 |
| push-lock-commit-guard | 3 | 0.080 | 0.080 | 0.070 |
| repair-packed-refs | 3 | 0.080 | 0.080 | 0.080 |
| repo-health | 3 | 0.080 | 0.080 | 0.080 |
| root-hygiene-policy | 3 | 0.260 | 0.230 | 0.220 |
| root-scratch-policy | 3 | 0.300 | 0.290 | 0.290 |
| scope-policy | 3 | 0.150 | 0.150 | 0.140 |
| staged-dash-policy | 3 | 0.270 | 0.240 | 0.220 |
| taste-advisory | 3 | 0.330 | 0.310 | 0.300 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 3.768 | 3.720 | 17 | False | 0 |
| 1 | 0 | 3.744 | 3.690 | 17 | False | 0 |
| 2 | 0 | 3.629 | 3.580 | 17 | False | 0 |

