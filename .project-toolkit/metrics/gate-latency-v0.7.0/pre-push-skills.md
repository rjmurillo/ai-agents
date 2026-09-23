# Gate latency: pre-push (skills)

- Commit: `1251644ddfce00e9d6ab2a2025ebab977089e305`
- Captured at: `2026-09-16T07:38:11.884742+00:00`
- Repetitions: 2
- Stdin ref line supplied: True
- Hook args: ['origin', 'https://github.com/rjmurillo/ai-agents.git']
- Forced (glob filtering bypassed): False
- Host: Linux-6.18.44-fc-v33-x86_64-with-glibc2.39, 4 CPUs, Python 3.14.7

These figures describe one machine on one date. Per-job scheduling is not inferred from the per-repetition table below; read `lefthook.yml` for that (ci-scripts.md MUST-17).

## Measurement command

```
scripts/metrics/gate_latency.py --hook pre-push --change-class skills --repetitions 2 --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git --stdin-ref-line refs/heads/claude/ai-agents-goal-spec-ch26ls 1251644ddfce00e9d6ab2a2025ebab977089e305 refs/heads/claude/ai-agents-goal-spec-ch26ls 659097d6d66c5e66aab76f9f2258bf2e333ee7b8 --json .project-toolkit/metrics/gate-latency-v0.7.0/pre-push-skills.json --markdown .project-toolkit/metrics/gate-latency-v0.7.0/pre-push-skills.md --allow-dirty
```

## Change class

- `skills`: `.claude/skills/spec/SKILL.md`

## Declared vs measured

- Declared budget (`lefthook.yml` `timeout:` sum, imported unmodified from `lefthook_budget_model.declared_budget`): 3330.0 seconds

n=2 is below 20: p95 in this report is an upper-order statistic of the observed samples, not a tail estimate.

## Latency by scope

A `group (N)` row is lefthook's own total for a group, which is the sum of its members rather than wall clock, so a parallel group can report more than the whole hook took (ci-scripts.md MUST-17). Those rows are marked; scheduling comes from `lefthook.yml`, never from this arithmetic.

| scope | kind | n | worst observed of n runs | p50 | min |
|---|---|---|---|---|---|
| __hook__ | hook wall clock | 2 | 124.186 | 123.594 | 123.594 |
| additions-advisory | job | 2 | 0.360 | 0.350 | 0.350 |
| bot-cascade-advisory | job | 2 | 0.760 | 0.630 | 0.630 |
| branch-context-policy | job | 2 | 0.410 | 0.340 | 0.340 |
| branch-scope | job | 2 | 0.330 | 0.300 | 0.300 |
| count-ratchets | job | 2 | 22.890 | 22.690 | 22.690 |
| dash-prohibition | job | 2 | 0.720 | 0.680 | 0.680 |
| group (4) | group total (sum) | 2 | 1.480 | 1.290 | 1.290 |
| group (5) | group total (sum) | 2 | 37.960 | 37.350 | 37.350 |
| group (7) | group total (sum) | 2 | 127.570 | 127.410 | 127.410 |
| infrastructure-advisory | job | 2 | 0.210 | 0.160 | 0.160 |
| mutation-safety | job | 2 | 0.100 | 0.090 | 0.090 |
| path-normalization | job | 2 | 3.520 | 3.260 | 3.260 |
| placeholder-identity | job | 2 | 0.310 | 0.290 | 0.290 |
| planning-artifacts | job | 2 | 0.220 | 0.130 | 0.130 |
| plugin-load-e2e | job | 2 | 0.430 | 0.310 | 0.310 |
| pre-pr-validation | job | 2 | 92.550 | 92.040 | 92.040 |
| push-ref-policy | job | 2 | 0.970 | 0.760 | 0.760 |
| push-ref-staleness | job | 2 | 0.930 | 0.730 | 0.730 |
| python-tests | job | 2 | 14.960 | 14.870 | 14.870 |
| python-unreachable-statements | job | 2 | 10.150 | 9.140 | 9.140 |
| repair-packed-refs | job | 2 | 0.080 | 0.080 | 0.080 |
| repo-health | job | 2 | 0.080 | 0.080 | 0.080 |
| review-axis-drift | job | 2 | 0.310 | 0.200 | 0.200 |
| security-scan | job | 2 | 6.340 | 6.220 | 6.220 |
| security-suppression-policy | job | 2 | 0.230 | 0.220 | 0.220 |
| worktree-gc-report | job | 2 | 0.990 | 0.760 | 0.760 |
| zero-collection-tests | job | 2 | 17.810 | 17.790 | 17.790 |

## Per-repetition runs

| repetition | exit_code | wall_clock_seconds | lefthook_reported_seconds | jobs_parsed | tree_mutated | unknown_status_count |
|---|---|---|---|---|---|---|
| 0 | 0 | 124.186 | 124.130 | 27 | False | 0 |
| 1 | 0 | 123.594 | 123.540 | 27 | False | 0 |

