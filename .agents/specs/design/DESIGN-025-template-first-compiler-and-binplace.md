---
type: design
id: DESIGN-025
title: Per-class compile modules and the binplace step for template-first distribution
status: draft
priority: P1
related:
  - REQ-026
  - REQ-003
  - ADR-108
  - ADR-109
  - TASK-031
  - TASK-032
  - TASK-033
  - TASK-034
  - TASK-035
  - TASK-036
created: 2026-09-11
updated: 2026-09-11
adr: ADR-109
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

# DESIGN-025: Per-class compile modules and the binplace step for template-first distribution

## Requirements Addressed

REQ-026-001 through REQ-026-014, per the numbering in `.agents/specs/requirements/REQ-026-template-first-plugin-distribution.md`.

## Design Overview

ADR-109 generalizes ADR-108's compile-and-drift-gate shape from one class (skills) to agents, rules, hooks and settings, with lib as a copy-only exception. This design reuses that shape directly: `build/scripts/skill_templates.py` and its sibling `skill_template_grammar.py` are the reference implementation every new per-class module mirrors, not a pattern restated from scratch. Two new pieces make the generalization possible: a binplace step, because ADR-109 adds a second output hop (plugin tree, then install tree) that ADR-108 never needed since skills render straight into `.claude/skills/`; and the binplace manifest, a data file naming every class's source, plugin-tree output, and install-tree output, so `assert_no_claude_writes`'s allowlist and the binplace step itself both read one file instead of each class adding its own code branch.

## Component Architecture

```text
templates/agents/<stem>.claude.md.tmpl   canonical (new, B1; Claude-only sections)
templates/agents/<stem>.copilot.md.tmpl  canonical (new, B1; Copilot-only sections)
templates/agents/partials/*.mustache     canonical, shared (new, B1; ADR-108 composition shape)
templates/rules/<name>.md                canonical (new, B2)
templates/hooks/                         canonical (new, B4; the hooks class only: 13 executables, hooks.json,
                                          dispatch_groups.json, PreToolUse/markdownlint-safe-config.yaml (16
                                          files), plus a separate settings.json template; the 7 doc files
                                          under .claude/hooks/ are not in the class)
scripts/{hook_utilities,github_core,ai_review_common}/   canonical, exception (lib)
templates/skills/<name>.SKILL.md.tmpl    canonical (existing, ADR-108, unchanged)
        |
        |  build/scripts/agent_templates.py    (new, B1; composes two outputs per agent from shared partials, per DESIGN-024's own composition shape, not a single-target mirror)
        |  build/scripts/rule_templates.py     (new, B2; mirrors skill_templates.py)
        |  build/scripts/hook_templates.py     (new, B4; byte-copy + settings/hooks.json render)
        |  build/scripts/skill_templates.py    (existing, ADR-108; B3 changes its render target from
        |                                       .claude/skills/ directly to src/claude/skills/, binplaced back)
        |  build_all.py lib step               (absorbs sync_plugin_lib.py's SYNC_PAIRS, B5)
        v
src/claude/{agents,rules,skills,hooks,lib}/     plugin tree: Claude Code (project-toolkit, post-B6); AGENTS.md and claude-instructions.template.md stay at the src/claude/ root, not under agents/
src/copilot-cli/{agents,skills,instructions,hooks,lib}/   plugin tree: Copilot CLI (unchanged layout)
        |
        |  build_all.py binplace step (new): reads templates/platforms/binplace.yaml,
        |  copies each plugin-tree path to its install-tree path, one pass per manifest row
        v
.claude/{agents,skills,rules,hooks}/, .claude/settings.json     install tree: Claude Code (repo-local)
.github/{instructions,agents,hooks}/, .github/prompts/pr-quality-gate-*.md   install tree: Copilot CLI (repo-local)

build/scripts/build_all.py               orchestrates render, then binplace, in one run;
                                          assert_no_claude_writes(allowed_paths=manifest.claude_paths())
scripts/validation/pre_pr_sequence.py    one _Gate per migrated class, plus the existing
                                          "Skill Template Drift" and "Generated Artifact Staleness" rows
```

## Technology Decisions

