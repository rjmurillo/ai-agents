---
type: requirement
id: REQ-006
title: Skill Catalog Prune M1
status: draft
priority: medium
category: maintainability
epic: skill-catalog-health
related: []
author: richard
---

# REQ-006: Skill Catalog Prune M1

## Requirement Statement

WHEN a developer inspects the skill catalog after M1 lands,
THE SYSTEM SHALL NOT contain `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, or `.claude/skills/workflow/` directories, and SHALL NOT expose those skills in the published `src/copilot-cli/skills/` copy,
SO THAT the catalog is free of subsumed and deprecated skills and `doc-accuracy` is the single entrypoint for documentation auditing.

## Context

`doc-accuracy` self-declares in its SKILL.md (lines 248-249) that it consolidates `doc-coverage` and `doc-sync`. Both subordinate skills remain in the repository, creating two problems: catalog confusion (developers do not know which entrypoint to use) and dead test coverage that asserts routing behavior for skills that should not exist.

`workflow` is tagged DEPRECATED in its own SKILL.md with no callers found in commands, agents, or CI. It occupies directory space and is listed in skill routing tables, adding noise.

M1 removes all three directories, updates the one cross-reference in `codebase-documenter/SKILL.md`, deletes four dead routing test cases, and regenerates the published skill copy.

## Acceptance Criteria

- [ ] REQ-006-AC1: WHEN M1 lands, THE SYSTEM SHALL NOT contain `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, or `.claude/skills/workflow/` directories SO THAT the catalog is free of subsumed and deprecated skills.
- [ ] REQ-006-AC2: WHEN `build/scripts/generate_skills.py` runs against the updated `.claude/skills/`, THE SYSTEM SHALL produce `src/copilot-cli/skills/` without `doc-coverage` or `doc-sync` entries SO THAT the published skill catalog is consistent.
- [ ] REQ-006-AC3: WHEN a developer opens `codebase-documenter/SKILL.md`, THE SYSTEM SHALL reference `doc-accuracy` (not `doc-coverage` or `doc-sync`) in the "when NOT to use" section SO THAT callers are routed correctly.
- [ ] REQ-006-AC4: WHEN `pytest tests/test_invoke_skill_learning.py` runs, THE SYSTEM SHALL exit 0 with zero references to `doc-sync` routing assertions SO THAT dead tests do not pollute the suite.
- [ ] REQ-006-AC5: WHEN the pre-push drift detection hook runs after M1 lands, THE SYSTEM SHALL report zero drift between `.claude/skills/` and `src/copilot-cli/skills/` SO THAT CI drift detection confirms catalog consistency.

## Rationale

- Removes user confusion: `doc-accuracy` is the canonical documentation audit skill; `doc-coverage` and `doc-sync` are redundant entrypoints that should not appear in autocomplete or skill listings.
- Removes dead test assertions: four test cases in `tests/test_invoke_skill_learning.py` assert routing for `doc-sync`, which is being removed. Keeping them would produce false failures.
- Zero behavior loss: `doc-accuracy` fully subsumes the auditing functionality; `workflow` has no active callers.

## Dependencies

None. All affected files are self-contained within this repository. No external consumers of `doc-coverage` or `doc-sync` APIs have been identified.
