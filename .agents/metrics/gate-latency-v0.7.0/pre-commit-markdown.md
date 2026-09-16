# Gate latency: pre-commit (markdown)

- Commit: `1251644ddfce00e9d6ab2a2025ebab977089e305`
- Captured at: `2026-09-16T07:29:30.689818+00:00`
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

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 3 | 9.821 | 9.662 | 9.650 |
| branch-context-policy | job | 3 | 0.200 | 0.200 | 0.200 |
| branch-policy | job | 3 | 0.210 | 0.200 | 0.190 |
| commit-file-count | job | 3 | 0.210 | 0.200 | 0.200 |
| conflict-marker-policy | job | 3 | 0.410 | 0.410 | 0.390 |
| group (5) | group total (sum) | 3 | 2.540 | 2.450 | 2.430 |
| group (6) | group total (sum) | 3 | 8.710 | 8.640 | 8.570 |
| infrastructure-advisory | job | 3 | 0.250 | 0.170 | 0.150 |
| markdown-autofix | job | 3 | 1.270 | 1.200 | 1.190 |
| markdown-check | job | 3 | 1.260 | 1.260 | 1.230 |
| push-lock-commit-guard | job | 3 | 0.080 | 0.080 | 0.080 |
| repair-packed-refs | job | 3 | 0.080 | 0.080 | 0.080 |
| repo-health | job | 3 | 0.080 | 0.080 | 0.070 |
| root-hygiene-policy | job | 3 | 0.390 | 0.380 | 0.290 |
| root-scratch-policy | job | 3 | 0.400 | 0.370 | 0.240 |
| scope-policy | job | 3 | 0.170 | 0.150 | 0.150 |
| security-suppressions-staged | job | 3 | 0.420 | 0.420 | 0.310 |
| staged-dash-policy | job | 3 | 0.400 | 0.380 | 0.370 |
| subprocess-encoding | job | 3 | 6.230 | 6.160 | 6.120 |
| taste-advisory | job | 3 | 0.430 | 0.420 | 0.400 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 9.650 | 9.600 | 19 | False | 0 |
| 1 | 0 | 9.821 | 9.770 | 19 | False | 0 |
| 2 | 0 | 9.662 | 9.610 | 19 | False | 0 |

