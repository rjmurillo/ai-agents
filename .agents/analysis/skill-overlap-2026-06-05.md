# Skill Overlap Analysis (M4) - 2026-06-05

Issue: #1949 (M4 pairwise overlap eval). Parent epic: #1944. Blocking infra: #1932.

## Scope

Run the pairwise overlap evaluator (`scripts/eval/eval-skill-overlap.py`, landed
from #1932) on the two INVESTIGATE-tier pairs from the M1 triage
(`.agents/analysis/skill-triage-2026-05-09.md`, Tier 3), then record a triage
decision per pair.

| Pair | Facet under test | Triage signal |
|------|------------------|---------------|
| `curating-memories` x `memory-enhancement` | Both maintain memory quality. curating-memories edits entry content; memory-enhancement edits operational metadata (confidence, citations, freshness). | curating-memories delta +1.28, memory-enhancement delta +1.67 vs baseline |
| `exploring-knowledge-graph` x `memory` (Tier 1) | Both answer "what do you know about X". exploring-knowledge-graph walks relation edges across hops; memory Tier-1 ranks entries by semantic similarity. | exploring-knowledge-graph delta +1.11 (lowest meaningful delta in the suspect cluster) |

## Methodology (from #1932)

For each pair (A, B) and each prompt, three conditions run: `baseline` (prompt
only), `skill_A` (prompt + A's SKILL.md context), `skill_B` (prompt + B's
context). Each response is scored 1-5 against the prompt's expected answer by an
LLM judge. The per-direction deltas produce a pair verdict:

- `DISTINCT`: each skill helps mainly on its own native prompts.
- `OVERLAP`: both skills help symmetrically on both prompt sets.
- `SUBSUMED`: one skill helps on both prompt sets while the other does not.

The verdict maps to the issue's triage decision tree: high overlap (>=80%) FOLD
the lower-delta skill into the higher-delta one; moderate (50-80%) rewrite
SKILL.md boundaries; low (<50%) KEEP both and document the boundary.

## Inputs

Pairs file: `scripts/eval/examples/overlap-pairs-issue-1949.json`. Four native
prompts per skill, derived from each SKILL.md. Pair 2 uses
`exploring-knowledge-graph` x `memory`, matching the issue AC, not the
`example-overlap-pairs.json` second pair (`curating-memories` x
`exploring-knowledge-graph`), which predates this issue.

## Evidence

Dry-run (no API calls; validates both pairs, confirms all four skills resolve,
estimates cost):

```
$ python3 scripts/eval/eval-skill-overlap.py \
    --pairs scripts/eval/examples/overlap-pairs-issue-1949.json --dry-run
Cost estimate: 96 API calls, ~336,000 tokens, ~$3.02 USD (pricing as of 2026-05-03)
Dry run: 2 pair(s) validated, no API calls made.
exit: 0
```

Live run status: BLOCKED on credentials. The build environment has no
`ANTHROPIC_API_KEY`, so the evaluator exits external (3) before any judge call:

```
$ python3 scripts/eval/eval-skill-overlap.py \
    --pairs scripts/eval/examples/overlap-pairs-issue-1949.json
ERROR (external): ANTHROPIC_API_KEY not found in environment or repo-root .env file.
```

## Boundary hypotheses (pre-registered, to be confirmed or refuted by the live run)

These are the expected verdicts based on a read of each SKILL.md. They are not
the result. Recording them before the run guards against fitting the
interpretation to whatever number comes back.

- `curating-memories` x `memory-enhancement`: expect `DISTINCT`. They share the
  word "memory quality" but split cleanly: content projection (curating) vs
  operational metadata as its own system of record (enhancement). The
  data-intensive-applications rule already names this as two separate
  consistency models. If the run shows OVERLAP, the descriptions are leaking and
  need a boundary rewrite, not a fold.
- `exploring-knowledge-graph` x `memory` (Tier 1): higher overlap risk. Both
  match "what do you know about X". The honest distinction is traversal depth:
  semantic search (memory Tier 1) is the entry point; relation-edge walking
  (exploring-knowledge-graph) is the deep path. If the judge cannot separate the
  two on the native prompts, the likely action is a SKILL.md boundary rewrite
  (moderate overlap), with FOLD reserved for >=80% overlap.

## Decision per pair

PENDING the live run. No FOLD (AC4) or KEEP-with-boundary-rewrite (AC5) decision
is final without the per-pair OVERLAP/DISTINCT/SUBSUMED verdict and its delta
numbers. Hand-curating a verdict from the SKILL.md text alone would violate the
evidence-rigor rule the parent plan adopted on 2026-05-09 (Decision Log: "PASS
!= non-redundant vs sibling; pruning requires pairwise eval"). When run, append
the verdict table and the resulting decision to this file.

## Reproduce

```
python3 scripts/eval/eval-skill-overlap.py \
  --pairs scripts/eval/examples/overlap-pairs-issue-1949.json
```

Report artifacts land under `evals/reports/`. Add the per-pair verdicts and the
final triage decision to the "Decision per pair" section above once the live run
completes.

## References

- Issue #1949 - M4 pairwise overlap eval
- Issue #1932 - eval-skill-overlap.py infrastructure
- `scripts/eval/eval-skill-overlap.py` - the evaluator
- `scripts/eval/examples/overlap-pairs-issue-1949.json` - the pairs and prompts
- `.agents/analysis/skill-triage-2026-05-09.md` - source triage (Tier 3 rows)
- `.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md` - M4 row and Decision Log
