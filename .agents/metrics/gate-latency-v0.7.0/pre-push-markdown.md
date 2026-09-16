# Gate latency: pre-push (markdown)

- Commit: `1251644ddfce00e9d6ab2a2025ebab977089e305`
- Captured at: `2026-09-16T07:34:03.749168+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class markdown --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 1251644ddfce00e9d6ab2a2025ebab977089e305 refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .agents/metrics/gate-latency-v0.7.0/pre-push-markdown.json --markdown .agents/metrics/gate-latency-v0.7.0/pre-push-markdown.md --allow-dirty
```

## Change class

- `markdown`: `README.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 2 | 126.162 | 124.561 | 124.561 |
| additions-advisory | job | 2 | 0.310 | 0.230 | 0.230 |
| bot-cascade-advisory | job | 2 | 0.680 | 0.610 | 0.610 |
| branch-context-policy | job | 2 | 0.400 | 0.350 | 0.350 |
| branch-scope | job | 2 | 0.290 | 0.280 | 0.280 |
| count-ratchets | job | 2 | 23.680 | 23.160 | 23.160 |
| dash-prohibition | job | 2 | 0.770 | 0.750 | 0.750 |
| group (4) | group total (sum) | 2 | 1.320 | 1.320 | 1.320 |
| group (5) | group total (sum) | 2 | 39.990 | 37.750 | 37.750 |
| group (7) | group total (sum) | 2 | 129.260 | 127.560 | 127.560 |
| infrastructure-advisory | job | 2 | 0.280 | 0.150 | 0.150 |
| mutation-safety | job | 2 | 0.100 | 0.090 | 0.090 |
| path-normalization | job | 2 | 3.450 | 3.430 | 3.430 |
| placeholder-identity | job | 2 | 0.300 | 0.290 | 0.290 |
| planning-artifacts | job | 2 | 0.170 | 0.160 | 0.160 |
| pre-pr-validation | job | 2 | 93.800 | 92.630 | 92.630 |
| push-ref-policy | job | 2 | 0.800 | 0.800 | 0.800 |
| push-ref-staleness | job | 2 | 0.740 | 0.680 | 0.680 |
| python-tests | job | 2 | 15.200 | 14.750 | 14.750 |
| python-unreachable-statements | job | 2 | 11.060 | 9.230 | 9.230 |
| repair-packed-refs | job | 2 | 0.080 | 0.080 | 0.080 |
| repo-health | job | 2 | 0.090 | 0.080 | 0.080 |
| review-axis-drift | job | 2 | 0.310 | 0.250 | 0.250 |
| security-scan | job | 2 | 6.440 | 6.330 | 6.330 |
| security-suppression-policy | job | 2 | 0.230 | 0.220 | 0.220 |
| worktree-gc-report | job | 2 | 0.880 | 0.810 | 0.810 |
| zero-collection-tests | job | 2 | 18.310 | 18.180 | 18.180 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 126.162 | 126.110 | 26 | False | 0 |
| 1 | 0 | 124.561 | 124.500 | 26 | False | 0 |

