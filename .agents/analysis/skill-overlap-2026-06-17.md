# Skill Overlap Analysis (M4 live run) - 2026-06-17

Issue: #1949 (M4 pairwise overlap eval). Parent epic: #1944. Blocking infra: #1932 (shipped via PR #2336).

This is the live scored run that the 2026-06-05 dry-run (`.agents/analysis/skill-overlap-2026-06-05.md`) left pending on credentials. The `ANTHROPIC_API_KEY` was present in the repo-root `.env`, so the evaluator ran end to end. The dry-run file stays as the methodology record; this file carries the verdicts.

## Run metadata

- Evaluator: `scripts/eval/eval-skill-overlap.py`
- Pairs file: `scripts/eval/examples/overlap-pairs-issue-1949.json`
- Model (generation and judge): `claude-sonnet-4-6`
- Run id: `m4-overlap-1949-2026-06-17`
- Artifacts: `evals/reports/overlap-m4-overlap-1949-2026-06-17/REPORT.md` and `matrix.json`
- Cost: 96 API calls, 2 pairs x 4 prompts x 2 directions x (baseline + skill_A + skill_B). Estimate ~$3.02.

## How to read the numbers

Per prompt set, the harness scores three conditions on a 1 to 5 scale: `baseline` (no skill), `own` (the owning skill's context), `other` (the sibling's context). `own_delta = own - baseline`; `other_delta = other - baseline`. The verdict (`scripts/eval/eval-skill-overlap.py:classify_overlap`) uses a help threshold of 0.5:

- A direction "is covered" when the sibling helps (`other_delta >= 0.5`) AND lands within 0.5 of the owner (`own_delta - other_delta <= 0.5`).
- Both directions covered: OVERLAP (fold candidate).
- Exactly one direction covered: SUBSUMED (prune candidate, the covering skill is the broader one).
- Neither: DISTINCT (keep both).

## Verdicts

| Pair | Verdict | A_delta (own) | B_delta (own) | Script recommendation |
|------|---------|---------------|---------------|-----------------------|
| `curating-memories` x `memory-enhancement` | DISTINCT | +0.00 | -0.75 | Keep both. Cover different prompts. |
| `exploring-knowledge-graph` x `memory` | SUBSUMED | +1.25 | +3.00 | Prune candidate. One covers the other without reciprocity. |

## Pair 1: curating-memories x memory-enhancement -> DISTINCT (KEEP both)

Raw scores:

- On `curating-memories` prompts: baseline 5.00, own 5.00 (+0.00), other 5.00 (+0.00).
- On `memory-enhancement` prompts: baseline 3.75, own 3.00 (-0.75), other 2.50 (-1.25).

Reading. The verdict matches the 2026-06-05 pre-registered hypothesis (expected DISTINCT). Neither skill covers the other: on the curating prompts the base model already scores a perfect 5.00 so no skill can add lift, and on the enhancement prompts neither skill clears the +0.5 help bar (both deltas are negative). The two skills split cleanly along the line the `data-intensive-applications` rule already draws: curating-memories edits memory content (a projection of source artifacts), memory-enhancement edits operational metadata (confidence, citations, freshness) as its own system of record.

One honest caveat. The DISTINCT verdict here is driven by "no skill helped on these prompts" (a ceiling on curating's set, negative deltas on enhancement's set), not by "each skill strongly helped on its own set and not the other." So the verdict is "do not fold," which is correct and final for M4, but it is weaker evidence of richness than a both-positive DISTINCT would be. The negative enhancement deltas suggest the four enhancement prompts may be answerable by the base model without the skill; that is a knowledge-integration (skill-vs-baseline) question, not an overlap question, and is out of M4 scope. No action beyond KEEP.

Action (AC5): add an explicit boundary statement to both SKILL.md files so routing stays crisp (content curation vs operational-metadata maintenance). This is a low-risk text change; it is queued as a follow-up, not landed in this analysis PR, to keep the eval artifact and the skill edits in separate reviewable commits.

## Pair 2: exploring-knowledge-graph x memory -> SUBSUMED (prune candidate, but moderate band: rewrite boundary, do not delete yet)

Raw scores:

- On `exploring-knowledge-graph` prompts: baseline 3.25, own 4.50 (+1.25), other(memory) 4.00 (+0.75).
- On `memory` prompts: baseline 1.25, own 4.25 (+3.00), other(exploring) 2.25 (+1.00).

