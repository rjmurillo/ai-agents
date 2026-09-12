---
type: task
id: TASK-033
title: Remaining 93 skills templated in batches, pilot-scope pin retired (B3)
status: todo
priority: P1
complexity: XL
source: ADR-109
related:
  - REQ-026
  - DESIGN-025
  - TASK-031
  - TASK-032
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-033: Remaining 93 skills templated in batches, pilot-scope pin retired (B3)

## Objective

Template the 93 skills not yet covered by ADR-108's pilot (measured 2026-09-11: `find .claude/skills -maxdepth 2 -name SKILL.md | wc -l` returns 111, `ls templates/skills/*.tmpl | wc -l` returns 18, so 93 remain), in batches, under one tracking issue, until `discover()` on the real tree matches the full 111-skill set and the pilot-scope pin is deleted. This task also gives skills the `src/claude/` plugin tree ADR-109 section 2 names but B1 does not deliver: `skill_templates.compile_all`'s render target moves from `.claude/skills/<name>/SKILL.md` directly to `src/claude/skills/<name>/SKILL.md`, and the binplace step copies that plugin tree into `.claude/skills/`, closing the same two-hop gap every other migrated class already closes. It also adds the twelve `pr-quality-gate-*.md` prompt files as a manifest row, since their source (`.claude/skills/review/references`) and compile step (`build/scripts/generate_pr_quality_prompts.py`) are both skill-derived and no other task's scope names them.

## In/Out of Scope

In scope: creating `templates/skills/<name>.SKILL.md.tmpl` for each of the 93 remaining skills, reusing the existing `build/scripts/skill_templates.py` and `skill_template_grammar.py` compile modules unchanged in their grammar and render logic (this task adds templates, not a new compile module); deleting `tests/build_scripts/test_skill_templates_pilot_scope.py`'s `PILOT` pin once the full set matches `discover()`; moving `skill_templates.compile_all`'s render target to `src/claude/skills/<name>/SKILL.md` and wiring the binplace step to copy it into `.claude/skills/`; switching the manifest's `skills` row (added at B1 with `plugin_tree: null`) to `plugin_tree: src/claude/skills`; repointing `generate_skills.py`'s Copilot-mirror copy step to read `src/claude/skills/` instead of `.claude/skills/`; widening `OWNED_PREFIXES` to include `.claude/skills/`; adding the `prompts` manifest row (`source: .claude/skills/review/references`, `install_tree: .github/prompts`, `compile: generate_pr_quality_prompts`, `plugin_tree: null`) for the twelve `pr-quality-gate-*.md` files.

Out of scope: changing `skill_template_grammar.py`'s grammar or render behavior; changing any skill's guidance content beyond what moving to a template requires (no content rewrite); the 21 non-`pr-quality-gate` `.github/prompts/` files (REQ-026 Deferred); agents, rules, hooks, settings, lib, marketplace switch.

## Acceptance Criteria

