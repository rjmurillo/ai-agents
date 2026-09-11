---
type: requirement
id: REQ-021
title: Pilot skills compiled from mustache templates with single-sourced guidance
status: draft
priority: P1
category: functional
source: GH-5706
related:
  - REQ-003
  - ADR-108
  - DESIGN-020
  - TASK-024
  - TASK-025
  - TASK-026
created: 2026-09-11
updated: 2026-09-11
author: spec
tags:
  - skills
  - rules
  - generation
---

# REQ-021: Pilot skills compiled from mustache templates with single-sourced guidance

## Step 0 First Principles

### Q1 Demand Reality

Three requesters by name. (1) The repository owner, `rjmurillo`, in epic #5698: "Skill guidance is compiled into SKILL.md from templates so the always-on rule set can shrink without losing ordering" is a listed outcome of that epic, and #5706 is its sub-issue. (2) The always-on rule cut, tracked in issues #5400, #5492, and #4871, which epic #5698 lists as a deferred candidate that "follows #5706". (3) The Copilot CLI harness, version 1.0.66-1, which treats the `@CLAUDE.md` include line as literal text; `build/scripts/copilot_body_translation.py:14` records that contract from the Serena memory `decisions/decision-copilot-cli-skill-task-arguments-claude-import-contract`.

### Q2 Status Quo

A skill author who wants rule guidance at a step has three moves today. Paste the rule text by hand into `SKILL.md`, which duplicates it with no drift check. Name the rule file by path in prose, which Copilot consumers cannot open. Or add the line `@CLAUDE.md`, which eight skills do (`sync`, `test`, `spec`, `ship`, `research`, `plan`, `checkpoint`, `build`), and which `generate_skills.py` rewrites into an HTML comment for the Copilot mirror (`no include directive needed`, `src/copilot-cli/skills/spec/SKILL.md:37`). No mechanism pins copied guidance to its source.

### Q3 Desperate Specificity

The owner, `rjmurillo`, is blocked on cutting the always-on rule set. Epic #5698 states the cut "follows #5706" because moving guidance into skills needs a single-source mechanism first. Without it, every byte cut from `voice.md` or `universal.md` becomes an unpinned copy inside some skill.

### Q4 Narrowest Wedge

One compile module plus a `--validate` flag on the existing skills generator, one allowlist argument on the existing `.claude/` guard, six partials, eight templates, tests, one `pre_pr` gate row, and the ADR-108 amendment that permits it. About 2 days human, about 3 hours AI-assisted including the ADR review round.

### Q5 Observation

Measured on `main` at `cd0f9561d` on 2026-09-11. `wc -c` on the five always-on rule files returns 56,984 bytes total (`voice.md` 19,748; `builder-ethos.md` 14,054; `universal.md` 10,097; `search-before-building.md` 7,115; `claude-model-patches.md` 5,970). `grep -n '@CLAUDE.md' .claude/skills/*/SKILL.md` returns exactly eight files, one line each. `build/scripts/copilot_body_translation.py:14` states: "`@CLAUDE.md` first line -> treated as LITERAL-TEXT (not auto-inlined)". `grep -n '\.claude/rules/' .claude/skills/{sync,test,spec,ship,research,plan,checkpoint,build}/SKILL.md` returns nothing, so the eight pilot skills carry no other rule reference today.

### Q6 Future-fit

The repository has 111 skill directories. A skill joins the class by the presence of one `.tmpl` file, so a skill with none costs the compile step nothing. At ten times the skill count the compile is still one render per template and one byte compare per rendered file. The cost that does scale is one extra file per migrated skill, which is the same shape `templates/agents/` already carries for 31 agents.

## Step 0.5 Prior Art

Searched: Serena memories (`copilot/copilot-skill-mirror-has-two-sources`, `architecture/always-on-membership-lives-in-the-mirror`, `agent-workflow/agent-generation-edit-locations`, `decision-agent-files-are-not-canonical`), ADR-107 and its debate log, REQ-003, `.agents/governance/GENERATOR-FILES.md`, `tests/skills/test_spec_bundle_parity.py`, `scripts/validation/check_generated_staleness.py`, `build/generate_agents.py --validate`. No existing mechanism pins an excerpt inside a skill to a rule file, so the gate does not halt. Two precedents shape the design: `test_spec_bundle_parity.py` pins byte-identical bundled copies to their canonical source, and `check_generated_staleness.py` wires a regenerate-then-diff gate into `pre_pr_sequence.py`.

