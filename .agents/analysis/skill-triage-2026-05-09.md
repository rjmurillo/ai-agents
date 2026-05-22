# Skill Triage Report 2026-05-09

## Scope

Evaluated 15 suspect skills in `.claude/skills/` via `eval-knowledge-integration.py` against built-in Anthropic API baseline. Goal: identify pruning and consolidation candidates among skills with high redundancy risk (deprecated, multiple overlapping siblings).

Run: `evals/reports/skill-triage-20260509-135851/`. Cost: 360 API calls, ~1.26M tokens.

## Method

Each skill scored on 6 prompt+expected pairs in two conditions:

- **Baseline**: prompt only, no skill context
- **Enhanced**: prompt + SKILL.md + references/

LLM judge graded responses 1-5 on accuracy, depth, specificity. Kill gate threshold: delta >= 0.5, no regression.

## Aggregate Verdict

**15/15 PASS.** Kill gate: PROCEED. Every skill provides knowledge baseline LLM lacks.

| Skill                       | Base | Enh  |  Delta | Ctx KB |
| --------------------------- | ---: | ---: | -----: | -----: |
| doc-coverage                | 3.67 | 4.17 |  +0.50 |    7.5 |
| exploring-knowledge-graph   | 3.50 | 4.61 |  +1.11 |    5.1 |
| curating-memories           | 3.33 | 4.61 |  +1.28 |    5.8 |
| codebase-documenter         | 3.00 | 4.33 |  +1.33 |   11.7 |
| doc-sync                    | 2.89 | 4.39 |  +1.50 |   19.1 |
| memory-enhancement          | 2.78 | 4.44 |  +1.67 |   27.1 |
| session-qa-eligibility      | 2.95 | 4.78 |  +1.83 |    8.5 |
| session-migration           | 2.78 | 4.61 |  +1.83 |   10.1 |
| using-forgetful-memory      | 2.22 | 4.22 |  +2.00 |    8.3 |
| workflow                    | 2.00 | 4.11 |  +2.11 |    5.9 |
| memory-documentary          | 2.56 | 4.67 |  +2.11 |   12.0 |
| session-log-fixer           | 2.11 | 4.50 |  +2.39 |   23.1 |
| doc-accuracy                | 2.50 | 4.89 |  +2.39 |    8.5 |
| session                     | 2.17 | 4.61 |  +2.44 |    8.9 |
| memory                      | 1.78 | 4.61 |  +2.83 |  143.6 |

## Critical Caveat

PASS verdict measures **uniqueness vs LLM defaults**, not **redundancy with sibling skills**. A skill can pass this gate while still being subsumed by a peer. Pruning decisions require pairwise overlap analysis the eval does not perform.

## Findings

### F1. doc-accuracy explicitly subsumes doc-coverage and doc-sync

`doc-accuracy` SKILL.md description (verbatim): "Consolidates incoherence, doc-coverage, doc-sync, and comment-analyzer into a single workflow."

Eval scores reinforce: `doc-accuracy` delta +2.39 (highest in doc cluster); `doc-coverage` delta +0.50 (lowest in entire triage, threshold-grazing); `doc-sync` delta +1.50 (mid). Authors of `doc-accuracy` themselves declared the subsumption.

**Recommendation: prune doc-coverage + doc-sync; route callers to doc-accuracy.** Keep `incoherence` (separate skill, also referenced in doc-accuracy description but provides distinct phase).

### F2. memory skill is 143.6 KB - exceeds passive context threshold

`memory` skill bundles all 4-tier memory documentation per ADR-007. Eval delta +2.83 (highest), but context size 143 KB is 18x the typical 8 KB skill ceiling.

**Recommendation: decompose `memory` into per-tier skills** (semantic, episodic, causal) OR move bulk to passive context (CLAUDE.md @import) with skill reduced to a thin router. ADR-038 reflexion memory schema research relevant.

### F3. workflow skill PASSED despite DEPRECATED label

Description: "DEPRECATED: Workflow commands replaced by lifecycle commands". Eval delta +2.11.

Pass driven by skill content explaining the deprecation and migration path. Skill IS providing real signal: callers attempting to use legacy workflow get correct redirect to /spec /plan /build /test /review /ship.

**Recommendation: keep `workflow` as deprecation guide.** Rename to `workflow-deprecation-notice` or fold contents into a one-paragraph CLAUDE.md note + delete skill.

### F4. memory cluster: 6 skills, possible internal redundancy

| Skill                     | Delta | Ctx KB | Distinct purpose claim                  |
| ------------------------- | ----: | -----: | --------------------------------------- |
| memory                    | +2.83 |  143.6 | 4-tier umbrella                         |
| memory-documentary        | +2.11 |   12.0 | Investigative reports w/ citations      |
| memory-enhancement        | +1.67 |   27.1 | Citations, code refs, confidence scores |
| using-forgetful-memory    | +2.00 |    8.3 | Forgetful-specific guidance             |
| curating-memories         | +1.28 |    5.8 | Update/obsolete/link memories           |
| exploring-knowledge-graph | +1.11 |    5.1 | Deep traversal across memories          |