- [ ] `ls templates/skills/*.tmpl | wc -l` equals `find .claude/skills -maxdepth 2 -name SKILL.md | wc -l` (both 111) once every batch lands.
- [ ] `git diff --exit-code -- .claude/skills` exits 0 after `uv run python build/scripts/build_all.py` runs on a clean checkout, for every batch's PR.
- [ ] Each batch PR touches at most ten files (`.claude/rules/claude-agents.md` MUST item 4, "File cap per PR", cited by ADR-109 section 7); `git show --stat <sha> | tail -1` on each batch's merge commit confirms.
- [ ] The existing `Skill Template Drift` gate stays green after every batch (no new gate needed; the class's gate already exists from ADR-108).
- [ ] `tests/build_scripts/test_skill_templates_pilot_scope.py`'s `PILOT` constant is deleted (and the file itself deleted, since its sole purpose was pinning the pilot boundary) once `discover(repo_root)` on the real tree returns all 111 names with no further owner-approval step required for a new one.
- [ ] `uv run pytest tests/build_scripts/test_generate_skills_template_compile.py tests/skills -v` passes for every migrated skill.
- [ ] `ls src/claude/skills/*/SKILL.md | wc -l` returns 111 once the last batch lands; `git diff --exit-code -- .claude/skills` exits 0 after `uv run python build/scripts/build_all.py` runs on a clean checkout, confirming the binplace copy from `src/claude/skills/` reproduces today's `.claude/skills/` content exactly.
- [ ] `grep -n "class: skills" -A 4 templates/platforms/binplace.yaml` shows `plugin_tree: src/claude/skills`, not `null`; `tests/build_scripts/test_binplace_manifest.py` passes with the updated row.
- [ ] `grep -n "sourceDir" build/scripts/generate_skills.py` (or the equivalent read site) shows the Copilot-mirror copy step reading `src/claude/skills`, not `.claude/skills`; `git diff --exit-code -- src/copilot-cli/skills` exits 0 after a clean run.
- [ ] `grep -n "OWNED_PREFIXES" -A 8 build/scripts/build_all.py` lists `.claude/skills/` in the tuple; symlinking `.claude/skills/` and running `uv run python build/scripts/build_all.py --check` exits 2.
- [ ] `grep -n "class: prompts" -A 4 templates/platforms/binplace.yaml` shows the row (`source: .claude/skills/review/references`, `install_tree: .github/prompts`, `compile: generate_pr_quality_prompts`); `git diff --exit-code -- .github/prompts` exits 0 after a clean run, and only the twelve `pr-quality-gate-*.md` files are covered by the row (the other 21 stay hand-maintained, per REQ-026 Deferred).
- [ ] No em dash or en dash in any changed file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.

## Files Affected

| File | Action | Description |
|---|---|---|
| `templates/skills/<name>.SKILL.md.tmpl` (93 files, in batches) | Create | Canonical source per skill, current `SKILL.md` content, batched five to ten files per PR |
| `tests/build_scripts/test_skill_templates_pilot_scope.py` | Delete | Pin retired once the full 111-skill set matches `discover()` |
| `tests/skills/<name>/test_skill_md_contract.py` (per migrated skill, as needed) | Create | Per-skill contract test, mirroring the eight ADR-108 pilot skills' existing tests |
| `build/scripts/skill_templates.py` (`compile_all`, `owned_targets`) | Modify | Render target moves from `.claude/skills/<name>/SKILL.md` to `src/claude/skills/<name>/SKILL.md` |
| `build/scripts/build_all.py` (binplace step, `OWNED_PREFIXES`) | Modify | Binplace copies `src/claude/skills/` into `.claude/skills/`; `OWNED_PREFIXES` gains `.claude/skills/` |
| `templates/platforms/binplace.yaml` | Modify | `skills` row's `plugin_tree` changes from `null` to `src/claude/skills`; new `prompts` row added (`source: .claude/skills/review/references`, `install_tree: .github/prompts`, `compile: generate_pr_quality_prompts`) |
| `build/scripts/generate_skills.py` | Modify | Copilot-mirror copy step repointed to read `src/claude/skills/` instead of `.claude/skills/` |

## Implementation Notes

- No new grammar or render module: `skill_template_grammar.py`'s tag handling and partial resolution are reused exactly as ADR-108 left them; `skill_templates.py`'s `discover`, `compile_all`, and `owned_targets` change only their target path, not their grammar.
- The render-target move (`.claude/skills/` to `src/claude/skills/`, binplaced back) is a separate commit from the 93 template additions: land it early in this task's batch sequence, with its own byte-identity test against a pre-move snapshot, so every subsequent batch PR compiles into the new target from the start rather than needing a second pass.
- Batch by logical grouping (skills sharing a domain, or an author's existing PR queue) rather than alphabetically, so each batch is independently reviewable; ADR-109 section 7 sets the ceiling (five to eight files per PR, ten-file cap) but not the grouping, which is this task's own call, recorded per batch's PR body.
- Track batch progress under one tracking issue so the 93-file total is visible across however many PRs the batching produces; do not open 93 separate issues.
- Delete the pilot-scope pin test only in the batch that completes the full 111-skill set; every earlier batch keeps it in place (with its `PILOT` set inapplicable until 111, since that test asserts `discover()` matches `PILOT` exactly, not a superset).
- Per `.claude/rules/claude-agents.md` MUST item 4, "File cap per PR", skill additions SHOULD ship at most 10 files per PR; batch accordingly.

## Testing Requirements

Positive: every migrated skill's rendered `SKILL.md` byte-identical to a fixture render of its template; `src/claude/skills/<name>/SKILL.md` and `.claude/skills/<name>/SKILL.md` byte-identical after the render-target move and binplace, for all 111 skills once the last batch lands; the twelve `pr-quality-gate-*.md` prompts render byte-identical to their fixture from the new `prompts` manifest row. Negative: a batch containing a missing partial or disallowed tag fails that batch's PR before merge, per the existing `Skill Template Drift` gate; a hand edit to `.claude/skills/` after the render-target move fails `build_all.py --check` with exit 2. Edge: a skill directory with no template stays untouched throughout the migration, verified after each batch by `git diff --exit-code` against the not-yet-migrated skills.

## Dependencies

TASK-031 and TASK-032 merged (agents and rules land first per ADR-109 section 7's stated order). Unlike rules or hooks, this task's template additions need no new binplace manifest row of their own, since TASK-031 already ships the `skills` row (delegating to `skill_templates.owned_targets`, `plugin_tree: null`); this task instead switches that row's `plugin_tree` to `src/claude/skills` and adds the separate `prompts` row.
