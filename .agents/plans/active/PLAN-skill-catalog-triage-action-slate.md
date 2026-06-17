# Execution Plan: Skill Catalog Triage Action Slate

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-09 |
| **Owner** | engineering |
| **Complexity** | Medium |
| **Source** | `.agents/analysis/skill-triage-2026-05-09.md` |
| **Eval run** | `evals/reports/skill-triage-20260509-135851/` |
| **Eval cost** | 360 API calls, ~1.26M tokens |

## Context

Skill eval (session-1825) ran `eval-knowledge-integration.py` against 15 suspect skills. All 15 PASS the kill gate (delta ≥ 0.5 vs LLM baseline). However, PASS measures uniqueness vs baseline, not redundancy vs siblings. Three skills surfaced as clear prune candidates via self-declared subsumption or deprecated status.

**Critical caveat**: Pairwise overlap eval (Issue #1932) is needed for the INVESTIGATE cluster. That work is blocked until the eval infra ships.

## Action Slate

### Tier 1: PRUNE/RENAME/SUNSET (No ADR needed, low risk)

| # | Skill | Action | Evidence | Status |
|---|-------|--------|----------|--------|
| 1 | `doc-coverage` <!-- orphan-ref-ignore --> | PRUNE | `doc-accuracy/SKILL.md` "Related Skills" table: `**Replaced**: Symbol extraction logic preserved in Phase 1`. Lowest delta (+0.50). | `[ ]` pending |
| 2 | `doc-sync` <!-- orphan-ref-ignore --> | PRUNE | `doc-accuracy/SKILL.md` "Related Skills" table: `**Replaced**: Structural audit absorbed into Phase 6`. | `[ ]` pending |
| 3 | `workflow` | PRUNE (delete) | DEPRECATED in SKILL.md. No callers in commands/agents/CI. | `[ ]` pending |
| 4 | `session-qa-eligibility` <!-- orphan-ref-ignore --> | FOLD into `session` | Both expose `Test-InvestigationEligibility`. Delta +1.83. | `[ ]` pending |
| 5 | `session-migration` <!-- orphan-ref-ignore --> | SUNSET (audit first) | One-shot md→json work. Verify no remaining .md logs before delete. | `[ ]` pending |

**M1 (doc-coverage + doc-sync + workflow)**: Spec written in session-1825. REQ/DESIGN/TASK TBD (in-progress).

**M2 (session-qa-eligibility + session-migration)**: Not yet specced. Plan after M1 lands.

### Tier 2: DECOMPOSE (ADR required)

| # | Skill | Action | Evidence | Status |
|---|-------|--------|----------|--------|
| 6 | `memory` | DECOMPOSE | 143 KB context = 18× skill ceiling. ADR needed per "Ask First" gate. | `[ ]` blocked on ADR |

**Blocker**: Architecture change requires ADR per AGENTS.md. Draft ADR for memory decomposition before speccing.

### Tier 3: INVESTIGATE (Blocked on #1932 eval infra)

| # | Skill | Action | Evidence | Blocked by |
|---|-------|--------|----------|-----------|
| 7 | `curating-memories` | INVESTIGATE overlap with memory-enhancement | Both maintain memory quality. Delta +1.28. | Issue #1932 |
| 8 | `exploring-knowledge-graph` | INVESTIGATE overlap with memory Tier 1 | Lowest meaningful delta (+1.11). | Issue #1932 |

### Tier 4: KEEP (Validated, no action)

| Skill | Delta | Reason |
|-------|-------|--------|
| `memory-enhancement` | +1.67 | Distinct citation/code-ref/confidence scope |
| `memory-documentary` | +2.11 | Distinct cross-source investigative purpose |
| `using-forgetful-memory` | +2.00 | Forgetful-specific Zettelkasten guidance |
| `session` | +2.44 | Umbrella, absorbs session-qa-eligibility |
| `session-log-fixer` | +2.39 | Distinct CI-failure response, high delta |
| `doc-accuracy` | +2.39 | High-delta consolidator of pruned skills |
| `codebase-documenter` | +1.33 | Distinct bootstrap-only lifecycle position |

## Milestones

| Milestone | Scope | Blocking | Status |
|-----------|-------|----------|--------|
| **M1**: Prune doc-coverage + doc-sync + workflow | Low-risk deletions only | Nothing | Spec in progress |
| **M2**: Fold session-qa-eligibility + sunset session-migration | Session cluster consolidation | M1 optional | Not started |
| **M3**: memory decomposition | ADR-led architecture | ADR draft | Blocked on ADR |
| **M4**: Investigate memory cluster overlap | Pairwise eval | Issue #1932 eval infra | Live verdicts landed 2026-06-17: Pair 1 KEEP, Pair 2 REWRITE boundary |
| **Wave 2**: Remaining 47 skills | Full catalog | M1-M4 learnings | Not started |

## Dependencies

```
#1932 (eval-skill-overlap.py) → M4 (curating-memories / exploring-knowledge-graph)
ADR (memory decomposition) → M3 (memory skill split)
M1 (prune doc-coverage/doc-sync/workflow) → optional gate for M2 (shows process works)
Wave 2 triage → M1-M4 learnings + quarterly CI cron
```

## Objectives

- [x] Run baseline eval against 15 suspect skills (session-1825, commit 6d94d2eb)
- [x] Produce triage report with action slate (.agents/analysis/skill-triage-2026-05-09.md)
- [x] Create GitHub issue for pairwise overlap eval (#1932)
- [ ] Spec M1: PRD produced in session-1825 (requirements-interview complete)
- [ ] Spec M1: REQ/DESIGN/TASK artifacts written to .agents/specs/
- [ ] Implement M1: PR deleting doc-coverage + doc-sync + workflow skills
- [ ] Spec M2: session-qa-eligibility fold + session-migration sunset
- [ ] Implement M2: PR consolidating session cluster
- [ ] ADR: memory skill decomposition approach
- [ ] Spec M3: memory skill decomposition PRD
- [ ] Implement M3: memory cluster refactor
- [ ] Implement #1932: eval-skill-overlap.py + Phase 1 (4 known pairs)
- [x] Run M4: overlap eval on curating-memories / exploring-knowledge-graph (live run 2026-06-17, `.agents/analysis/skill-overlap-2026-06-17.md`)
- [ ] Wave 2: triage remaining 47 skills

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-09 | Start with 15 suspect skills only, not full 70-skill sweep | Cost/time proportionality. Suspect cluster has highest redundancy signal. | Full 70-skill sweep (~$30, 2hr) deferred to after M1-M4 learnings |
| 2026-05-09 | PASS = keep for all 15 evaluated skills | All delta ≥ 0.5 vs baseline. But PASS ≠ non-redundant vs sibling. Pruning requires pairwise eval (Issue #1932) or self-declared subsumption evidence. | Pure LLM judgment (no evidence rigor); rejected |
| 2026-05-09 | M1 scope = doc-coverage + doc-sync + workflow ONLY (not session or memory) | doc-accuracy self-declares consolidation; workflow explicitly deprecated. Session and memory require deeper analysis. | Include session-qa-eligibility in M1; rejected (different mechanism, adds risk) |
| 2026-05-09 | `workflow` action = PRUNE (delete), not KEEP-as-deprecation-guide | Source analysis (`.agents/analysis/skill-triage-2026-05-09.md` F3) recommended keeping `workflow` as a deprecation guide pointing to lifecycle commands. M1 spec reversed this: the SKILL.md was already DEPRECATED with no callers, and a deprecation guide adds catalog noise without surfacing in routing. The migration table in `docs/workflow-commands.md` is preserved and serves as the canonical map (legacy phase → lifecycle slash command). | KEEP as deprecation guide (analysis F3 recommendation); rejected because deprecation guides accumulate as zombie skills; the migration table in `docs/workflow-commands.md` is the documentation surface that survives the prune |
| 2026-05-09 | M3 memory decomposition requires ADR-first | AGENTS.md "Ask First" gate for architecture changes. 143 KB skill is architectural concern. | Skip ADR; rejected (governance) |
| 2026-05-09 | Issue #1932 filed for pairwise eval infra | Current eval-knowledge-integration.py cannot answer "are A and B redundant." Separate PR/issue for new evaluator. | Extend existing script; deferred (design needed) |
| 2026-06-05 | M4 pairwise overlap eval wired and dry-run validated; live verdict pending credentials (Issue #1949) | `eval-skill-overlap.py` landed on main and ran a dry-run over the two M4 pairs (`curating-memories` x `memory-enhancement`, `exploring-knowledge-graph` x `memory` Tier-1): 96 calls, ~$3.02. The live run that produces the per-pair OVERLAP/DISTINCT/SUBSUMED verdict needs `ANTHROPIC_API_KEY`, absent in the build environment. Pairs file and methodology are recorded in `.agents/analysis/skill-overlap-2026-06-05.md`. No FOLD or KEEP decision is final until the live run executes. | Hand-curate verdicts without running the evaluator; rejected (no evidence, violates the evidence-rigor rule the plan adopted on 2026-05-09) |
| 2026-06-17 | M4 live verdicts (Issue #1949): Pair 1 DISTINCT (KEEP both), Pair 2 SUBSUMED but moderate band (REWRITE boundary, do NOT delete). | Live scored run executed with `ANTHROPIC_API_KEY` from repo-root `.env`, model `claude-sonnet-4-6`, run id `m4-overlap-1949-2026-06-17`. Pair 1 `curating-memories` x `memory-enhancement` = DISTINCT (deltas +0.00 / -0.75; neither covers the other; matches pre-registered hypothesis). Pair 2 `exploring-knowledge-graph` x `memory` = SUBSUMED with `memory` the covering skill (on exploring's prompts memory recovers +0.75 of exploring's +1.25 = 60% one-way coverage; on memory's prompts exploring lags +1.00 vs +3.00). 60% sits in the issue's 50-80% moderate band, which routes to SKILL.md boundary rewrite + routing re-check, NOT delete/FOLD. AC1-AC3, AC6 satisfied. AC4 (FOLD PR) not triggered. AC5 (boundary statements) recommended for both pairs as a separate follow-up. Full analysis: `.agents/analysis/skill-overlap-2026-06-17.md`; artifacts: `evals/reports/overlap-m4-overlap-1949-2026-06-17/`. | Delete `exploring-knowledge-graph` on the bare SUBSUMED label; rejected (60% one-way coverage on a single 4-prompt run is moderate-band evidence; deletion needs a confirmatory rewrite-then-eval pass, per the evidence-rigor rule). Hand-curate without re-running; not needed, the live run executed. |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-09 | Created plan from skill triage session-1825 | Claude Opus 4.7 |
| 2026-05-09 | 15 suspect skills evaluated via eval-knowledge-integration.py. 15/15 PASS. Action slate confirmed. | Claude Opus 4.7 |
| 2026-05-09 | Issue #1932 created for pairwise overlap eval feature | Claude Opus 4.7 |
| 2026-05-09 | M1 spec PRD produced via requirements-interview. Awaiting REQ/DESIGN/TASK formalization. | Claude Opus 4.7 |

## Blockers

1. ~~**Issue #1949** (live overlap eval): Blocks final M4 verdicts until credentials are available.~~ RESOLVED 2026-06-17: live run executed (key present in repo-root `.env`). Verdicts: Pair 1 KEEP (DISTINCT), Pair 2 REWRITE boundary (SUBSUMED, moderate band). Follow-up: SKILL.md boundary statements for both pairs (AC5), then a confirmatory Pair 2 eval before any delete/FOLD.
2. **ADR: memory decomposition**: Blocks M3. Owner: engineering (needs design discussion).

## References

- `.agents/analysis/skill-triage-2026-05-09.md` - source triage analysis
- `.agents/analysis/skill-overlap-2026-06-05.md` - M4 dry-run evidence and pair list
- `evals/reports/skill-triage-20260509-135851/` - raw eval scores
- `tests/evals/skills/triage-prompts.json` - eval scenarios
- `scripts/eval/eval-knowledge-integration.py` - evaluator
- `scripts/eval/eval-skill-overlap.py` - pairwise overlap evaluator
- Issue #1932 - pairwise overlap eval feature
- Issue #1949 - live overlap eval credential blocker
- Session-1825 log: `.agents/sessions/2026-05-09-session-1825.json`
