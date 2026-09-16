# Gate latency: pre-commit (python)

- Commit: `610e14d313e1f7d5927c5c0ae8f43ccaaf69f9af`
- Captured at: `2026-09-16T06:50:12.317143+00:00`
- Repetitions: 3
- Stdin ref line supplied: False
- Hook args: (none)
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-commit --change-class python --repetitions 3 --json .agents/metrics/gate-latency-v0.7.0/pre-commit-python.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-commit-python.md --allow-dirty
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 6230.0 seconds

n=3 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

| scope | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|
| __hook__ | 3 | 7.236 | 7.089 | 6.943 |
| branch-context-policy | 3 | 0.210 | 0.190 | 0.190 |
| branch-policy | 3 | 0.190 | 0.190 | 0.180 |
| commit-file-count | 3 | 0.200 | 0.190 | 0.190 |
| conflict-marker-policy | 3 | 0.360 | 0.310 | 0.280 |
| group (6) | 3 | 8.320 | 8.070 | 8.000 |
| infrastructure-advisory | 3 | 0.220 | 0.200 | 0.190 |
| push-lock-commit-guard | 3 | 0.080 | 0.080 | 0.080 |
| python-autofix | 3 | 0.120 | 0.110 | 0.080 |
| python-check | 3 | 0.080 | 0.080 | 0.080 |
| repair-packed-refs | 3 | 0.080 | 0.080 | 0.080 |
| repo-health | 3 | 0.080 | 0.080 | 0.080 |
| root-hygiene-policy | 3 | 0.370 | 0.290 | 0.270 |
| root-scratch-policy | 3 | 0.340 | 0.320 | 0.280 |
| scope-policy | 3 | 0.150 | 0.140 | 0.140 |
| security-suppressions-staged | 3 | 0.380 | 0.370 | 0.340 |
| subprocess-encoding | 3 | 6.200 | 6.070 | 5.920 |
| taste-advisory | 3 | 0.420 | 0.420 | 0.330 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 6.943 | 6.890 | 17 | False | 0 |
| 1 | 0 | 7.236 | 7.180 | 17 | False | 0 |
| 2 | 0 | 7.089 | 7.040 | 17 | False | 0 |

