# Routing benchmark corpus

Deterministic scenarios for the #5422 routing experiment (issue #5425).
Scenarios name no model. Every strategy arm receives the same requirement.

Run the loader and every control:

```bash
uv run python scripts/eval/eval_routing_corpus.py
```

| Scenario | Category | Difficulty | Provenance |
|---|---|---|---|
| RB-01-bounded-implementation | bounded_implementation | ordinary_bounded | synthetic |
| RB-02-multi-file-invariants | multi_file_invariants | fallback_reasoning | synthetic |
| RB-03-investigate-before-edit | investigate_before_edit | fallback_reasoning | adapted from `evals/oneshot-vs-shipped/corpus/perfdiff-1265.json` |
| RB-04-scope-expansion | scope_expansion | ordinary_bounded | synthetic |
| RB-05-plausible-but-wrong | plausible_but_wrong | ordinary_bounded | adapted from `evals/reviewer-asymmetry-spike/fixtures/F001-critic-planted-issues.json` |
| RB-06-architecture-resolved | architecture_resolved | ordinary_bounded | synthetic |

Difficulty is declared before any run and is never reclassified after results.
The loader allows one scenario per category, which keeps the paid matrix bounded.

Each scenario directory holds `scenario.json`, `initial/` (driver-visible),
`hidden/` (grader-only), `known_good/`, and `known_bad/`. Files inside those
directories end in `.fixture`. The loader and grader are
`scripts/eval/_routing_scenario.py` and `scripts/eval/_routing_grader.py`.

## Scoring results

`uv run python scripts/eval/eval_routing_verdicts.py --results <jsonl> [<jsonl> ...]` applies `PREDICTIONS.md` (`predictions-v1` plus Amendment 1) to result rows and prints the H1 to H4 statuses, per arm and class tables, and the evidence-floor check as JSON. It refuses to pool `results-2026-10-03/` with later runs, and it maps the statuses to a strategy decision with the floor and mapping of Amendment 2.

## Codex results summary (2026-10-23)

Codex has produced four attempts at the routing benchmark: 2026-10-03, 2026-10-20, 2026-10-21, and 2026-10-23. All four stopped on `Your workspace is out of credits. Add credits to continue.` The 2026-10-23 attempt ran after the Codex login changed, and the cap held. The owner decided on 2026-10-23 to publish what exists and run Codex no more.

The Codex decision is `INSUFFICIENT_EVIDENCE` for H1, H2, H3, and H4. Each attempt was scored alone with `scripts/eval/eval_routing_verdicts.py`. The three new attempts are in `results-2026-10-20-partial/`, `results-2026-10-21-partial/`, and `results-2026-10-23-partial/`. Each has a README and a `verdicts.json`. They ran `codex-cli 0.163.0` with `predictions-v1` plus Amendments 1 and 2. The first attempt, `results-2026-10-03/`, ran `codex-cli 0.160.0` under the old prompt. No attempt is pooled with another.

Counts as of 2026-10-23 for the three new partial attempts only (every row is repetition 1). The 2026-10-03 attempt is reported in `results-2026-10-03/`. A row is one scenario and arm, and it holds several runner invocations: the orchestrator plan, each worker, and the integration step. `Successful invocations` counts invocations with no `failure` record, across all rows of the attempt. The status columns count rows.

| Attempt | Successful invocations | ACCEPTED | TASK_FAILED | HARNESS_FAILED | Rows |
|---|---|---|---|---|---|
| 2026-10-20 | 20 | 5 | 0 | 29 | 34 |
| 2026-10-21 | 24 | 3 | 2 | 29 | 34 |
| 2026-10-23 | 15 | 3 | 1 | 16 | 20 |

### Observations that are not verdicts

RB-01 repetition 1 is the only scenario that ran for most arms. Outcomes per arm across the three new attempts:

