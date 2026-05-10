---
type: task
id: TASK-007
title: Skill Catalog Prune M1
status: done
priority: P2
complexity: S
estimate: 4
created: 2026-05-09
updated: 2026-05-10
related:
  - DESIGN-007
  - REQ-007
blocked_by: []
blocks: []
assignee: claude-opus-4-7
---

# TASK-007: Skill Catalog Prune M1

## Design Context

Implements DESIGN-007 (Skill Catalog Prune M1). The design rationale: `doc-accuracy` self-declares in its `Related Skills` table that it `**Replaced**` `doc-coverage` (Symbol extraction logic preserved in Phase 1) and `doc-sync` (Structural audit absorbed into Phase 6). The `workflow` skill is DEPRECATED in its own SKILL.md with no callers in commands, agents, or CI. This task subtracts the three subsumed skills to reduce catalog cognitive load, with zero behavior loss for callers (consolidation paths documented in `doc-accuracy/SKILL.md` and the `docs/workflow-commands.md` migration table).

## Objective

Remove three deprecated skill directories, update one cross-reference, delete four dead test cases, and regenerate the published copilot-cli skill copy. All work is subtractive; no new code is written.

## In Scope

- Delete `.claude/skills/doc-coverage/`
- Delete `.claude/skills/doc-sync/`
- Delete `.claude/skills/workflow/`
- Delete `src/copilot-cli/skills/doc-coverage/` (published copy)
- Delete `src/copilot-cli/skills/doc-sync/` (published copy)
- Update `codebase-documenter/SKILL.md` "when NOT to use" section (replace `doc-coverage`/`doc-sync` references with `doc-accuracy`)
- Update `src/copilot-cli/skills/codebase-documenter/SKILL.md` (same edit, published copy)
- Delete four `doc-sync` routing test cases from `tests/test_invoke_skill_learning.py` (lines 370-394)

## Out of Scope