Constraint found during the search, and it changes the design issue #5706 sketches: `build/scripts/build_all.py:793` (`assert_no_claude_writes`, REQ-003-010) exits 2 when any generator writes under `.claude/`. ADR-107 lists "Generators read canonical trees and write mirror trees. They never write under `.claude/`" as a settled property it does not reopen. REQ-003 decision D4 makes `.claude/<artifact>/` canonical. Epic #5698's review corrections state that #5706 "must not create a second ADR-107 or a generator that writes over canonical `.claude/` content". `assert_no_claude_writes` is a before-and-after content diff, so a compile step that renders `templates/skills/<name>.SKILL.md.tmpl` into `.claude/skills/<name>/SKILL.md` through `build_all.py` exits 2 whenever the render differs from the committed file, which is every regeneration that does work. Beyond the guard, the design is blocked by policy text: ADR-107 property 1, REQ-003 D4, and the epic correction. So the issue's design needs an amendment before it can land, and issue #5706 step 1 routes exactly that. The owner chose the amendment path on 2026-09-11 (decision D1) over a no-amendment excerpt design; ADR-108 carries the amendment and DESIGN-020 the chosen mechanism, with the declined design kept at its end.

## Requirement Statement

WHEN a pilot skill's committed `.claude/skills/<name>/SKILL.md` differs from the render of `templates/skills/<name>.SKILL.md.tmpl` with its partials, or a partial with a `rule-source` pin no longer appears verbatim in its rule file, THE SYSTEM SHALL fail the pre-PR gate and name the drifted file, SO THAT rule guidance bundled into a skill is authored once and cannot silently fork from the rule that still binds non-skill work.

## Context

Rule guidance loads on every turn from five always-on files regardless of task. The owner wants guidance to land at the step that needs it, inside the skill, and later to shrink the always-on set. That needs a template layer skills do not have today. Issue #5706 proposes mustache templates rendered into `.claude/skills/`; REQ-003-010 forbids the write, so ADR-108 amends it for this one enumerated class.

## Ontology

Entities from `.agents/specs/ontology/skill-guidance-excerpts.md` (revised for D1): rule file, always-on rule set, skill template, partial, template-owned skill file, skill mirror, compile step, drift gate, pilot skill, include line. Implements decision rules DR1 through DR6.

## Acceptance Criteria

