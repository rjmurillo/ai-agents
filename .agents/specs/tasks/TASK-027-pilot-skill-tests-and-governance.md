---
type: task
id: TASK-027
title: Eight pilot templates, six partials, rendered files, mirrors, contract tests (A2)
status: todo
priority: P1
complexity: M
source: GH-5706
related:
  - REQ-025
  - DESIGN-024
  - TASK-025
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-027: Eight pilot templates, six partials, rendered files, mirrors, contract tests (A2)

## Done definition

- `templates/skills/{sync,test,spec,ship,research,plan,checkpoint,build}.SKILL.md.tmpl` exist: each is the current `SKILL.md` with the `@CLAUDE.md` line deleted and the `{{> slug}}` lines from the DESIGN-024 placement table inserted at the named steps.
- `templates/skills/partials/{no-dashes,completion-tail-audit,clear-the-gate,conventional-commits,bound-the-search,terminal-predicate}.mustache` exist, each opening with `{{! rule-source: <file>.md }}` and each body a verbatim contiguous span of that rule file.
- `uv run python build/scripts/build_all.py` rendered the eight `.claude/skills/<name>/SKILL.md` files and regenerated their `src/copilot-cli/skills/<name>/SKILL.md` mirrors; both sets committed; `build_all.py --check` exits 0; `git status` shows no unrelated drift.
- `tests/build_scripts/test_skill_partials_rule_parity.py` passes with a negative control.
- `tests/build_scripts/test_skill_templates_pilot_scope.py` `PILOT` widened to the eight pilot names in the same commit as the templates.
- `tests/skills/_template_contract.py` plus `tests/skills/<pilot>/test_skill_md_contract.py` for all eight pass: rendered equals render of template; no `^@CLAUDE\.md$` line and no `{{` in rendered or mirror.
- `.claude/skills/CLAUDE.md`, `.agents/steering/claude-skills.md`, and `.agents/governance/SKILL-CREATION-CRITERIA.md` each carry one sentence: the eight pilot skills are template-owned; edit `templates/skills/<name>.SKILL.md.tmpl`, not `SKILL.md`; the first regenerates its plugin mirror through `build_all.py`.
- The PR byte report names every template-owned file carrying a NO-REGEN sentinel (expected: none).
- `tests/test_frontgate_crosslink_1927.py:163` flipped to assert absence of `@CLAUDE.md` in the plan source and mirror.
- `uv run python scripts/validation/check_skill_md_portability.py` reports no new offender; `uv run pytest tests/commands/test_spec_step0.py tests/build_scripts/test_generate_skills.py -q` passes.
- PR body quotes `wc -c` before and after for the five always-on rule files and the eight pilot files, uses `Fixes #5706`, and states issue #5657 is untouched.

## Implementation notes

- Do not hand-edit a rendered file once its template exists; edit the template or partial and rerun `build_all.py`.
- The excerpt for `bound-the-search` goes directly under the `### Step 0.5: Memory-First Gate` heading in the `spec` template, not in `references/`.
- Atomic commits: partials (6); templates in two commits of four; rendered files and mirrors are generated companions; tests in two commits.

## Dependencies

TASK-025 merged, so the compile exists when the templates land.
