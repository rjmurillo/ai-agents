# Gate latency: pre-push (python)

- Commit: `1251644ddfce00e9d6ab2a2025ebab977089e305`
- Captured at: `2026-09-16T07:46:32.592090+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class python --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 1251644ddfce00e9d6ab2a2025ebab977089e305 refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .project-toolkit/metrics/gate-latency-v0.7.0/pre-push-python.json --markdown .project-toolkit/metrics/gate-latency-v0.7.0/pre-push-python.md --allow-dirty
```

## Change class

- `python`: `scripts/ci/lefthook_budget_model.py`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 2 | 124.106 | 123.995 | 123.995 |
| additions-advisory | job | 2 | 0.410 | 0.380 | 0.380 |
| bot-cascade-advisory | job | 2 | 0.730 | 0.700 | 0.700 |
| branch-context-policy | job | 2 | 0.370 | 0.360 | 0.360 |
| branch-scope | job | 2 | 0.320 | 0.200 | 0.200 |
| count-ratchets | job | 2 | 23.300 | 22.970 | 22.970 |
| dash-prohibition | job | 2 | 0.720 | 0.710 | 0.710 |
| group (4) | group total (sum) | 2 | 1.590 | 1.430 | 1.430 |
| group (5) | group total (sum) | 2 | 38.300 | 37.030 | 37.030 |
| group (7) | group total (sum) | 2 | 127.820 | 127.710 | 127.710 |
| infrastructure-advisory | job | 2 | 0.130 | 0.120 | 0.120 |
| mutation-safety | job | 2 | 0.090 | 0.090 | 0.090 |
| path-normalization | job | 2 | 3.570 | 3.190 | 3.190 |
| placeholder-identity | job | 2 | 0.320 | 0.320 | 0.320 |
| planning-artifacts | job | 2 | 0.140 | 0.120 | 0.120 |
| pre-pr-validation | job | 2 | 92.060 | 91.870 | 91.870 |
| push-ref-policy | job | 2 | 1.050 | 0.870 | 0.870 |
| push-ref-staleness | job | 2 | 0.920 | 0.680 | 0.680 |
| python-lint-advisory | job | 2 | 0.070 | 0.060 | 0.060 |
| python-tests | job | 2 | 15.100 | 14.770 | 14.770 |
| python-type-check | job | 2 | 0.460 | 0.390 | 0.390 |
| python-unreachable-statements | job | 2 | 10.040 | 8.760 | 8.760 |
| repair-packed-refs | job | 2 | 0.080 | 0.080 | 0.080 |
| repo-health | job | 2 | 0.090 | 0.080 | 0.080 |
| review-axis-drift | job | 2 | 0.300 | 0.260 | 0.260 |
| security-scan | job | 2 | 6.400 | 6.240 | 6.240 |
| security-suppression-policy | job | 2 | 0.240 | 0.230 | 0.230 |
| worktree-gc-report | job | 2 | 0.900 | 0.900 | 0.900 |
| zero-collection-tests | job | 2 | 18.290 | 18.200 | 18.200 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 123.995 | 123.940 | 28 | False | 0 |
| 1 | 0 | 124.106 | 124.040 | 28 | False | 0 |