1. [ ] `ls templates/skills/{sync,test,spec,ship,research,plan,checkpoint,build}.SKILL.md.tmpl` lists all eight files with no error.
2. [ ] WHEN `uv run python build/scripts/build_all.py` runs on the branch, `git diff --exit-code -- .claude/skills/{sync,test,spec,ship,research,plan,checkpoint,build}/SKILL.md` exits 0 (the committed rendered files are byte-identical to the compile output).
3. [ ] WHEN one rendered pilot file is hand-edited, `uv run python build/scripts/generate_skills.py --validate` SHALL exit 1 and print that file's path; after `uv run python build/scripts/build_all.py`, the same command SHALL exit 0.
4. [ ] WHEN a template names a partial with no file under `templates/skills/partials/`, or carries any tag other than `{{> slug}}` and `{{! comment}}`, THE SYSTEM SHALL exit 2 and print the template path and the offending tag or slug, writing nothing.
5. [ ] WHEN a template-owned target carries a NO-REGEN sentinel recognized by `build/scripts/regen_guard.py:detect_reason` (in-file token or `.noregen` sidecar), the compile SHALL leave the file unchanged, print a WARN, and exit 1 in write and validate mode (ADR-108 section 4; diverges from issue #5706 step 10 by owner-reviewed decision).
6. [ ] WHEN `build_all.py` runs, `assert_no_claude_writes` SHALL report no violation for a template-owned `.claude/skills/<name>/SKILL.md` and SHALL still report a violation and exit 2 for any other write under `.claude/`.
7. [ ] WHEN `build_all.py --check` runs on a tree whose rendered pilot file differs from its template, THE SYSTEM SHALL exit 2 and leave every file under `.claude/` unchanged.
8. [ ] `grep -l '{{' src/copilot-cli/skills/{sync,test,spec,ship,research,plan,checkpoint,build}/SKILL.md` SHALL print nothing. (Issue #5706 states the check over all of `src/copilot-cli/skills/`; measured on `cd0f9561d`, 22 non-pilot mirrors already contain `{{` and are out of scope.)
9. [ ] `grep -l '^@CLAUDE\.md' src/copilot-cli/skills/*/SKILL.md .claude/skills/{sync,test,spec,ship,research,plan,checkpoint,build}/SKILL.md` SHALL print nothing.
10. [ ] Every partial under `templates/skills/partials/` whose first line is `{{! rule-source: <file>.md }}` SHALL be a verbatim contiguous substring of `.claude/rules/<file>.md`, enforced by `tests/build_scripts/test_skill_partials_rule_parity.py` with a negative control.
11. [ ] `uv run python scripts/validation/pre_pr.py` SHALL include a gate named `Skill Template Drift` that runs the validate command and fails closed on exit 1 or 2.
12. [ ] `uv run pytest tests/build_scripts/test_generate_skills_template_compile.py tests/skills/{sync,test,spec,ship,research,plan,checkpoint,build} -v` SHALL pass with the positive, negative, config, and edge cases listed in DESIGN-020.
13. [ ] The PR body SHALL quote `wc -c` on the five always-on rule files and on the eight pilot `SKILL.md` files, before (on `origin/main`) and after (on the branch).
14. [ ] `git diff --name-only origin/main... | grep -E '\.(sh|ps1)$'` SHALL print nothing under `build/` or `scripts/`.
15. [ ] `chevron==0.14.0` SHALL appear in both `[project.optional-dependencies].dev` and `[dependency-groups].dev` of `pyproject.toml`, and `tests/test_pyproject_dev_deps_parity.py` SHALL pass.
16. [ ] ADR-108 SHALL exist under `.agents/architecture/` with a recorded `adr-review` round, and `.agents/architecture/README.md` SHALL be regenerated to list it.

## Rationale

The template design makes `templates/skills/` the canonical source for the eight pilot skills, which is what issue #5706 asks for and what the owner confirmed. It reuses the agent-template shape (`templates/agents/*.shared.md` rendered by `build/generate_agents.py --validate`) so a reader who knows one pipeline knows both. The restricted grammar keeps the engine from hiding a typo, and the run-time allowlist keeps REQ-003-010 fail-closed for every path that is not template-owned.

## Buy-vs-build decision

Context capability (a repo-internal build step). Alternatives evaluated: `chevron` 0.14.0 (pure Python, MIT, no dependencies, standard mustache, last release 2021-01-02); Jinja2 (larger grammar, HTML-escaping defaults, more surface than partial expansion needs); an in-tree partial expander (about 40 lines, no dependency, but a second mustache-like syntax to document). Recommendation: buy `chevron` as a dev dependency behind a restricted grammar, so a later swap to an in-tree expander is bounded. Issue #5706 asks for the decision to be recorded in the PR description as well.

## Complexity classification

Engineering tier 4. Cynefin: Complicated (known techniques, expert sequencing, one governance change). Methodology: amendment first (ADR-108 through `adr-review`), then the compile pipeline with tests, then the pilot content. ADR cross-reference: ADR-108, which amends ADR-107 property 1 and REQ-003-010.

## Out of scope

- Cutting or rewriting any rule file. Excerpts copy; they do not move text.
- Converting any skill beyond the eight pilots.
- Changing `build/generate_agents.py`, `templates/agents/`, or `generate_skills.py` behavior.
- Narrowing the `paths: ["**"]` scope of any always-on rule.
- Any amendment beyond the one enumerated class in ADR-108.
- Templates for `references/*.md`; the pilot compiles `SKILL.md` only.
- Closing any part of issue #5657 (`references/` translation and multi-line prompt bodies); untouched.

## Deferred

- Migrating the other 103 skills to templates. Owner: `rjmurillo`, after the pilot's byte report.
- Templates for `references/*.md`. Owner: whoever runs the second pilot wave.
- Sub-section partials with an in-rule marker pair, if a needed span is not contiguous in its rule file. Owner: same.
- Replacing `chevron` with an in-tree expander if its unmaintained status becomes a finding. Owner: same.

## Open questions

- Whether ADR-108 moves to `accepted` on merge of the A0 pull request or after the pilot lands. Owner: `rjmurillo`. The A1 pull request cites ADR-108 as its authority either way, since the owner selected the path on 2026-09-11.

## CVA summary

Common: every pilot skill needs rule text at a step, authored once, portable to the Copilot mirror unchanged. Varies: which partials each skill carries and at which step. Relationship: a many-to-many between templates and partials, expressed by `{{> slug}}` tags, resolved by one compile step.
