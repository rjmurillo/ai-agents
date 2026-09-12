---
type: requirement
id: REQ-026
title: Template-first distribution for every artifact class the plugins ship
status: draft
priority: P1
category: functional
source: ADR-109
related:
  - REQ-003
  - ADR-107
  - ADR-108
  - ADR-109
  - DESIGN-025
  - TASK-031
  - TASK-032
  - TASK-033
  - TASK-034
  - TASK-035
  - TASK-036
created: 2026-09-11
updated: 2026-09-11
author: spec
tags:
  - agents
  - skills
  - rules
  - hooks
  - lib
  - generation
  - plugins
---

# REQ-026: Template-first distribution for every artifact class the plugins ship

## Step 0 First Principles

### Q1 Demand Reality

One requester by name: the repository owner, `rjmurillo`, directive recorded in ADR-109 Decision Drivers D1 on 2026-09-11: move every artifact class the plugins ship under `templates/`, compile into two plugin trees, and bin-place those trees into the two hand-edited install locations, as one atomic operation. Two named downstream consumers depend on this directive already landing: ADR-109 Decision Driver D2, the 31 percent unguarded agent-drift figure that the existing co-change gate does not catch; and Decision Driver D6, this repository's own Copilot CLI sessions and cloud-agent runs, which read `.github/hooks/*.json` and receive nothing today because that path does not exist in this tree.

### Q2 Status Quo

A contributor who wants to change an agent, a rule, a hook, or `.claude/settings.json` edits the hand-maintained file directly today: `src/claude/<name>.md` for agents (33 files at the plugin root, no `agents/` subdirectory, measured with `ls src/claude/*.md | wc -l`), `.claude/rules/<name>.md` for rules (30 files, measured with `ls .claude/rules/*.md | wc -l`, no `templates/rules/` tree exists), `.claude/hooks/` and `.claude/settings.json` for hooks (23 files tracked under `.claude/hooks/`, measured with `git ls-files .claude/hooks | wc -l`, the tracked count rather than a directory walk since a directory walk also counts untracked `__pycache__` byproducts; of these, 16 are the hooks class this record migrates: 13 executables (`.py`/`.sh`, measured with `git ls-files .claude/hooks | grep -cE '\.(py|sh)$'`), `hooks.json`, `dispatch_groups.json`, and `PreToolUse/markdownlint-safe-config.yaml`, a hook's own configuration file; the remaining 7 are doc files (`AGENTS.md` and six `CLAUDE.md`/`README.md` files) that stay outside the class; no `templates/hooks/` tree exists). Only skills (ADR-108, 18 of 111 skill directories templated, measured with `ls templates/skills/*.tmpl | wc -l` against `find .claude/skills -maxdepth 2 -name SKILL.md | wc -l`) and, for one narrower slice, PR-quality prompts already compile from a template. Lib is copied twice through an unenforced two-hop chain (`scripts/sync_plugin_lib.py` then `build/scripts/build_all.py`'s lib step) with no single command that performs both hops.

The 31 existing `templates/agents/*.shared.md` files are not a byte-for-byte source for `src/claude/<name>.md` today: they already diverge in body content, because `templates/agents/` today renders only the Copilot and VS Code copies, never `src/claude/`. Measured 2026-09-11 with a frontmatter-stripped `comm -13`/`comm -23` over sorted body lines for each of the 31 paired files (`templates/agents/<stem>.shared.md` against `src/claude/<stem>.md`), blank lines counted: 18 of the 31 pairs carry Claude-only content; across those 18 pairs, 1,414 lines exist only in the current `src/claude/<stem>.md` body and 622 lines exist only in the current `templates/agents/<stem>.shared.md` body. Frontmatter diverges too: `grep -l 'isolation_required: true' templates/agents/*.shared.md src/claude/*.md` returns four `src/claude/*.md` files (`architect.md`, `implementer.md`, `qa.md`, `security.md`) against two templates (`security.shared.md`, `implementer.shared.md`). A render that simply pointed `src/claude/agents/` at the existing `templates/agents/*.shared.md` files would therefore silently drop up to 1,414 lines of Claude-specific content and two frontmatter flags on first render, which is why B1 cannot be a bare retarget of the existing single-variant template.