Reading. The SUBSUMED verdict resolves as follows. On exploring's own prompts, `memory` recovers most of the lift (+0.75 vs exploring's +1.25), so `memory` covers exploring's prompts. On memory's own prompts, exploring lags badly (+1.00 vs memory's +3.00), so exploring does NOT cover memory's prompts. Exactly one direction covers, so the covering (broader) skill is `memory` and the covered (prune-candidate) skill is `exploring-knowledge-graph`. This direction matches the 2026-06-05 hypothesis that Pair 2 carried the higher overlap risk.

Why this is NOT an automatic delete. The issue's triage tree keys the action on overlap magnitude: >=80% high overlap FOLD/delete, 50 to 80% moderate REWRITE boundary, <50% low KEEP. The one-directional coverage here is `memory`'s +0.75 against exploring's +1.25 on exploring's prompts, 60% recovery. That sits in the moderate band, not the high band. A 60% one-way coverage says the two skills are close on graph-traversal prompts, not that `memory` fully replaces `exploring-knowledge-graph`. Deleting exploring-knowledge-graph on a single 4-prompt run at 60% coverage would be the "confident incorrectness" failure the canonical-source-mirror rule and the parent plan's evidence-rigor decision (2026-05-09) warn against.

The asymmetry is itself the design signal. `memory` is the unified four-tier router; its Tier 1 semantic search overlaps the entry phase of `exploring-knowledge-graph`. But exploring's multi-hop relation walk is what the base model is worst at (memory's own prompts start at baseline 1.25 and exploring only lifts them to 2.25, while memory lifts them to 4.25). So the genuine, defensible boundary is: `memory` owns the flat "what do you know about X" recall (Tier 1 semantic search), `exploring-knowledge-graph` owns the deep multi-hop relation traversal. Today both SKILL.md descriptions claim the "what do you know about X" phrasing, which is the leak that produced the 60% cross-coverage.

Action (AC5, recommended): rewrite the two SKILL.md descriptions to make the boundary explicit (memory = Tier 1 flat recall and the tier router; exploring-knowledge-graph = multi-hop relation traversal beyond Tier 1), then verify routing with a follow-up eval. Defer the DELETE/FOLD decision until a confirmatory run on the rewritten descriptions shows whether the cross-coverage drops below the 50% KEEP line (boundary rewrite worked) or stays above 80% (then exploring-knowledge-graph becomes a real fold candidate into memory's deep tier). AC4 (the FOLD spec triplet + implementation PR) is therefore NOT triggered by this run.

## Acceptance criteria status

- AC1 (curating x enhancement scored): DONE. DISTINCT, structured matrix at `evals/reports/overlap-m4-overlap-1949-2026-06-17/matrix.json`.
- AC2 (exploring x memory scored): DONE. SUBSUMED, same matrix.
- AC3 (analysis report with per-pair triage): DONE. This file.
- AC4 (FOLD spec + impl PR): NOT TRIGGERED. Pair 1 is KEEP. Pair 2 is moderate-band SUBSUMED, which the tree routes to boundary rewrite, not FOLD. No FOLD PR is warranted on this evidence.
- AC5 (KEEP -> SKILL.md boundary statements): RECOMMENDED for both pairs. Queued as a separate follow-up PR (skill text edits), not bundled with this eval-artifact PR, per the canonical-source-mirror and refactoring one-hat-per-commit conventions.
- AC6 (plan Decision Log updated): DONE. See `.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md` Decision Log entry dated 2026-06-17.

## Limitations (honest)

- Single run, 4 prompts per skill, no repeat-sampling. The verdicts are point estimates from one judge pass at temperature defaults. A delta of 0.5 is one judge point on one prompt out of four; the confidence interval is wide. The Pair 2 boundary-rewrite recommendation is robust to this (it is the conservative action), but a DELETE would not be.
- Prompts are derived from each SKILL.md, so they favor each skill's framing. That is the intended design of the harness (native prompts), but it means the eval measures "does the sibling cover the owner's framed task," not "does either skill win real user traffic."
- The judge and the generator are the same model family. Self-grading bias is possible. Out of scope to correct here; flagged for whoever runs the confirmatory Pair 2 rewrite eval.

## Reproduce

```
set -a; . .env; set +a
python3 scripts/eval/eval-skill-overlap.py \
  --pairs scripts/eval/examples/overlap-pairs-issue-1949.json \
  --run-id m4-overlap-1949-rerun
```

## References

- Issue #1949 (M4 pairwise overlap eval)
- Issue #1932 (eval-skill-overlap.py infrastructure, shipped PR #2336)
- `.agents/analysis/skill-overlap-2026-06-05.md` (dry-run + methodology + pre-registered hypotheses)
- `scripts/eval/eval-skill-overlap.py` (the evaluator; `classify_overlap` is the verdict unit)
- `scripts/eval/examples/overlap-pairs-issue-1949.json` (pairs and native prompts)
- `evals/reports/overlap-m4-overlap-1949-2026-06-17/` (REPORT.md, matrix.json)
- `.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md` (M4 row, Decision Log)
