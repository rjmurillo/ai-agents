---
type: requirement
id: REQ-007
title: Skill Catalog Prune M1
status: implemented
priority: P2
category: maintainability
epic: skill-catalog-health
related: []
created: 2026-05-09
updated: 2026-05-10
author: richard
---

# REQ-007: Skill Catalog Prune M1

## Requirement Statement

WHEN a developer inspects the skill catalog after M1 lands,
THE SYSTEM SHALL NOT contain `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, or `.claude/skills/workflow/` directories, and SHALL NOT expose those skills in the published `src/copilot-cli/skills/` copy,
SO THAT the catalog is free of subsumed and deprecated skills and `doc-accuracy` is the single entrypoint for documentation auditing.

## Context

`doc-accuracy` self-declares in its SKILL.md "Related Skills" table that it `**Replaced**` `doc-coverage` (Symbol extraction logic preserved in Phase 1) and `doc-sync` (Structural audit absorbed into Phase 6). Both subordinate skills remain in the repository, creating two problems: catalog confusion (developers do not know which entrypoint to use) and dead test coverage that asserts routing behavior for skills that should not exist.

`workflow` is tagged DEPRECATED in its own SKILL.md with no callers found in commands, agents, or CI. It occupies directory space and is listed in skill routing tables, adding noise.

M1 removes all three directories, updates the one cross-reference in `codebase-documenter/SKILL.md`, deletes four dead routing test cases, and regenerates the published skill copy.

## Acceptance Criteria

- [ ] REQ-007-AC1: WHEN M1 lands, THE SYSTEM SHALL NOT contain `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, or `.claude/skills/workflow/` directories SO THAT the catalog is free of subsumed and deprecated skills.
- [ ] REQ-007-AC2: WHEN `build/scripts/generate_skills.py` runs against the updated `.claude/skills/`, THE SYSTEM SHALL produce `src/copilot-cli/skills/` without `doc-coverage` or `doc-sync` entries SO THAT the published skill catalog is consistent.
- [ ] REQ-007-AC3: WHEN a developer opens `codebase-documenter/SKILL.md`, THE SYSTEM SHALL reference `doc-accuracy` (not `doc-coverage` or `doc-sync`) in the "when NOT to use" section SO THAT callers are routed correctly.
- [ ] REQ-007-AC4: WHEN `pytest tests/test_invoke_skill_learning.py` runs, THE SYSTEM SHALL exit 0 with zero references to `doc-sync` routing assertions SO THAT dead tests do not pollute the suite.
- [ ] REQ-007-AC5: WHEN `python3 build/scripts/generate_skills.py` runs from a clean working tree after M1 lands, THE SYSTEM SHALL produce zero `git diff` output (round-trip idempotent) SO THAT `.claude/skills/` and `src/copilot-cli/skills/` are demonstrably in sync. (Note: `generate_skills.py` is the canonical regenerator. There is no separate `detect_skill_drift.py`; idempotent regeneration is the verification mechanism.)

## Rationale

- Removes user confusion: `doc-accuracy` is the canonical documentation audit skill; `doc-coverage` and `doc-sync` are redundant entrypoints that should not appear in autocomplete or skill listings.
- Removes dead test assertions: four test cases in `tests/test_invoke_skill_learning.py` assert routing for `doc-sync`, which is being removed. Keeping them would produce false failures.
- Zero behavior loss: `doc-accuracy` fully subsumes the auditing functionality; `workflow` has no active callers.

## Dependencies

None. All affected files are self-contained within this repository. No external consumers of `doc-coverage` or `doc-sync` APIs have been identified.

## Deferred

These items are scoped to follow-up PRs and tracked in the parent plan
`.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md`:

- **ADR-040 amendment**: Tier 2 Sonnet enumeration in `.agents/architecture/ADR-040-skill-frontmatter-standardization.md:119` references `doc-sync`. Updated in this PR as a factual count correction; if the enumeration drifts again, route through full adr-review.
- **Eval baseline cleanup**: `tests/evals/skills/triage-prompts.json` blocks for deleted skills converted to negative-routing fixtures; full baseline regeneration is deferred to Wave 2 when the parent eval harness runs.
- **`incoherence` overlap analysis**: `doc-accuracy` Phase 6 description claims structural-audit subsumption of `incoherence`; whether `incoherence` should also be pruned is deferred to Wave 2 triage.
- **`generate_skills.py --prune` flag**: M1 manually deleted `src/copilot-cli/skills/{doc-coverage,doc-sync,workflow}` because the generator copies but does not prune. A `--prune` flag would automate this for future deletions; tracked as future work, not blocking M1.
