# Skill Overlap Report: m4-overlap-1949-2026-06-17

Model: `claude-sonnet-4-6`

Pairwise skill overlap analysis (Issue #1932). Verdicts: DISTINCT (keep both), OVERLAP (fold candidate), SUBSUMED (prune candidate).

## Prune / Fold Table

| Skill A | Skill B | Verdict | A_delta | B_delta | Recommendation |
|---------|---------|---------|---------|---------|----------------|
| curating-memories | memory-enhancement | DISTINCT | +0.00 | -0.75 | Keep both. curating-memories and memory-enhancement cover different prompts. |
| exploring-knowledge-graph | memory | SUBSUMED | +1.25 | +3.00 | Script classification: SUBSUMED (moderate-band, 60% one-way coverage). Triage action: rewrite boundary + confirmatory eval; deletion not triggered on this evidence. |

## Per-Pair Detail

### curating-memories vs memory-enhancement: DISTINCT

- curating-memories on its own prompts: baseline 5.00, own 5.00 (delta +0.00), cross 5.00 (delta +0.00).
- memory-enhancement on its own prompts: baseline 3.75, own 3.00 (delta -0.75), cross 2.50 (delta -1.25).
- Recommendation: Keep both. curating-memories and memory-enhancement cover different prompts.

### exploring-knowledge-graph vs memory: SUBSUMED

- exploring-knowledge-graph on its own prompts: baseline 3.25, own 4.50 (delta +1.25), cross 4.00 (delta +0.75).
- memory on its own prompts: baseline 1.25, own 4.25 (delta +3.00), cross 2.25 (delta +1.00).
- Recommendation: Script classification: SUBSUMED (moderate-band, 60% one-way coverage). Triage action: rewrite boundary + confirmatory eval; deletion not triggered on this evidence.
