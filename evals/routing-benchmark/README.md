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

Counts as of 2026-10-23, rows by status per attempt (every row is repetition 1):

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