- Adding replacement routing test cases for `doc-accuracy`
- session-qa-eligibility fold or memory decomposition (separate milestones; tracked under epic #1944)
- Automated redirection shim

## Updated post-merge (2026-05-10)

The original "Out of Scope" list excluded `doc-accuracy` SKILL.md and `tests/evals/skills/triage-prompts.json`. Both were updated in this PR:

- `doc-accuracy/SKILL.md` description reworded from present-tense "Consolidates X" to past-tense "replaced the former X (deleted 2026-05-09)" after `/pr-quality:all` adversarial review surfaced the staleness. Same change mirrored to the `src/copilot-cli/skills/` published copy and to `docs/SKILL-AUTHORING.md` per the canonical-source-mirror rule.
- `tests/evals/skills/triage-prompts.json` had its workflow/doc-coverage/doc-sync expected-answer blocks reframed as negative-routing fixtures so the evaluator scores correctly when an agent encounters an old-name reference.

Both changes are remediations driven by the adversarial review and the merge with main; neither expands the prune scope itself.

## Acceptance Criteria

- [x] TASK-007-AC1: `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, `.claude/skills/workflow/` do not exist after the PR lands. Verified via `git ls-tree -r HEAD -- .claude/skills/` returning zero matches for the three names.
- [x] TASK-007-AC2: `src/copilot-cli/skills/doc-coverage/` and `src/copilot-cli/skills/doc-sync/` do not exist after the PR lands. Verified via `git ls-tree -r HEAD -- src/copilot-cli/skills/` returning zero matches.
- [x] TASK-007-AC3: `codebase-documenter/SKILL.md` and its published copy contain `doc-accuracy` (not `doc-coverage` or `doc-sync`) in the "when NOT to use" section. Verified by inspection at commit `07ec8553`.
- [x] TASK-007-AC4: `pytest tests/test_invoke_skill_learning.py` exits 0 with no `doc-sync` routing assertions present. Verified locally via `.venv/bin/python3 -m pytest tests/` at HEAD: 8323 passed, 0 failed, 3 skipped.
- [x] TASK-007-AC5: `python3 build/scripts/generate_skills.py` exits 0 from a clean working tree and produces no diff (round-trip idempotent), confirming `.claude/skills/` and `src/copilot-cli/skills/` agree. (Mechanism updated to match REQ-007-AC5; the prior `build_all.py --platform copilot-cli` invocation produced the same effect through a different entrypoint.)
- [x] TASK-007-AC6: `validate_marketplace_counts.py` reports zero drift between `.claude-plugin/marketplace.json` (67 skills), `.github/plugin/marketplace.json` (79 skills), and the actual skill directory contents. Verified locally via `python3 build/scripts/validate_marketplace_counts.py` at commit `eecf83f3`.

## Files Affected

| File | Action | Description |
|---|---|---|
| `.claude/skills/doc-coverage/` | DELETE | Source skill directory (SKILL.md + scripts/check_docs.py) |
| `.claude/skills/doc-sync/` | DELETE | Source skill directory (SKILL.md + references/) |
| `.claude/skills/workflow/` | DELETE | Source skill directory (SKILL.md + modules/ + scripts/) |
| `src/copilot-cli/skills/doc-coverage/` | DELETE | Published copy (auto-generated mirror) |
| `src/copilot-cli/skills/doc-sync/` | DELETE | Published copy (auto-generated mirror) |
| `.claude/skills/codebase-documenter/SKILL.md` | UPDATE | Replace doc-coverage/doc-sync refs with doc-accuracy in "when NOT to use" section (lines 40-41) |
| `src/copilot-cli/skills/codebase-documenter/SKILL.md` | UPDATE | Same edit as above on the published copy |
| `tests/test_invoke_skill_learning.py` | UPDATE | Delete 4 doc-sync routing test cases (lines 370-394) |

## Implementation Notes

**Step order matters for drift detection:**

1. Delete the three source skill directories under `.claude/skills/`.
2. Delete the two matching published copies under `src/copilot-cli/skills/`.
3. Edit `codebase-documenter/SKILL.md` (source copy first, then published copy).
4. Delete the four dead test cases from `tests/test_invoke_skill_learning.py`.
5. Run `python3 build/scripts/build_all.py --platform copilot-cli` and confirm exit 0.
6. Run `uv run pytest tests/test_invoke_skill_learning.py` and confirm exit 0.
7. Run `python3 scripts/validation/pre_pr.py` and resolve any failures before committing.

**Commit strategy (atomic, ≤5 files each):**

- Commit 1: Delete `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, `.claude/skills/workflow/` (3 dirs = multiple files; split if >5 files total).
- Commit 2: Delete `src/copilot-cli/skills/doc-coverage/`, `src/copilot-cli/skills/doc-sync/`.
- Commit 3: Update `codebase-documenter/SKILL.md` (source) + `src/copilot-cli/skills/codebase-documenter/SKILL.md` (published copy).
- Commit 4: Delete dead test cases in `tests/test_invoke_skill_learning.py`.

**Skill pattern cache:** `.claude/hooks/Stop/.skill_pattern_cache.json` auto-regenerates on next hook invocation. No manual step needed.

**Failure modes to check before PR:**
- Search for any remaining references to `doc-coverage`, `doc-sync`, or `workflow` in `.claude/`, `src/copilot-cli/`, and `tests/` directories. Confirm only the known cross-reference in `codebase-documenter/SKILL.md` existed and has been updated.
- Confirm `build/scripts/generate_skills.py` does not hard-code skill names that would fail on absence.

## Testing Requirements

| Test | Command | Expected |
|---|---|---|
| Source dirs absent | `ls .claude/skills/` | No doc-coverage, doc-sync, workflow |
| Published dirs absent | `ls src/copilot-cli/skills/` | No doc-coverage, doc-sync |
| Cross-ref correct | `grep -r "doc-coverage\|doc-sync" .claude/skills/codebase-documenter/` | Zero matches |
| Build clean | `python3 build/scripts/build_all.py --platform copilot-cli` | Exit 0 |
| Routing tests pass | `uv run pytest tests/test_invoke_skill_learning.py` | Exit 0 |
| Pre-PR validation | `python3 scripts/validation/pre_pr.py` | No BLOCKING items |