`memory-enhancement` and `curating-memories` overlap in scope: both maintain memory quality. Enhancement = metadata; curating = content. Distinction is fine-grained and may not justify two skills.

`exploring-knowledge-graph` has lowest delta (+1.11) and overlaps `memory` umbrella's Tier 1 semantic search.

**Recommendation: pairwise overlap analysis needed.** Likely consolidation: `memory-enhancement` + `curating-memories` -> single `memory-curation` skill. `exploring-knowledge-graph` + `memory` Tier 1 docs -> consolidate into `memory` skill (after F2 decomposition).

### F5. session cluster: 4 skills measured, distinct purposes

| Skill                  | Delta | Purpose                                    |
| ---------------------- | ----: | ------------------------------------------ |
| session                | +2.44 | Umbrella for ADR-034 eligibility checks    |
| session-qa-eligibility | +1.83 | Specific check for ADR-034 paths           |
| session-migration      | +1.83 | Markdown to JSON conversion (one-time use) |
| session-log-fixer      | +2.39 | Repair CI session validation failures      |

`session-qa-eligibility` and `session` umbrella overlap: both expose Test-InvestigationEligibility. Two skills for one operation.

`session-migration` is one-shot legacy work. After all logs migrated, skill becomes dead code.

**Recommendation:**

- Fold `session-qa-eligibility` into `session` umbrella (eliminate one skill).
- Mark `session-migration` for deletion when historical migration complete; track via issue.
- Keep `session-log-fixer` (distinct CI-failure response purpose, high delta).

### F6. doc cluster: codebase-documenter has narrow lifecycle position

`codebase-documenter` (delta +1.33): bootstrap-only, used once per project.

Not redundant with `doc-accuracy` (verification of existing docs) or `doc-sync` (index maintenance). Distinct lifecycle phase.

**Recommendation: keep `codebase-documenter`.** Document its one-shot positioning to prevent confusion with doc-* maintenance skills.

## Prune / Consolidate Slate

| Skill                     | Action      | Rationale                                                     |
| ------------------------- | ----------- | ------------------------------------------------------------- |
| doc-coverage              | PRUNE       | doc-accuracy explicitly consolidates it. Lowest delta (+0.50) |
| doc-sync                  | PRUNE       | doc-accuracy explicitly consolidates it                       |
| session-qa-eligibility    | FOLD        | Merge into `session` umbrella                                 |
| session-migration         | SUNSET      | One-shot legacy work; delete after migration completes        |
| memory                    | DECOMPOSE   | 143 KB exceeds skill ceiling; split per-tier or to @imports   |
| curating-memories         | INVESTIGATE | Overlap with memory-enhancement; pairwise comparison needed   |
| exploring-knowledge-graph | INVESTIGATE | Lowest delta (1.11); may fold into post-decomposed memory     |
| workflow                  | RENAME      | Deprecated; rename to `workflow-deprecation-notice` or delete |
| memory-enhancement        | KEEP        | Distinct citation/freshness scope                             |
| memory-documentary        | KEEP        | Distinct cross-source investigative purpose                   |
| using-forgetful-memory    | KEEP        | Forgetful-specific atomic memory guidance                     |
| session                   | KEEP        | Umbrella with absorbed eligibility check                      |
| session-log-fixer         | KEEP        | High-delta CI-failure response                                |
| doc-accuracy              | KEEP        | High-delta consolidator                                       |
| codebase-documenter       | KEEP        | Distinct bootstrap lifecycle position                         |

Net: 4 prunes (doc-coverage, doc-sync, session-qa-eligibility, session-migration). 2 investigations. 1 decomposition. 1 rename. 7 keeps.

## Followups

1. **Pairwise overlap eval** for memory-enhancement vs curating-memories, exploring-knowledge-graph vs memory Tier 1. Current eval cannot answer.
2. **Wave 2 triage** for remaining 47 skills. Suggested clusters: agent-workflow, code-review, retrospective-reflect, session-* siblings not in this run.
3. **Memory skill decomposition ADR**. 143 KB context warrants design discussion.
4. **CI cron for eval-suite.py**. Run quarterly to detect skill drift before catalog bloats again.
5. **Pruning PR**. Implement F1 + F4 + F5 in separate atomic PRs to allow per-cluster rollback.

## References

- `evals/reports/skill-triage-20260509-135851/results.json` - raw scores
- `evals/reports/skill-triage-20260509-135851/run.log` - full run log
- `tests/evals/skills/triage-prompts.json` - 90 prompts authored for this triage
- `scripts/eval/eval-knowledge-integration.py` - evaluator
- `scripts/eval/README.md` - eval infra catalog
- ADR-007 - memory-first architecture (governs `memory` skill)
- ADR-034 - investigation session QA exemption (governs `session-qa-eligibility`)
- ADR-038 - reflexion memory schema (relevant to F2)
- ADR-057 - prompt behavioral evaluation (governs eval-prompt-change.py, complementary)
