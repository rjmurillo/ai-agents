---
type: task
id: TASK-006
title: Skill Catalog Prune M1
status: open
priority: medium
complexity: S
related:
  - DESIGN-006
blocked_by: []
blocks: []
assignee: ""
---

# TASK-006: Skill Catalog Prune M1

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

- Changes to `doc-accuracy` SKILL.md
- Adding replacement routing test cases for `doc-accuracy`
- session-qa-eligibility fold or memory decomposition (separate milestones)
- Automated redirection shim
- Updates to `tests/evals/skills/triage-prompts.json`

## Acceptance Criteria

- [ ] TASK-006-AC1: `.claude/skills/doc-coverage/`, `.claude/skills/doc-sync/`, `.claude/skills/workflow/` do not exist after the PR lands.
- [ ] TASK-006-AC2: `src/copilot-cli/skills/doc-coverage/` and `src/copilot-cli/skills/doc-sync/` do not exist after the PR lands.
- [ ] TASK-006-AC3: `codebase-documenter/SKILL.md` and its published copy contain `doc-accuracy` (not `doc-coverage` or `doc-sync`) in the "when NOT to use" section.
- [ ] TASK-006-AC4: `uv run pytest tests/test_invoke_skill_learning.py` exits 0 with no `doc-sync` routing assertions present.
- [ ] TASK-006-AC5: `python3 build/scripts/build_all.py --platform copilot-cli` exits 0 after all deletions.
- [ ] TASK-006-AC6: Pre-push drift detection reports zero drift between `.claude/skills/` and `src/copilot-cli/skills/`.

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
