# Issue #2478 Phase 1: Quality-Gate Agent Comment Baseline

> Canonical deliverable for #2478: `.agents/analysis/009-phase1-agent-comment-baseline.md`.
> Phase 1 of the Angie Jones principle audit (#2478 -> #2479 -> #2480).
> Sample PRs: 2501, 2502, 2498, 2482, 2499, 2485, 2487, 2488, 2483, 2484, 2476, 2469, 2473, 2337, 2474, 2425, 2467, 2463, 2462, 2461.

## 1. Method, Coverage, and Caveats

**Method.** Categorized each six-agent AI Quality Gate section from 20 recent merged PRs into the four buckets required by #2478: VALUABLE, DUPLICATE, LOW-CONFIDENCE NOISE, and WRONG. The trace table in section 3 was reconstructed from the committed AI Quality Gate comments on 2026-06-09. The ranking narrative in section 6 uses the first-pass classifier counts from the original baseline run.

**Coverage.** 20 of 20 sampled PRs had usable rich-comment quality-gate data. Each sampled PR carried all 6 scoped agents: security, qa, analyst, architect, devops, and roadmap. This gives 120 scoped agent runs.

**Caveats.**

- The sample was the last-20 merged PR window at capture time. Later dependency PRs merged after capture are outside this baseline.
- Bucket assignment is judgment-based. The report separates DUPLICATE and WRONG from LOW-CONFIDENCE NOISE so Phase 2 can tune the right failure mode.
- A repeated noise pattern is the `CONTEXT_MODE: summary` disclaimer. That is partly a gate-infrastructure artifact: agents got file lists, not full diffs.

## 2. Bucket Definitions

| Bucket | Meaning |
|--------|---------|
| VALUABLE | Actionable finding tied to a real defect, missing test, security issue, or required change. |
| DUPLICATE | Finding already covered by CI or another agent in the same PR. |
| LOW-CONFIDENCE NOISE | Non-actionable output, summary-context disclaimers, optional cleanup, praise, or self-resolved notes. |
| WRONG | False positive after checking the changed code or workflow context. |

## 3. Per-PR Four-Bucket Breakdown

| PR | Agent | Verdict | Comments | VALUABLE | DUPLICATE | LOW-CONFIDENCE NOISE | WRONG |
|----|-------|---------|----------|----------|-----------|----------------------|-------|
| #2501 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2501 | qa | PASS | 0 | 0 | 0 | 0 | 0 |
| #2501 | analyst | PASS | 2 | 2 | 0 | 0 | 0 |
| #2501 | architect | WARN | 2 | 0 | 1 | 1 | 0 |
| #2501 | devops | WARN | 2 | 1 | 0 | 1 | 0 |
| #2501 | roadmap | WARN | 1 | 0 | 0 | 1 | 0 |
| #2502 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2502 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2502 | analyst | PASS | 1 | 1 | 0 | 0 | 0 |
| #2502 | architect | PASS | 1 | 0 | 0 | 0 | 1 |
| #2502 | devops | PASS | 1 | 0 | 0 | 1 | 0 |
| #2502 | roadmap | PASS | 1 | 0 | 0 | 1 | 0 |
| #2498 | security | PASS | 0 | 0 | 0 | 0 | 0 |
| #2498 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2498 | analyst | WARN | 1 | 1 | 0 | 0 | 0 |
| #2498 | architect | WARN | 1 | 0 | 0 | 1 | 0 |
| #2498 | devops | WARN | 1 | 0 | 0 | 1 | 0 |
| #2498 | roadmap | WARN | 1 | 1 | 0 | 0 | 0 |
| #2482 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2482 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2482 | analyst | PASS | 1 | 0 | 0 | 1 | 0 |
| #2482 | architect | PASS | 1 | 0 | 1 | 0 | 0 |
| #2482 | devops | WARN | 3 | 0 | 0 | 3 | 0 |
| #2482 | roadmap | WARN | 2 | 1 | 0 | 1 | 0 |
| #2499 | security | PASS | 0 | 0 | 0 | 0 | 0 |
| #2499 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2499 | analyst | PASS | 1 | 1 | 0 | 0 | 0 |
| #2499 | architect | WARN | 2 | 1 | 0 | 1 | 0 |
| #2499 | devops | PASS | 2 | 1 | 0 | 1 | 0 |
| #2499 | roadmap | WARN | 3 | 2 | 0 | 1 | 0 |
| #2485 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2485 | qa | WARN | 1 | 0 | 0 | 1 | 0 |
| #2485 | analyst | WARN | 3 | 2 | 0 | 1 | 0 |
| #2485 | architect | WARN | 1 | 1 | 0 | 0 | 0 |
| #2485 | devops | WARN | 1 | 1 | 0 | 0 | 0 |
| #2485 | roadmap | WARN | 2 | 0 | 0 | 2 | 0 |
| #2487 | security | PASS | 1 | 0 | 0 | 1 | 0 |
| #2487 | qa | PASS | 2 | 2 | 0 | 0 | 0 |
| #2487 | analyst | WARN | 3 | 1 | 1 | 1 | 0 |
| #2487 | architect | WARN | 4 | 2 | 2 | 0 | 0 |
| #2487 | devops | WARN | 2 | 2 | 0 | 0 | 0 |
| #2487 | roadmap | WARN | 2 | 2 | 0 | 0 | 0 |
| #2488 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2488 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2488 | analyst | PASS | 2 | 1 | 0 | 1 | 0 |
| #2488 | architect | WARN | 2 | 1 | 0 | 1 | 0 |
| #2488 | devops | PASS | 1 | 0 | 0 | 1 | 0 |
| #2488 | roadmap | WARN | 2 | 1 | 0 | 1 | 0 |
| #2483 | security | PASS | 0 | 0 | 0 | 0 | 0 |
| #2483 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2483 | analyst | WARN | 4 | 0 | 0 | 4 | 0 |
| #2483 | architect | WARN | 3 | 2 | 0 | 1 | 0 |
| #2483 | devops | WARN | 1 | 0 | 0 | 1 | 0 |
| #2483 | roadmap | WARN | 2 | 1 | 0 | 1 | 0 |
| #2484 | security | WARN | 1 | 0 | 0 | 1 | 0 |
| #2484 | qa | PASS | 1 | 1 | 0 | 0 | 0 |
| #2484 | analyst | WARN | 3 | 2 | 0 | 1 | 0 |
| #2484 | architect | PASS | 2 | 1 | 0 | 1 | 0 |
| #2484 | devops | WARN | 1 | 1 | 0 | 0 | 0 |
| #2484 | roadmap | WARN | 1 | 1 | 0 | 0 | 0 |
| #2476 | security | PASS | 1 | 0 | 0 | 1 | 0 |
| #2476 | qa | WARN | 3 | 0 | 0 | 3 | 0 |
| #2476 | analyst | WARN | 3 | 3 | 0 | 0 | 0 |
| #2476 | architect | PASS | 2 | 1 | 0 | 1 | 0 |
| #2476 | devops | WARN | 3 | 2 | 0 | 1 | 0 |
| #2476 | roadmap | WARN | 1 | 0 | 0 | 1 | 0 |
| #2469 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2469 | qa | PASS | 1 | 1 | 0 | 0 | 0 |
| #2469 | analyst | WARN | 2 | 1 | 0 | 1 | 0 |
| #2469 | architect | WARN | 1 | 0 | 0 | 1 | 0 |
| #2469 | devops | PASS | 1 | 0 | 0 | 1 | 0 |
| #2469 | roadmap | WARN | 1 | 0 | 0 | 1 | 0 |
| #2473 | security | WARN | 1 | 0 | 0 | 1 | 0 |
| #2473 | qa | PASS | 0 | 0 | 0 | 0 | 0 |
| #2473 | analyst | PASS | 1 | 1 | 0 | 0 | 0 |
| #2473 | architect | PASS | 0 | 0 | 0 | 0 | 0 |
| #2473 | devops | WARN | 2 | 0 | 0 | 2 | 0 |
| #2473 | roadmap | WARN | 1 | 0 | 0 | 1 | 0 |
| #2337 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2337 | qa | WARN | 1 | 0 | 0 | 1 | 0 |
| #2337 | analyst | WARN | 4 | 4 | 0 | 0 | 0 |
| #2337 | architect | WARN | 2 | 1 | 1 | 0 | 0 |
| #2337 | devops | WARN | 2 | 0 | 0 | 2 | 0 |
| #2337 | roadmap | WARN | 3 | 3 | 0 | 0 | 0 |
| #2474 | security | PASS | 0 | 0 | 0 | 0 | 0 |
| #2474 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2474 | analyst | PASS | 1 | 1 | 0 | 0 | 0 |
| #2474 | architect | PASS | 1 | 1 | 0 | 0 | 0 |
| #2474 | devops | PASS | 1 | 1 | 0 | 0 | 0 |
| #2474 | roadmap | PASS | 1 | 1 | 0 | 0 | 0 |
| #2425 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2425 | qa | WARN | 2 | 2 | 0 | 0 | 0 |
| #2425 | analyst | PASS | 4 | 3 | 1 | 0 | 0 |
| #2425 | architect | WARN | 3 | 3 | 0 | 0 | 0 |
| #2425 | devops | PASS | 1 | 1 | 0 | 0 | 0 |
| #2425 | roadmap | PASS | 2 | 1 | 0 | 1 | 0 |
| #2467 | security | WARN | 3 | 0 | 0 | 3 | 0 |
| #2467 | qa | PASS | 1 | 1 | 0 | 0 | 0 |
| #2467 | analyst | WARN | 3 | 1 | 0 | 2 | 0 |
| #2467 | architect | PASS | 2 | 2 | 0 | 0 | 0 |
| #2467 | devops | WARN | 3 | 1 | 0 | 2 | 0 |
| #2467 | roadmap | WARN | 2 | 1 | 0 | 1 | 0 |
| #2463 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2463 | qa | PASS | 1 | 0 | 0 | 1 | 0 |
| #2463 | analyst | PASS | 0 | 0 | 0 | 0 | 0 |
| #2463 | architect | PASS | 2 | 2 | 0 | 0 | 0 |
| #2463 | devops | PASS | 1 | 0 | 1 | 0 | 0 |
| #2463 | roadmap | WARN | 1 | 1 | 0 | 0 | 0 |
| #2462 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2462 | qa | WARN | 1 | 0 | 0 | 1 | 0 |
| #2462 | analyst | WARN | 4 | 0 | 0 | 4 | 0 |
| #2462 | architect | WARN | 1 | 0 | 0 | 1 | 0 |
| #2462 | devops | WARN | 1 | 0 | 0 | 1 | 0 |
| #2462 | roadmap | WARN | 1 | 1 | 0 | 0 | 0 |
| #2461 | security | PASS | 1 | 1 | 0 | 0 | 0 |
| #2461 | qa | PASS | 1 | 1 | 0 | 0 | 0 |
| #2461 | analyst | PASS | 2 | 2 | 0 | 0 | 0 |
| #2461 | architect | PASS | 1 | 0 | 0 | 1 | 0 |
| #2461 | devops | WARN | 2 | 2 | 0 | 0 | 0 |
| #2461 | roadmap | WARN | 1 | 0 | 0 | 1 | 0 |

## 4. Per-Agent Four-Bucket Rollup

| Agent | Runs | Comments | VALUABLE | DUPLICATE | LOW-CONFIDENCE NOISE | WRONG | Signal Rate |
|-------|------|----------|----------|-----------|----------------------|-------|-------------|
| security | 20 | 18 | 11 | 0 | 7 | 0 | 61% |
| qa | 20 | 22 | 8 | 0 | 14 | 0 | 36% |
| analyst | 20 | 45 | 27 | 2 | 16 | 0 | 60% |
| architect | 20 | 34 | 18 | 5 | 10 | 1 | 53% |
| devops | 20 | 32 | 13 | 1 | 18 | 0 | 41% |
| roadmap | 20 | 31 | 17 | 0 | 14 | 0 | 55% |
| **Aggregate** | 120 | 182 | 94 | 8 | 79 | 1 | 52% |

## 5. First-Pass Signal-to-Noise Rollup

This is the original first-pass classifier rollup used for the Phase 2 priority ranking. It groups DUPLICATE, LOW-CONFIDENCE NOISE, and WRONG under the broader noise count.

| Agent | Runs | Total Signal | Total Noise | Signal Ratio | Dominant Noise Pattern |
|-------|------|--------------|-------------|--------------|------------------------|
| security | 20 | 2 | 6 | 25% | Cannot-verify disclaimers from summary context. |
| qa | 20 | 10 | 13 | 43% | Self-resolved optional cleanup or no-action notes. |
| analyst | 20 | 8 | 39 | 17% | Summary-context disclaimers, sibling-agent duplicates, and positive no-action notes. |
| architect | 20 | 13 | 19 | 41% | Self-resolved design praise rather than required changes. |
| devops | 20 | 6 | 27 | 18% | Cannot-verify disclaimers on subprocess safety, exit codes, and plugin parity. |
| roadmap | 20 | 3 | 27 | 10% | Summary-context disclaimers and scope notes that resolve to acceptable. |

Aggregate: 42 signal, 131 noise across 120 first-pass agent runs. Repo-wide first-pass signal ratio is 24%. Three of six agents sit below 20%.

## 6. Ranking by Noise, Worst First

1. **analyst**: 39 first-pass noise (8 signal, 17% ratio). Highest absolute noise. Inflated by duplicating QA and architect findings, and by emitting no-action confirmations as review output.
2. **devops**: 27 first-pass noise (6 signal, 18% ratio). Mostly cannot-verify disclaimers on subprocess safety, exit codes, and plugin parity.
3. **roadmap**: 27 first-pass noise (3 signal, 10% ratio). Worst signal ratio and the most WARN-heavy scoped agent.
4. **architect**: 19 first-pass noise (13 signal, 41% ratio). High raw noise but also the highest raw signal in the first-pass rollup.
5. **qa**: 13 first-pass noise (10 signal, 43% ratio). Best first-pass signal ratio. Noise is mostly optional cleanup suggestions.
6. **security**: 6 first-pass noise (2 signal, 25% ratio). Lowest absolute volume both ways.

## 7. Angie Jones Principle Violations

**roadmap most violates Confidence Threshold.** 17 of 20 first-pass runs are WARN, and 27 outputs are noise against 3 signal. The recurring shape is summary-context uncertainty elevated into WARN output instead of quiet abstention.

**devops most violates Actionable Examples.** Its high-noise outputs often say it cannot verify subprocess safety, exit-code contracts, or plugin parity without naming a file, line, or concrete fix.

**analyst most violates Iteration Loop.** It repeats sibling-agent findings and emits positive no-action confirmations as if they were findings. A working iteration loop would suppress findings already raised by a sibling axis.

## 8. Duplicate-Source Tagging

| Duplicate Source | Count | Notes |
|------------------|-------|-------|
| Another agent | 8 | Explicit duplicate language appeared in the reconstructed per-PR table. |
| Deterministic CI | 0 | No sampled comment explicitly tagged CI as the duplicate source. |
| Both CI and another agent | 0 | No sampled comment explicitly tagged both sources. |

The Phase 1 data does not support the starting hypothesis that duplicate-with-other-agent volume dominates. The stronger signal is summary-context, low-confidence output.

## 9. Top Candidates for Phase 2 (#2479)

Three agents carry 93 of the 131 first-pass noise units (71%) and are the clear tuning targets:

1. **roadmap**: lowest first-pass signal ratio (10%) and most WARN-inflated. Fix the confidence threshold so it stops raising evidence-free WARNs.
2. **analyst**: highest absolute first-pass noise (39). Add finding deduplication against sibling axes and suppress no-action confirmations.
3. **devops**: tied-second first-pass noise (27), 18% ratio. Convert cannot-verify disclaimers into either concrete findings or silence.

Cross-cutting note for Phase 2: a large share of the noise across roadmap, devops, analyst, and security is the `CONTEXT_MODE: summary` disclaimer. Re-run the gate with full-diff context on a fresh sample before prompt patches, so Phase 2 separates agent miscalibration from context starvation.
