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

Each scenario directory holds `scenario.json`, `initial/` (driver-visible),
`hidden/` (grader-only), `known_good/`, and `known_bad/`. Files inside those
directories end in `.fixture`. The loader and grader are
`scripts/eval/_routing_scenario.py` and `scripts/eval/_routing_grader.py`.
