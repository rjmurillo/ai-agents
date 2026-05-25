# Skill Triage Eval - 2026-05-09 - PR feat/skill-eval-triage

Ran `eval-knowledge-integration.py` against 15 suspect skills in `.claude/skills/`. Targeted clusters most likely to be redundant or deprecated.

## Method

- Tool: `scripts/eval/eval-knowledge-integration.py --prompts-file tests/evals/skills/triage-prompts.json`
- Authored 6 prompts × 15 skills = 90 prompts; expected captures unique skill signal
- Each prompt scored baseline (no skill context) vs enhanced (SKILL.md + references) on accuracy/depth/specificity
- Cost: 360 API calls, ~1.26M tokens

## Result

**15/15 PASS kill gate** (delta ≥0.5). Verdict PROCEED.

But PASS measures uniqueness vs LLM baseline, NOT redundancy vs sibling skills. Pruning needs pairwise overlap analysis the eval cannot do.

## Action Slate

| Skill | Action | Why |
|---|---|---|
| doc-coverage | PRUNE | doc-accuracy SKILL.md description says it consolidates this. Lowest delta (+0.50) |
| doc-sync | PRUNE | doc-accuracy SKILL.md description says it consolidates this |
| session-qa-eligibility | FOLD | Merge into `session` umbrella (both expose Test-InvestigationEligibility) |
| session-migration | SUNSET | One-shot legacy markdown→JSON migration. Delete after complete |
| memory | DECOMPOSE | 143 KB context exceeds skill ceiling (8 KB target); split per ADR-007 tier or move to @import |
| curating-memories | INVESTIGATE | Overlap with memory-enhancement (both maintain memory quality) |
| exploring-knowledge-graph | INVESTIGATE | Lowest delta after doc-coverage (+1.11); may fold into post-decomposed memory |
| workflow | RENAME | DEPRECATED; eval pass driven by deprecation guidance content |
| memory-enhancement | KEEP | Distinct citation/code-ref/confidence scope |
| memory-documentary | KEEP | Distinct cross-source investigative purpose |
| using-forgetful-memory | KEEP | Forgetful-specific Zettelkasten guidance |
| session | KEEP | Umbrella with absorbed eligibility check |
| session-log-fixer | KEEP | High-delta CI-failure response, distinct from session-end |
| doc-accuracy | KEEP | High-delta consolidator |
| codebase-documenter | KEEP | Distinct bootstrap-only lifecycle position |

Net: 4 prunes + 2 investigates + 1 decompose + 1 rename + 7 keeps.

## Followups

1. **Wave 2 triage** for remaining 47 skills (agent-workflow, code-review, retrospective-reflect clusters likely most fruitful)
2. **Pairwise overlap eval**: current eval cannot answer "are skills A and B redundant"
3. **Memory decomposition ADR**: 143 KB outlier deserves design discussion
4. **CI cron**: run `eval-suite.py` quarterly to detect skill drift before catalog bloats again
5. **Per-cluster prune PRs**: F1 (doc), F4 (memory), F5 (session) as separate atomic PRs

## Artifacts

- `.agents/analysis/skill-triage-2026-05-09.md` - full report
- `evals/reports/skill-triage-20260509-135851/results.json` - raw scores
- `evals/reports/skill-triage-20260509-135851/run.log` - full run log
- `tests/evals/skills/triage-prompts.json` - 90 prompts authored

## Refs

- ADR-007 memory-first architecture (governs memory skill)
- ADR-034 investigation session QA exemption (governs session-qa-eligibility)
- ADR-038 reflexion memory schema (relevant to memory decomposition)
- ADR-057 prompt behavioral evaluation (governs eval-prompt-change.py)