### Q3 Desperate Specificity

The owner is blocked on closing the exact gap ADR-109 Decision Driver D2 measures: 31 percent of commits touching a hand-maintained shared-agent member skip the template with no gate catching it. ADR-109 Decision Driver D4 records that the prior direction for agents, ADR-052, has sat at `accepted` with zero implementation for 17 days, so a second unimplemented direction is not free; this record must supersede it, not stack beside it.

### Q4 Narrowest Wedge

Six pull requests, one per ADR-109 Implementation Notes step (B1 agents, B2 rules, B3 remaining 93 skills in batches, B4 hooks and settings, B5 lib, B6 marketplace switch), each landing its own drift gate, tests, and `GENERATOR-FILES.md` row, reusing the compile-and-drift-gate shape ADR-108 already proved for skills across five pull requests in one day (ADR-109 Decision Driver D5).

### Q5 Observation

Measured in this worktree on 2026-09-11. `ls templates/agents/*.shared.md | wc -l` returns 31. `ls .claude/rules/*.md | wc -l` returns 30. `git ls-files .claude/hooks | wc -l` returns 23, of which `git ls-files .claude/hooks | grep -cE '\.(py|sh)$'` returns 13. `ls templates/skills/*.tmpl | wc -l` returns 18; `find .claude/skills -maxdepth 2 -name SKILL.md | wc -l` returns 111, so 93 skills remain untemplated. `ls .github/hooks` fails, no such directory. `ls .github/prompts | wc -l` returns 33; `ls .github/prompts | grep -c pr-quality-gate` returns 12, so 21 prompt files stay outside the manifest until a template names them. `ls src/claude/*.md | wc -l` returns 33 (plugin-root files, no `agents/` subdirectory today); of those, `AGENTS.md` and `claude-instructions.template.md` are not one of the 31 agent files and stay at the plugin root after B1's move. `find src/claude/security -type f | wc -l` returns 3 (`dependency-risk-scoring.md`, `powershell-security-checklist.md`, `threat-model-template.md`), a nested reference tree the `security` agent uses that sits outside the flat `*.md` count above and moves to `src/claude/agents/security/` alongside `security.md` in B1's layout move. `cat .claude/hooks/hooks.json` and the Copilot-side equivalent both read `"hooks": {}`. `cat .github/plugin/marketplace.json` names one plugin, `project-toolkit`, sourced at `./src/copilot-cli`. `cat .claude-plugin/marketplace.json` names two plugins, `claude-agents` and `project-toolkit`. `grep -n "hook_utilities\|github_core\|ai_review_common" .github/CODEOWNERS` shows one lib package pinned today, `ai_review_common`. `grep -n "sourceDir" templates/platforms/copilot-cli.yaml` shows four stanzas (agents, skills, rules, lib) naming a `.claude/` path as `sourceDir`, plus `scriptSource`/`settingsSource` naming `.claude/hooks/`; `grep -n "sourceDir" templates/platforms/visual-studio.yaml templates/platforms/vscode.yaml` returns nothing, so only the Copilot CLI manifest carries this field today.

### Q6 Future-fit

A class joins the template-first model by the presence of a `templates/<class>/` tree the compiler discovers at run time (the same run-time-enumerated allowlist shape ADR-108 established for skills), so a class with no templates yet costs the compiler nothing. The binplace manifest is a data file, so a seventh class needs a new manifest row, not a new code branch. The lib exception is bounded to three named packages; a new lib package is added to the manifest's lib rows without changing the copy mechanism.

## Step 0.5 Prior Art

Searched: ADR-109 in full, its Prior Art and Rationale sections, and the exemplar pair ADR-108 plus REQ-025, DESIGN-024, TASK-030, TASK-025, and the completed plan for issue #5706, since ADR-109 states it generalizes that exact pattern. Also searched `build/scripts/skill_templates.py`, `build/scripts/skill_template_grammar.py`, `build/scripts/build_all.py` (`assert_no_claude_writes`, `OWNED_PREFIXES`), `scripts/sync_plugin_lib.py`, `templates/platforms/copilot-cli.yaml`, `.claude/rules/generated-artifacts.md`, `.agents/governance/GENERATOR-FILES.md`, and `scripts/validation/pre_pr_sequence.py`'s gate registry, all read in this worktree on 2026-09-11.