| Decision | Choice | O5 source | Rationale |
|---|---|---|---|
| Markdown-class compile engine | `chevron`, unchanged from ADR-108 | DR1 | Agents and rules are markdown with frontmatter, the same shape ADR-108 already compiles for skills; no new engine decision to make |
| Agent composition shape | Two NEW per-provider templates per agent (`<stem>.claude.md.tmpl`, `<stem>.copilot.md.tmpl`), sharing text through `templates/agents/partials/*.mustache`, both compiled by the same chevron engine and grammar module skills already use; `templates/agents/<stem>.shared.md` is not replaced, it stays the `src/vs-code-agents/` source unchanged until a later record migrates that seam | DR1 | Measured 2026-09-11 (REQ-026 Q2): 18 of 31 agent pairs already diverge in body content between `templates/agents/*.shared.md` and `src/claude/<name>.md`, 1,414 lines existing only in the Claude copy and 622 only in the shared template, plus a two-file frontmatter divergence on `isolation_required: true`; a single shared template per agent would silently drop the Claude-only content on first render, so B1 needs two composed outputs, not one, from the start |
| Agent B1 render fidelity | Lossless first render: `src/claude/agents/<stem>.md` byte-identical to today's `src/claude/<stem>.md`; `src/copilot-cli/agents/` unchanged; pinned by a fixture test | DR1 | Reconciling the 18 divergent pairs into genuinely shared partials is a content decision the owner signs off on per agent, not a mechanical property the migration PR can safely assert; B1 proves the pipe carries the content unchanged, later PRs decide what becomes shared |
| Hooks and settings compile engine | Direct byte copy for hook scripts; a small render step for `.claude/settings.json` and `hooks.json` (JSON, not mustache) | DR1, DR6 | ADR-109 section 3 states hooks are "Python and JSON, not markdown with frontmatter: the compile is a byte copy for scripts and a render for `settings.json` and `hooks.json`"; introducing mustache tags into JSON or Python source would be a second grammar to maintain for no benefit |
| Lib compile engine | Direct byte copy of three named packages, relative-import rewrite on copy (absorbs `scripts/sync_plugin_lib.py`'s `SYNC_PAIRS` logic) | DR6 | The packages carry absolute imports at their canonical path; a template layer would need to reproduce chevron rendering for Python source, which buys nothing over a copy plus the existing import-rewrite regex `sync_plugin_lib.py` already uses |
| Binplace manifest format | YAML under `templates/platforms/`, one new file (`binplace.yaml`), alongside the existing per-platform generator manifests (`copilot-cli.yaml`, `visual-studio.yaml`, `vscode.yaml`) | DR3 | Those three files already establish the repository's convention for a generator manifest: a mapping of `sourceDir`/`outputDir`/`mode` keys read by a Python generator; the binplace manifest reuses that convention for the plugin-tree-to-install-tree hop instead of a fourth ad hoc format |
| `assert_no_claude_writes` allowlist derivation | Computed at run time from the manifest's `.claude/`-rooted rows, replacing the ADR-108-only `skill_templates.owned_targets()` call | DR3 | ADR-109 section 6 states the allowlist "generalizes to an allowlist equal to the binplace manifest"; reading the manifest keeps one source of truth instead of a second hardcoded set that could drift from it |

## Decision-rule Traceability

| Decision rule | Source | Where enforced |
|---|---|---|
| DR1 (plugin-tree file equals canonical-source render) | `.agents/specs/ontology/template-first-distribution.md` O5 | Each new compile module's `compile_all`, mirroring `skill_templates.compile_all` |
| DR2 (install-tree file equals plugin-tree counterpart) | same | The binplace step's own compare-then-copy loop |
| DR3 (writes under `.claude/` confined to the manifest) | same | `build_all.py`'s `assert_no_claude_writes(allowed_paths=...)`, allowlist computed from the manifest |
| DR4 (NO-REGEN sentinel suspends the gate, never silent) | same | Each compile module and the binplace step call `regen_guard.detect_reason`; WARN, nonzero exit, never a silent skip |
| DR5 (unmigrated class untouched) | same | A class's compile module runs only when its `templates/<class>/` directory exists, mirroring `skill_templates.discover`'s "absent directory yields an empty mapping" rule |
| DR6 (lib exception) | same | `build_all.py`'s lib step, absorbing `SYNC_PAIRS`; no `templates/lib/` tree is ever created |
| DR7 (B6 one-way for an already-updated consumer) | same | Rollback section below; not a runtime check, a documented consequence of the marketplace switch |
| DR8 (each class implements its own checks) | same | Per-class Test Plan below; no shared base class is introduced that a new class could silently omit overriding |
| DR9 (agent variant pair's first render is byte-identical to today's output) | same | `tests/build_scripts/test_agent_templates_lossless.py`, the fixture test pinning both `.claude.md.tmpl` and `.copilot.md.tmpl`'s initial render against a pre-B1 snapshot of `src/claude/<stem>.md` and `src/copilot-cli/agents/<stem>.md` |

## Per-class compile modules

Each new module (`build/scripts/agent_templates.py`, `rule_templates.py`, `hook_templates.py`) is split the same way ADR-108 split skills into `skill_templates.py` (filesystem discovery, allowlist, compile orchestration) and `skill_template_grammar.py` (grammar, partial-tree validation, render). Agents and rules reuse the grammar module unchanged, since both are markdown-with-partials like skills; hooks does not need it, since its compile is a byte copy and a JSON render, not a mustache render.

| Function | Contract (mirrors `skill_templates.py`) |
|---|---|
| `discover(repo_root) -> dict[str, Path]` | `{name: templates/<class>/<name>.<ext>}` for every file matching the class's template suffix; an absent `templates/<class>/` directory yields an empty mapping, not an error |
| `owned_targets(repo_root) -> set[Path]` | The set of install-tree paths this class's discovered templates own; contributes to the binplace manifest's derived allowlist the same way `skill_templates.owned_targets` does today |
| `check_grammar(text) -> list[str]` (agents, rules only) | Delegates to `skill_template_grammar.check_grammar`; hooks has no grammar step |
| `render(tmpl_path, partials_dir) -> str` (agents, rules only) | Delegates to `skill_template_grammar.render`; hooks renders JSON with `json.dumps` after a dict merge, not chevron |
| `compile_all(repo_root, *, validate, what_if) -> CompileResult` | Same shape as `skill_templates.compile_all`: skip with WARN and nonzero exit when `regen_guard.detect_reason(target)` is not `None`; in validate mode compare and record drift; otherwise write when bytes differ. Returns written, skipped, drifted, and an aggregate exit code, worst-code-wins, per `AGENTS.md` Standards (0 ok, 1 logic, 2 config) |

Agents' B1 migration is not a bare retarget of the existing `templates/agents/*.shared.md` files, because those files are not lossless against `src/claude/<name>.md` today (REQ-026 Q2: 18 of 31 pairs already diverge, 1,414 lines Claude-only, 622 shared-template-only, plus a two-file `isolation_required: true` frontmatter divergence). `agent_templates.py` therefore discovers TWO NEW templates per agent, `templates/agents/<stem>.claude.md.tmpl` and `templates/agents/<stem>.copilot.md.tmpl`, both composed from `templates/agents/partials/*.mustache` using the same grammar and render functions skills and rules use, with any Claude-only section written directly into the `.claude.md.tmpl` variant instead of a partial (since it has exactly one consumer). `discover()` for this class returns `{stem: (claude_tmpl_path, copilot_tmpl_path)}`, a pair per agent rather than a single path, and `compile_all` renders both members of the pair in the same pass. The initial population of these two templates, for every one of the 31 agents, is generated FROM the current `src/claude/<stem>.md` and the current `templates/agents/<stem>.shared.md` respectively, so the first render is byte-identical to both of today's outputs (Design Overview above, "Agent B1 render fidelity"); no partial is shared across the two variants of a given agent until a later, owner-approved, per-agent pull request extracts one. `templates/agents/<stem>.shared.md` itself is NOT replaced or deleted: it stays exactly as it is today, the unchanged source `build/generate_agents.py` renders `src/vs-code-agents/` from; this record does not migrate that seam (ADR-109 section 5). `.github/agents/` (the Copilot mirror) is repointed to render from the new `.copilot.md.tmpl` variant; `src/claude/agents/<stem>.md` is the new target rendered from the `.claude.md.tmpl` variant. `AGENTS.md` and `claude-instructions.template.md` live at the `src/claude/` root today, not inside `.claude/agents/` (verified 2026-09-11: `ls src/claude` lists both at the root; neither is under `.claude/agents/`, the `sourceDir` `copilot-cli.yaml`'s `agents` stanza names before B1). `excludeFilenames: ["AGENTS.md", "CLAUDE.md"]` on that stanza is the mechanism for a different pair of filenames (`CLAUDE.md`, which does not exist at `src/claude/` root, not `claude-instructions.template.md`) and applies only to what that stanza's `sourceDir` enumerates; it never excluded `claude-instructions.template.md`, because that file was never a candidate to begin with. The real mechanism this class relies on is `agent_templates.py`'s discovery step: it enumerates `templates/agents/<stem>.claude.md.tmpl` files, one per agent stem, so a file with no matching template (`AGENTS.md`, `claude-instructions.template.md`) is never a render target and stays exactly where it is, untouched by this class and not moved under `agents/`. `build/scripts/validate_install_parity.py`'s `src-claude` matching pattern and `detect_agent_drift.py`'s comparison pairs are rewritten in the same PR to match the new `src/claude/agents/<name>.md` path, per ADR-109 section 2.

## The binplace step in `build/scripts/build_all.py`

A new function, `_binplace(repo_root, *, check) -> int`, runs after every class's render step and before `assert_no_claude_writes`'s post-generation snapshot. It reads the manifest (below), and for each row whose `plugin_tree` output exists (a class that has been migrated), compares the plugin-tree file to its `install_tree` counterpart; in write mode it copies on a mismatch, in `--check` mode a mismatch is reported as staleness and nothing is written, matching the existing staleness exit code `_build_skills` already uses. Two manifest rows carry no `plugin_tree` value, because no plugin consumes them: `.claude/settings.json` (repo-local Claude Code configuration, rendered directly from `templates/hooks/settings.tmpl` with no plugin-tree hop) and the 21 non-`pr-quality-gate` `.github/prompts/` files (unmanifested, hand-maintained, per ADR-109 section 3). The twelve `pr-quality-gate-*.md` prompts are manifest rows whose compile step is the existing `build/scripts/generate_pr_quality_prompts.py`, reused unchanged as the compile function for that row.

"One command" means write atomicity across the render and binplace steps in one `build_all.py` invocation, not live reload of an already-running session; ADR-109 section 3 states this explicitly and this design does not add a reload mechanism.

## Binplace manifest schema

`templates/platforms/binplace.yaml`. One top-level list, `rows`, each entry:

```yaml
rows:
  - class: agents
    source: templates/agents        # .claude.md.tmpl / .copilot.md.tmpl pairs, per agent_templates.py
    plugin_tree: src/claude/agents
    install_tree: .claude/agents
  - class: skills
    source: templates/skills        # existing ADR-108 tree, unchanged by this row's addition
    plugin_tree: null                # B1: no plugin-tree hop yet; B3 repoints this to src/claude/skills
    install_tree: .claude/skills
    compile: skill_templates          # delegates to skill_templates.owned_targets, not a class-wide prefix
  - class: rules
    source: templates/rules
    plugin_tree: src/claude/rules
    install_tree: .claude/rules
  - class: hooks
    source: templates/hooks
    plugin_tree: src/claude/hooks
    install_tree: .claude/hooks
  - class: settings
    source: templates/hooks/settings.tmpl
    plugin_tree: null
    install_tree: .claude/settings.json
  - class: lib
    source: scripts/hook_utilities
    plugin_tree: src/claude/lib/hook_utilities
    install_tree: .claude/lib/hook_utilities
  - class: prompts
    source: .claude/skills/review/references
    plugin_tree: null
    install_tree: .github/prompts
    compile: generate_pr_quality_prompts
```

Each row's `install_tree` value is a path prefix under `.claude/` or `.github/`; the binplace step and `assert_no_claude_writes`'s derived allowlist both treat every path under that prefix as owned. A row with `plugin_tree: null` skips the plugin-tree render hop and copies straight from `source` to `install_tree`. Two surfaces carry `plugin_tree: null` permanently, because ADR-109 section 3 names them as having no plugin stage at all (`settings`, `prompts`); the `skills` row carries `plugin_tree: null` only until B3, when the skills class gains its own `src/claude/skills` plugin tree and the row's `plugin_tree` value and `compile` delegation both change (Per-class compile modules, below). The `compile` key is optional and names a Python callable already used for the class's render (skills and prompts reuse existing functions; a class with no such override uses its own compile module's `compile_all`).

B1 ships the manifest with two active rows, `agents` and `skills`, not one. Without a `skills` row from B1 on, `assert_no_claude_writes`'s manifest-derived allowlist would have no entry covering `.claude/skills/<name>/SKILL.md`, and every commit against an ADR-108-templated skill would trip the REQ-003-010 guard the moment the allowlist stops falling back to the old ADR-108-only call (Technology Decisions, above). The `skills` row's `install_tree` stays `.claude/skills` and its targets keep delegating to `skill_templates.owned_targets(repo_root)` (per-skill-directory paths, not a blanket `.claude/skills/` prefix) until B3 moves the class's render target to `src/claude/skills/<name>/SKILL.md` and repoints the row's `plugin_tree` there (TASK-033).

## How `--check` extends to the binplaced trees

`build_all.py --check` runs every class's compile in validate mode (unchanged shape), then runs `_binplace(check=True)`, which performs the same plugin-tree-to-install-tree comparison without writing. A drift at either hop, template-to-plugin-tree or plugin-tree-to-install-tree, produces the same staleness exit code (2) and the same "leave every tree unchanged" guarantee ADR-109 section 3 requires: `--check` verifies all four trees (`src/claude`, `src/copilot-cli`, `.claude`, the manifest-named `.github` paths) are byte-identical to what the templates render, in one pass, reusing the existing `_root_only` gate wrapper convention `pre_pr_sequence.py` already uses for every other validator.

## How `assert_no_claude_writes` derives its allowlist

`build_all.py`'s `run()` function currently computes `claude_allowed_paths = skill_templates.owned_targets(repo_root)` and passes it through to `_run_generators`, which calls `assert_no_claude_writes(repo_root, claude_baseline, preexisting_boundaries=claude_boundaries, allowed_paths=claude_allowed_paths)`; `run()` itself never calls `assert_no_claude_writes` directly. This design replaces that single-class computation with `claude_allowed_paths = binplace_manifest.claude_allowlist(repo_root)`, a function that reads `templates/platforms/binplace.yaml`, filters rows whose `install_tree` starts with `.claude/`, and returns the union of each such row's owned paths (the skills row's contribution is unchanged: it still delegates to `skill_templates.owned_targets` for that one row, since skills' allowlist is scoped per skill directory, not per class-wide prefix, until B3 moves the skills class to a `src/claude/skills` plugin tree). Every other `.claude/` write is still reported and still fails the build, per ADR-109 section 6's restatement of REQ-003-010.

`sourceDir` is not a uniform field: `build/scripts/generate_rules.py`, `build/scripts/generate_skills.py`, and `build_all.py`'s generic `_build_directory_copy` helper (used for lib) all load their stanza's `sourceDir` at run time to resolve that class's copy source, verified 2026-09-11 by grep for `sourceDir` in each file. `build/generate_agents.py` does not: it takes only `--templates-path` and `--output-root` as arguments and hardcodes its glob to `templates/agents/*.shared.md` (verified 2026-09-11: grep for `sourceDir` in `build/generate_agents.py` returns zero matches), so the `agents` stanza's `sourceDir` field in `templates/platforms/copilot-cli.yaml` is inert today and stays inert after B1's repoint.

B1 still repoints `templates/platforms/copilot-cli.yaml`'s `agents` stanza's `sourceDir` off `.claude/agents`, but the change is documentation bookkeeping, not a functional render-source switch: the actual switch happens because `build/generate_agents.py` gains a second output target (`src/claude/agents/`, rendered from `.claude.md.tmpl`) and the Copilot mirror it already renders (`src/copilot-cli/agents/`, via `--output-root`) starts reading from the new `.copilot.md.tmpl` variant instead of `*.shared.md`, both driven by the `--templates-path` argument `_build_agents` already passes, not by the stanza. Repointing the stanza's `sourceDir` anyway keeps the manifest from asserting a `.claude/agents` path that is no longer true in substance, even though no code path consumes it for agents. The `skills`, `rules`, and `lib` stanzas, and the hooks `scriptSource`/`settingsSource` fields, are deliberately left naming `.claude/` until each of those classes' own migration task (B2, B4, B5) repoints them: repointing a stanza before its class's `templates/<class>` tree exists and is populated would break the Copilot mirror in the interim, since `generate_rules.py` and `generate_skills.py` genuinely read that field. Skills' stanza is a partial exception: it is never repointed by this record at all, because ADR-108's architecture keeps `.claude/skills/<name>/SKILL.md` as the compiled intermediate `generate_skills.py`'s existing directory-copy step reads, and this record does not reopen that design (REQ-026 Open questions records this scoping decision for owner confirmation).

## The `src/claude/` layout move (B1)

Before B1: `ls src/claude` shows agent files flat at the plugin root (`src/claude/<name>.md`, 33 files measured 2026-09-11) with no `agents/` subdirectory, plus `src/claude/security/references/` (three files: `dependency-risk-scoring.md`, `powershell-security-checklist.md`, `threat-model-template.md`, verified 2026-09-11), a nested reference tree the `security` agent uses; `build/scripts/validate_install_parity.py`'s `src-claude` pattern matches `^src/claude/(?P<name>[^/]+)\.md$`. After B1: the 31 agent files render to `src/claude/agents/<name>.md`, the layout `.claude/agents/` already uses; `src/claude/security/` moves alongside the agent it serves, to `src/claude/agents/security/`, and the parity rewrite below covers that move too. `AGENTS.md` and `claude-instructions.template.md`, the two plugin-root files that are not one of the 31 agents, stay exactly where they are today: neither has a matching `templates/agents/<stem>.claude.md.tmpl`, so `agent_templates.py`'s discovery step never treats either as a render target, and no compile module touches them. The `src-claude` pattern and `detect_agent_drift.py`'s comparison pairs are rewritten in the same commit that lands the new render target, so no commit exists where the tool and the tree disagree on the path shape. A consumer of the `claude-agents` plugin (retired at B6) sees the path move at their next plugin update, per ADR-109 section 2.

## Skills and hooks gain a `src/claude/` plugin tree (B3, B4)

ADR-109 section 2 names `src/claude/{agents,skills,rules,hooks,lib}` as the full plugin tree, but B1 alone only delivers the `agents` member; without a further step, no task ever renders `src/claude/skills/` or `src/claude/hooks/`, and B6's marketplace switch would point `project-toolkit` at an incomplete tree. Two migration steps close this gap.

B3 (skills) changes `skill_templates.compile_all`'s render target from `.claude/skills/<name>/SKILL.md` directly to `src/claude/skills/<name>/SKILL.md`; the binplace step then copies `src/claude/skills/` into `.claude/skills/`, the same two-hop shape every other migrated class already uses. The manifest's `skills` row (added at B1, above) switches its `plugin_tree` from `null` to `src/claude/skills` and its `compile` delegation from a bare `skill_templates.owned_targets` allowlist call to the same function now scoped against the plugin tree; `install_tree` stays `.claude/skills`. `generate_skills.py`'s existing Copilot-mirror copy step, which reads `.claude/skills/` per `copilot-cli.yaml`'s `skills` stanza, is repointed to read `src/claude/skills/` instead, so it reads the plugin tree rather than the install tree the binplace step also writes; this keeps the Copilot mirror one hop away from the true source instead of two.

B4 (hooks) renders `templates/hooks/`'s 13 executables, `hooks.json`, and `dispatch_groups.json` into `src/claude/hooks/` and `src/claude/hooks.json` first, then binplaces that plugin tree into `.claude/hooks/` and, for the Copilot side, into `.github/hooks/*.json` for the first time (Decision section 3, D6). `markdownlint-safe-config.yaml` renders into `src/claude/hooks/PreToolUse/markdownlint-safe-config.yaml` alongside the scripts it configures. `.claude/settings.json` is the one member of this class that never gains a `src/claude/` counterpart: its manifest row keeps `plugin_tree: null` because it ships in no plugin (Decision section 3), so it renders straight from `templates/hooks/settings.tmpl` to `.claude/settings.json` with no intermediate hop.

B6's Implementation Notes (TASK-036) depend on both of these: the marketplace switch is only safe once `src/claude/skills/` and `src/claude/hooks/` both exist and match their templates, not merely once `.claude/skills/` and `.claude/hooks/` do.

## The lib copy absorbing `scripts/sync_plugin_lib.py`

`scripts/sync_plugin_lib.py`'s `SYNC_PAIRS` list (three whole-package syncs with relative-import rewriting: `scripts/hook_utilities`, `scripts/github_core`, `scripts/ai_review_common`, each into a `.claude/lib/<pkg>` destination) and its `SYNC_FILE_PAIRS` list (two individual file copies, sourced from `scripts/hook_utilities/bootstrap.py` and `scripts/validation/validate_review_marker.py`) move inside `build_all.py`'s lib step as-is at B5, same regex-based `IMPORT_CONVERSIONS` table, same destinations. The step then runs inside the one `build_all.py` invocation instead of as a separately invoked script, so there is no second command whose order matters, and `scripts/sync_plugin_lib.py` is deleted as a standalone entry point at B5 (its logic, not its behavior, is what moves). `scripts/ci/check_plugin_lib_mirrors.py` is rewired to check the new single-step output or retired if `build_all.py --check` supersedes it; the B5 task decides which, based on whether any caller outside CI still invokes it directly.

The two `SYNC_FILE_PAIRS` destinations do not share a prefix: `scripts/hook_utilities/bootstrap.py` lands at `.claude/lib/bootstrap.py`, which the `lib` manifest row's `.claude/lib` `install_tree` prefix already covers, but `scripts/validation/validate_review_marker.py` lands at `.claude/skills/review/scripts/validate_review_marker.py` (verified 2026-09-11, `scripts/sync_plugin_lib.py`'s `SYNC_FILE_PAIRS` list), a path under `.claude/skills/`, outside every `lib` row's prefix and outside the `skills` row's per-skill-directory allowlist (`skill_templates.owned_targets` only names `.claude/skills/<name>/SKILL.md`, never a sidecar script). B5 adds a dedicated manifest row for this one file, either a narrow `skills-sidecar` class or folded into the `skills` row as a second, explicit path, so `assert_no_claude_writes` allowlists it instead of failing every B5 build on a write the manifest never named.

`.claude/rules/generated-artifacts.md`'s "Generator order: sync before build" section is rewritten at B1, not B5, because B1 is the task that introduces the binplace manifest and the "one atomic operation" model the section needs to describe; the rewrite documents the target architecture (one manifest, one binplace step, per-class ownership) and states explicitly that the lib package's specific two-hop ordering hazard the section names is not yet closed and remains load-bearing until B5 lands, at which point B5 removes that residual sentence. This keeps the rule file accurate at every point in the migration instead of describing a stale two-script model through four intervening classes' PRs, or describing a fully-closed hazard before it actually closes.

## The marketplace switch (B6)

`.claude-plugin/marketplace.json` drops the `claude-agents` entry (`./src/claude`) and repoints `project-toolkit`'s `source` from `./.claude` to `./src/claude`. `src/claude/.claude-plugin/plugin.json` becomes the `project-toolkit` manifest; `.claude/.claude-plugin/plugin.json` is deleted. `.github/plugin/marketplace.json` is unchanged in `source`; only its `project-toolkit` description's "generated from Claude canonical sources" wording is updated once templates, not `.claude/`, are the true canonical source. No manifest gains a `version` field, per ADR-092, unaffected by this design.

## Failure modes

| Failure | Detection | Handling |
|---|---|---|
| Stale hand edit to an install-tree file after its class migrates | `build_all.py --check` compares install tree to plugin-tree render | Exit 2, staleness reported, file left unchanged; the same behavior ADR-108 already gives skills |
| Missing partial (agents, rules) | The class's compile module delegates to `skill_template_grammar._validate_partial_tree`, which recurses through every included partial | Exit 2 before any render, naming the template and the missing slug |
| Symlinked install-tree path | Per-class containment check, mirroring `skill_templates._name_validation_error`'s five checks (symlink on the directory, symlink on the leaf file, resolved-path containment for both the class root and the specific target) | Exit 2, that target excluded from the class's discovered set, named in the error |
| Manifest row pointing outside the repository | `binplace_manifest.claude_allowlist` resolves every row's `install_tree` against `repo_root` and rejects a resolved path outside it, the same CWE-22 defense `skill_templates.py` already applies per skill | Exit 2 at manifest load, before any class's compile runs |
| Concurrent PRs regenerating the same tree | `build_all.py --check` in CI on each PR's branch; a merge conflict on the rendered files themselves surfaces as a normal git conflict, not a silent overwrite, since the rendered files are committed, not gitignored | Standard PR-merge conflict resolution; no new mechanism, same as any other generated-and-committed tree today |
| A class's compile module written to skip the symlink or containment check entirely | DR8 names this as a class-by-class obligation, not inherited automatically | Caught by that class's own test suite (Test Plan below) before merge, not by a shared runtime guard; this is a documented review obligation, not a code-enforced one |

## Security Considerations

Path containment (no write outside `repo_root`) and no-symlink-following are enforced per class, mirroring `skill_templates._name_validation_error`'s CWE-22 and CWE-59 defenses: a real, non-symlinked class-root directory, resolved inside the repository root, with no symlinked leaf file at the target path. The binplace manifest itself is treated as an input to validate, not trusted blindly: `binplace_manifest.claude_allowlist` resolves every row's paths and rejects one outside the repository before computing the allowlist, so a malformed or malicious manifest row cannot widen `assert_no_claude_writes`'s allowlist to an arbitrary path. No template, partial, or hook script may embed a secret; this is an existing repository-wide rule (`universal.md` MUST 6, no secrets), unchanged by this design, and the existing `security-detection` and CI secret-scanning gates apply identically to the new `templates/rules/` and `templates/hooks/` trees.

## Observability

`build_all.py` already emits a build audit at `build/audit/GENERATION-AUDIT.md` (overwrite-only). This design adds one row per migrated class to that audit, naming the class, whether its compile ran (templates present) or was skipped (no `templates/<class>/` directory yet), and the binplace step's written, skipped, and drifted counts, the same shape `CompileResult` already reports for skills. `pre_pr_sequence.py` gains one `_Gate` row per migrated class ("Agent Template Drift" at B1, "Rule Template Drift" at B2, "Hook Template Drift" at B4), placed alongside the existing "Skill Template Drift" and "Generated Artifact Staleness" rows, so a reader of the gate list sees every class's drift check by name rather than inferring hooks or rules are covered by the general staleness gate alone.

## Testing Strategy

Per module, positive, negative, and edge cases, mirroring `tests/build_scripts/test_generate_skills_template_compile.py`'s shape:

| Module | Positive | Negative | Edge |
|---|---|---|---|
| `agent_templates.py` (B1) | Both variants of a pair (`.claude.md.tmpl`, `.copilot.md.tmpl`) with a shared partial render byte-identical to a fixture; a fixture-pinned losslessness test (`tests/build_scripts/test_agent_templates_lossless.py`) renders all 31 pairs from their B1-initial templates and asserts byte-identity against a pre-B1 snapshot of `src/claude/<name>.md` and `src/copilot-cli/agents/` | Missing partial: exit 2, path and slug named, target untouched; a Claude-only section accidentally left in a shared partial (a losslessness-test regression against the Copilot output) | Agent with only one of the two variant templates present: exit 2, named as an incomplete pair; symlinked `src/claude/agents/<name>/` directory: exit 2 |
| `rule_templates.py` (B2) | Template renders byte-identical to a fixture; both `.claude/rules/` and both Copilot instruction mirrors match | Disallowed tag (`{{var}}`, `{{#s}}`): exit 2, tag printed | Rule with no template during migration: untouched; NO-REGEN sentinel on a rendered rule: unchanged, WARN, exit 1 |
| `hook_templates.py` (B4) | Hook script byte-copies identically; rendered `settings.json` and `hooks.json` match a fixture; `tests/build_scripts/test_generate_hooks_runtime_contract.py`'s pattern is extended with a case that generates `.github/hooks/*.json` and runs the emitted command under the Copilot cloud-agent contract (cwd set to the working directory, `bash` as the only honored interpreter) with a negative control proving a bare relative command fails the same harness | Malformed `settings.json` template (invalid JSON after render): exit 2 | A hook script with no corresponding template during migration: untouched; symlinked `.github/hooks/` directory: exit 2 |
| Binplace step | Manifest row with both `plugin_tree` and `install_tree` binplaces correctly; a row with `plugin_tree: null` copies straight from `source` | Manifest row naming a path outside the repository root: exit 2 at load, before any class compiles | A class with no `templates/<class>/` directory contributes no rows' worth of writes; `--check` on a drifted binplaced file exits 2 and writes nothing |
| `assert_no_claude_writes` allowlist | An allowlisted class-wide write (post-B2, a rule file) passes the guard | A write to a `.claude/` path outside every manifest row still exits 2 | A manifest with rows present but no `skills` row is a FAILING case: `.claude/skills/<name>/SKILL.md` writes are then unallowlisted and the guard must reject them, proving the allowlist never silently reintroduces the pre-B1 ADR-108-only fallback once the manifest exists |

`tests/build_scripts/test_binplace_manifest.py` is new: loads the real `templates/platforms/binplace.yaml` once each class lands and asserts every row's `install_tree` resolves inside the repository and every `class` name is unique. `tests/build_scripts/test_build_all.py` gains the binplace positive and negative cases above, alongside its existing allowlist tests.

## Open Questions

- Whether the binplace manifest's `compile` key (naming an existing function like `generate_pr_quality_prompts`) is the right shape for a class whose render logic predates the manifest, or whether every manifest row should eventually own a dedicated compile module. Owner: whoever migrates the `pr-quality-gate` prompts under this manifest, if that migration happens before B6.
- Whether `scripts/ci/check_plugin_lib_mirrors.py` is rewired or retired once B5 lands; ADR-109's Impact on Dependent Components table leaves both open. Owner: `rjmurillo`, decided in the B5 PR.

## Declined alternative: a code branch per class instead of a manifest

Each class's binplace could be a hardcoded `if class == "agents": ...` branch inside `build_all.py`, avoiding a new YAML file. Declined: ADR-109 section 7 states the manifest is "data, not code: a YAML file under `templates/platforms/`... so adding a class means adding a manifest row, not a code branch," and `assert_no_claude_writes`'s allowlist would then need its own separate hardcoded set to stay in sync with whatever the branches do, reintroducing exactly the two-sources-of-truth problem ADR-109 exists to close.