| Arm | 2026-10-20 | 2026-10-21 | 2026-10-23 |
|---|---|---|---|
| A | ACCEPTED | ACCEPTED | ACCEPTED |
| B | ACCEPTED | TASK_FAILED | TASK_FAILED |
| C | ACCEPTED | ACCEPTED | ACCEPTED |
| D | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED |
| E | ACCEPTED | TASK_FAILED | ACCEPTED |
| F | ACCEPTED | ACCEPTED | HARNESS_FAILED |

RB-01 alone cannot separate arms. It is one ordinary scenario, and the same arm gave different outcomes across attempts (B, E, F). Arm D never completed it. The scorer does not read this table as a verdict.

## #5426 recommendation (2026-10-23)

**Strategy decision: `INSUFFICIENT_EVIDENCE` for Codex and for Claude.** The scorer applied `predictions-v1` to each harness alone. The three Codex attempts from 2026-10-20 to 2026-10-23 ran under Amendments 1 and 2, and the 2026-10-03 attempt predates Amendment 1. The Claude run ran under Amendments 1 to 5. Results are never pooled across harnesses, so no Codex and Claude matched comparison exists.

Statuses as of 2026-10-23. Codex covers the three partial attempts and the 2026-10-03 attempt, none pooled. Claude is the run in `results-2026-10-23-claude-v2/` (72 rows: 60 ACCEPTED, 12 TASK_FAILED). `results-2026-10-23-claude-aborted/` used the grader before Amendment 5, is not pooled, and earns no floor credit.

| Hypothesis | Codex | Claude | Evidence that would move it |
|---|---|---|---|
| H1 default worker | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE (arm C has no runs) | Codex: a funded run that clears the 20 percent harness-failure limit. Claude: a Haiku 5.5 effort signal that rises strictly from low to medium to high, then arm C runs. On 2026-10-23 Haiku measured 285, 233, 337 thinking tokens, which dips at medium, so it failed the rule. |
| H2 conditional fallback | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE (arm D has no runs) | Codex: a funded run with arm D completing. Claude: a Sonnet 5.5 effort signal that rises strictly, then arm D runs. On 2026-10-23 Sonnet measured 105, 103, 105 thinking tokens, which dips and then ties, so it failed the rule. |
| H3 Opus or Sol-only fan-out | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE (neither SUPPORTED nor FALSIFIED rule holds) | Claude: arm A is non-inferior to B (15 of 18 against 14 of 18) and uses 34.9 percent fewer uncached tokens per accepted task, but only 23.5 percent less wall-clock (105.7 s against 138.2 s). A latency advantage of 25 percent would meet the bar. Codex: a funded run. |
| H4 single agent | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE (fallback evidence rule not met) | Claude: E and A both accept 6 of 6 fallback runs, so E shows no quality advantage, and A is not cheaper than E, so FALSIFIED does not hold. More fallback scenarios on which A and E differ in acceptance would move it either way. Codex: a funded run. |

### Harness guidance

- **Copilot:** UNSUPPORTED. The owner dropped it on 2026-10-03.
- **Codex:** every run stopped on the workspace credit limit after 15 to 24 successful calls in four attempts. The owner stopped Codex runs on 2026-10-23. All four hypotheses stay `INSUFFICIENT_EVIDENCE`.
- **Claude:** the run completed under Amendments 3 to 5 with 0 harness failures. Only arms A, B, E, and F are eligible. Arms C and D need Haiku 5.5 and Sonnet 5.5 effort control, which the behavioral check on 2026-10-23 did not verify. Effort evidence is `behavioral`, which shows that the flag changes behavior and never shows which value was served.

### Decision

No routing change is supported by the pre-registered result. No policy implementation issue is filed, because #5426 says to file exactly one issue only if the evidence supports shipped changes.

The Claude run records one observation that is not a verdict: on the fallback scenarios arm E matched arm A's acceptance at 29.7 percent of the wall-clock and 24.8 percent of the uncached tokens. The scorer does not read it. See `results-2026-10-23-claude-v2/README.md`.