Constraint found: ADR-109 itself is the amendment; there is no further policy blocker beyond what it already resolves. What differs from the ADR-108 precedent: ADR-108 amended REQ-003-010 and ADR-107 property 1 for one enumerated class (skills); ADR-109 generalizes that same exception to every class the plugins ship, so each of B1 through B5 must independently implement the drift gate, NO-REGEN handling, and symlink and containment checks ADR-108 built for skills, because those checks live in `build/scripts/skill_templates.py` scoped to `.claude/skills/<name>/` and do not extend to a sibling class on their own (ADR-109 section 6).

## Requirement Statement

WHEN a contributor or a build changes any artifact under an ADR-109-enumerated class with a plugin consumer (agents, rules, hooks; skills already covered by ADR-108; lib excepted to `scripts/`), THE SYSTEM SHALL treat the class's `templates/` tree as the sole canonical source, render it into both plugin trees (Claude Code at `src/claude/<class>` and Copilot CLI at `src/copilot-cli/<class>`) and bin-place those trees into install trees (Claude at `.claude/<class>` and Copilot at `.github/<...>` where a Copilot install surface exists) in one atomic `build_all.py` run, and fail closed under `--check` or the pre-PR drift gate whenever any of the four trees would not match. WHEN settings change, THE SYSTEM SHALL render `.claude/settings.json` directly from `templates/hooks/settings.tmpl` to `.claude/settings.json` with no plugin-tree hop. WHEN lib packages change, THE SYSTEM SHALL copy them from `scripts/{hook_utilities,github_core,ai_review_common}` directly into `.claude/lib/`, `src/claude/lib/`, and `src/copilot-cli/lib/` with no template render step. SO THAT one edit to one template reaches every consumer instead of forking across multiple hand-maintained copies.

## Context

ADR-109 supersedes ADR-052's Claude-first direction for agents and extends ADR-108's compile-and-drift-gate pattern from one enumerated class (skills) to agents, rules, hooks, and settings, with lib as a narrower, exception-carrying fifth case. This requirement formalizes ADR-109 section by section: canonical source per class (section 1), the two-plugin-tree compiler (section 2), the one-atomic-operation binplace step (section 3), one Claude plugin (section 4), the amendment text (section 6), and the migration order (section 7). It does not reopen or restate the ADR's own reasoning; it states what a passing build and a passing gate must be true of once each of B1 through B6 lands.

## Ontology

Entities from `.agents/specs/ontology/template-first-distribution.md`: class, template tree, plugin tree, install tree, binplace, manifest row, canonical source, binplace manifest, drift gate. Implements decision rules DR1 through DR9.

## Acceptance Criteria

1. [ ] REQ-026-001 WHEN a class's migration PR (B1 agents, B2 rules, B4 hooks and settings) lands, `templates/<class>/` SHALL exist and be the class's canonical source; `.claude/<class>/` SHALL no longer be hand-editable without the next `build_all.py` run overwriting the edit. Verification, per class after its PR: `test -d templates/agents`, `test -d templates/rules`, `test -d templates/hooks` each exit 0 once that class lands; the hand-edit clause is verified by hand-editing a rendered file under that class's `.claude/` target and running `uv run python build/scripts/build_all.py --check`, which SHALL exit 2.
2. [ ] REQ-026-002 WHEN B5 lands, `scripts/sync_plugin_lib.py` SHALL no longer exist as a standalone entry point; `build/scripts/build_all.py`'s lib step SHALL copy `scripts/{hook_utilities,github_core,ai_review_common}` directly into `src/claude/lib/` and `src/copilot-cli/lib/` in the same run that renders every other class. Verification: `git log --diff-filter=D --oneline -- scripts/sync_plugin_lib.py | head -1` returns a non-empty deletion commit.
3. [ ] REQ-026-003 WHEN `uv run python build/scripts/build_all.py` runs on a branch with every migration PR landed, THE SYSTEM SHALL render `src/claude/` and `src/copilot-cli/` from the templates in the same invocation that renders every other generated tree. Verification: `git diff --exit-code -- src/claude src/copilot-cli` exits 0 immediately after the run.
4. [ ] REQ-026-004 WHEN that same run completes, THE SYSTEM SHALL have bin-placed `src/claude/` into `.claude/` and `src/copilot-cli/` into `.github/` (`instructions/`, `agents/`, `hooks/` as `.github/hooks/*.json`, and the twelve `pr-quality-gate-*.md` prompt files under `.github/prompts/`) as part of the one invocation, SO THAT no second command is required to reach either install tree. Verification: `git diff --exit-code -- .claude .github` exits 0 immediately after the same single run.
5. [ ] REQ-026-005 WHEN `uv run python build/scripts/build_all.py --check` runs, THE SYSTEM SHALL verify all four trees (`src/claude`, `src/copilot-cli`, `.claude`, the manifest-named paths under `.github`) are byte-identical to what the templates render, and SHALL exit 2 and leave every tree unchanged when any one of the four drifts. Verification: hand-edit one file under `.claude/rules/` after B2 lands, then run `uv run python build/scripts/build_all.py --check`; it exits 2 and `git diff --exit-code` over the four trees still shows the hand edit untouched.
6. [ ] REQ-026-006 WHEN a contributor adds a class to the binplace manifest, THE SYSTEM SHALL read the manifest as data from `templates/platforms/`, so adding a class is a manifest row, not a code branch. Verification: `grep -n "class:" templates/platforms/*.yaml` (or the manifest's chosen key name) lists one row per migrated class with no matching new `if` branch required in `build_all.py`'s binplace function for that class.
7. [ ] REQ-026-007 WHEN `assert_no_claude_writes` runs inside `build_all.py`, THE SYSTEM SHALL compute its `allowed_paths` argument from the binplace manifest's full row set (every migrated class), not from the ADR-108 skill-only set alone, and SHALL still report a violation and exit 2 for any `.claude/` write outside that manifest. Verification: a pytest that loads `templates/platforms/binplace.yaml` and asserts set equality between the manifest-derived allowlist and the `allowed_paths` argument `build_all.py` actually passes to `assert_no_claude_writes`.
8. [ ] REQ-026-008 WHEN B6 lands, `.claude-plugin/marketplace.json` SHALL name exactly one Claude-side plugin, `project-toolkit`, sourced at `./src/claude`, and SHALL NOT carry a `claude-agents` entry; `.claude/.claude-plugin/plugin.json` SHALL no longer exist. Verification: `jq '.plugins | length' .claude-plugin/marketplace.json` returns 1 and `jq -r '.plugins[0].source' .claude-plugin/marketplace.json` returns `./src/claude`; `test -f .claude/.claude-plugin/plugin.json` exits nonzero.
9. [ ] REQ-026-009 WHEN any of B1 through B5 lands, its class SHALL carry its own drift-gate row in `scripts/validation/pre_pr_sequence.py`, its own NO-REGEN sentinel handling (`regen_guard.py`), and its own symlink and resolved-containment checks over its install paths, mirroring the shape `build/scripts/skill_templates.py` and `skill_template_grammar.py` already implement for skills, SO THAT a class does not inherit skills' checks by assumption. Verification, per class: `grep -n '_Gate("<Class> Template Drift"' scripts/validation/pre_pr_sequence.py` returns one match; `uv run pytest tests/build_scripts/test_<class>_templates.py -v` passes including a symlinked-install-path negative case.
10. [ ] REQ-026-010 WHEN the migration proceeds, THE SYSTEM SHALL land one PR series per class in the order agents, rules, remaining skills, hooks and settings, lib, marketplace switch, with a class split into batches only when its file count exceeds the repository's five-to-eight-file-per-PR precedent, and SHALL keep `build_all.py --check` green after every batch. Verification: each task's `Dependencies` section (TASK-032 depends on TASK-031, TASK-033 on TASK-031 and TASK-032, and so on through TASK-036) names the same relative order this criterion states, and the plan's milestone checkboxes in `.agents/plans/active/adr-109-template-first-distribution.md` are checked off in that order; for the 93-skill batch, each batch PR touches at most ten files (`git show --stat <sha> | tail -1` on that batch's merge commit).
11. [ ] REQ-026-011 WHEN B1 renders an agent, THE SYSTEM SHALL compose it from two new per-provider templates, `templates/agents/<stem>.claude.md.tmpl` and `templates/agents/<stem>.copilot.md.tmpl`, sharing common text through partials under `templates/agents/partials/`, with any Claude-only section confined to the `.claude.md.tmpl` variant or a Claude-only partial; `templates/agents/<stem>.shared.md` SHALL remain unchanged as the VS Code source until a later record migrates that seam, SO THAT the asymmetric content Q2 measures (1,414 lines existing only in `src/claude/`, 622 existing only in the shared template, across 18 of 31 pairs, plus two frontmatter-only flags) has a home in the template layer instead of being silently dropped by a single shared render. Verification: `ls templates/agents/*.claude.md.tmpl templates/agents/*.copilot.md.tmpl | wc -l` returns 62 (31 pairs); `ls templates/agents/*.shared.md | wc -l` still returns 31; `ls templates/agents/partials/*.mustache | wc -l` returns a nonzero count.
12. [ ] REQ-026-012 WHEN B1's compiler renders `src/claude/agents/<stem>.md` for the first time, THE SYSTEM SHALL produce output byte-identical to today's `src/claude/<stem>.md` for every one of the 31 agents, frontmatter included, and SHALL leave `src/copilot-cli/agents/` byte-identical to its pre-B1 output and `src/vs-code-agents/` unaffected (it keeps rendering from the unchanged `templates/agents/<stem>.shared.md`), pinned by a fixture test, SO THAT the class migration itself introduces zero content change; reconciling the 18 pairs' divergent content and the two frontmatter-only flags into shared partials is deferred to later, per-agent pull requests the owner signs off on individually, not bundled into B1. Verification: `git diff --exit-code -- src/claude/agents src/copilot-cli/agents src/vs-code-agents` against a pre-B1 snapshot exits 0 immediately after B1's first `build_all.py` run; `uv run pytest tests/build_scripts/test_agent_templates_lossless.py -v` passes.
13. [ ] REQ-026-013 WHEN B1 lands, `src/copilot-cli/agents/<stem>.md` SHALL render from `templates/agents/<stem>.copilot.md.tmpl`, not from a copy of `.claude/agents/`. `templates/platforms/copilot-cli.yaml`'s `agents` stanza's `sourceDir` field is documentation bookkeeping only: `build/generate_agents.py` never reads that field (it takes only `--templates-path` and `--output-root`, verified 2026-09-11 by grep over `build/generate_agents.py` for `sourceDir`, zero matches), so repointing it changes no rendered byte; it is updated so the manifest stops naming a `.claude/` path it no longer describes. Verification: `grep -n "sourceDir" templates/platforms/copilot-cli.yaml` shows the `agents` stanza's value outside `.claude/`; `uv run pytest tests/build_scripts/test_agent_templates.py -k copilot` passes, asserting `src/copilot-cli/agents/<stem>.md` is byte-identical to a render of `templates/agents/<stem>.copilot.md.tmpl`; `uv run python build/scripts/build_all.py --check` exits 0 immediately after the change on a tree with no other drift.
14. [ ] REQ-026-014 WHEN each of B1 through B5 lands, `build/scripts/build_all.py`'s `OWNED_PREFIXES` tuple SHALL widen to include that class's newly binplaced `.claude/`- and `.github/`-rooted install paths (B1: `.claude/agents/`; B2: `.claude/rules/`; B3: `.claude/skills/`; B4: `.claude/hooks/`, `.github/hooks/`; B5: `.claude/lib/`), SO THAT the unreachable-owned-path check (issue #4632: a symlinked, unreadable, or nested-repository path under `OWNED_PREFIXES` aborts `--check` with exit 2) covers every tree the binplace step writes, not only `src/` and `.github/instructions/` as it does before this record. Verification, per class after its PR: `grep -n "OWNED_PREFIXES" -A 8 build/scripts/build_all.py` lists that class's install path in the tuple; symlinking that install path and running `uv run python build/scripts/build_all.py --check` exits 2.

## Rationale

Each acceptance criterion binds to one clause of ADR-109's Decision (sections 1 through 4, 6, 7) so a reader who traces this requirement's numbering back to the ADR finds the exact sentence it tests, the same discipline REQ-025 held against ADR-108. No criterion invents a mechanism the ADR does not already specify.

## Buy-vs-build decision

N/A (approved capability extension of ADR-108). ADR-109 explicitly generalizes ADR-108's already-accepted compile-and-drift-gate mechanism to more classes using the same engine (`chevron` for markdown classes, byte copy for hooks and lib); no new tool or library decision is introduced.

## Complexity classification

Engineering tier 4. Cynefin: Complicated (known technique per ADR-108, expert sequencing across six PRs, one governance amendment already recorded in ADR-109 rather than pending). Methodology: land B1 through B6 in the stated order, each with its own gate and tests before the next begins. ADR cross-reference: ADR-109, which supersedes ADR-052 at acceptance and amends ADR-107 property 1 and REQ-003 D4, D9, REQ-003-010.

## Out of scope

- VS Code agents (`src/vs-code-agents/`); ADR-109 section 5 states this record does not touch that seam.
- REQ-003 D8 (`applyTo:` instructions verification for Copilot CLI); ADR-109 section 6 leaves it unchanged and states no new evidence was found.
- `.github/workflows` (CI pipeline definitions); not a class ADR-109 enumerates.
- Rewriting ADR-052's Migration Plan phases; ADR-109 states they are not carried forward.
- Cutting or rewriting any rule, agent, or hook's content; every migration renders the current content through a template, unchanged in substance.
- Reconciling the 18 agent pairs' divergent Claude-only and Copilot-only content into shared partials; B1's render is lossless (criterion 12), not reconciled, by design.

## Deferred

- Migrating `.github/prompts/`'s 21 non-`pr-quality-gate` files to a template. Owner: whoever runs that wave, after B4.
- Requiring code-owner review before B4 writes executable hook configuration. Owner: `rjmurillo`, per ADR-109's Negative consequence naming this as an open ruleset decision.
- Confirming B3's exact batch size and count before work starts. Owner: `rjmurillo`.
- Reconciling the 18 agent pairs' divergent content into shared `templates/agents/partials/`. Owner: `rjmurillo`, one pull request per agent, after B1's lossless render lands.
- Repointing `templates/platforms/copilot-cli.yaml`'s `skills`, `rules`, and `lib` stanzas' `sourceDir`, and its hooks `scriptSource`/`settingsSource`, away from `.claude/`. Owner: each class's own migration task (B2 rules, B4 hooks, B5 lib); skills' stanza is deliberately left pointed at `.claude/skills` because ADR-108's architecture keeps `.claude/skills/<name>/SKILL.md` as the compiled intermediate the existing `generate_skills.py` copy step reads, unchanged by this record.

## Open questions

- Whether the default-branch ruleset gains `require_code_owner_review: true` before B4 lands, given B4 is the first class to write executable hook configuration through the binplace step. Owner: `rjmurillo`.
- B3's batching plan: how many batches, what size each, in what order, for the 93 remaining skills. Owner: `rjmurillo`; ADR-109 section 7 sets only the ceiling (five to eight files per PR, ten-file cap), not the plan.
- Whether a class's `sourceDir` in `templates/platforms/copilot-cli.yaml` should forward-declare its post-migration `templates/<class>` path before that class's own compile module exists (breaking the Copilot mirror until the migration PR lands) or wait until the migration PR itself repoints it (the path this record takes for B2, B4, B5, leaving a `.claude/`-rooted `sourceDir` in place until each class's own task changes it). Owner: `rjmurillo`.

## CVA summary

Common: every class moves from a hand-maintained install-tree file to a `templates/` source rendered by one compile step, bin-placed by one shared binplace step, gated by one class-scoped drift check. Varies: the compile engine per class (chevron for agents, rules; byte copy plus a settings and hooks-json render for hooks; direct copy for lib, no template); the number of install trees a class's output reaches (agents and rules reach four trees, lib reaches two `lib/` copies, hooks reach `.claude/`, `.github/hooks/`, and both plugin `hooks.json` files). Relationship: a one-to-many between one manifest row and the install paths it names, resolved by one binplace step reading the manifest as data.
