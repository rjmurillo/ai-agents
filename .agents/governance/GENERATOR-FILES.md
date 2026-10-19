# Generator-Owned Files

This inventory lists every file tree that the build pipeline generates from a
canonical source. Editing a generated file directly is wasted work: the next
`build_all.py` run overwrites it, and the drift check (`build_all.py --check`)
fails the PR. Edit the source, then regenerate.

If you are about to edit a file under any "Output" path below, stop and edit the
matching "Source" instead.

## Generated trees

| Generator | Source (edit here) | Output (do not edit) | Spec |
|-----------|--------------------|----------------------|------|
| `build/generate_agents.py` | `templates/agents/*.shared.md` | `src/copilot-cli/agents/`, `src/vs-code-agents/` (per platform YAML) | ADR-002 |
| `build/scripts/generate_rules.py` | `src/claude/rules/*.md` plus the repo-only real files in `.claude/rules/` (ADR-119) | `.github/instructions/*.instructions.md`, `src/copilot-cli/instructions/*.instructions.md` | REQ-003-006 |
| `build/scripts/generate_skills.py` | `src/claude/skills/<name>/` (ADR-119: the real directory each shipped `.claude/skills/<name>` links to) | `src/copilot-cli/skills/<name>/` (except `review/scripts/validate_review_marker.py`, rendered from `scripts/validation/` by `lib_mirror.py`) | REQ-003-001 |
| `build/scripts/skill_templates.py` | `templates/skills/<name>.SKILL.md.tmpl` + `templates/skills/partials/*.mustache` | `src/claude/skills/<name>/SKILL.md` (shipped; `.claude/skills/<name>` links to its directory) or `.claude/skills/<name>/SKILL.md` (repo-local), template-owned skills only | ADR-108, ADR-109, ADR-119 |
| `build/scripts/generate_skills.py` (`prune_stale_claude_skill_support`) | the `metadata.distribution` flag of each skill | removes a stale `src/claude/skills/<name>/` left by a skill that became repo-local; copies nothing (ADR-119 retired the `.claude/` to `src/` support-file mirror) | ADR-109 B3 follow-up, ADR-119 |
| `build/scripts/agent_templates.py` | `templates/agents/<stem>.claude.md.tmpl`, `<stem>.copilot.md.tmpl`, `templates/agents/partials/*.mustache` | `src/claude/agents/<stem>.md` and through `build/generate_agents.py` to `src/copilot-cli/agents/<stem>.agent.md` | ADR-109 |
| `build/scripts/rule_templates.py` | `templates/rules/<name>.md` (every rule; a literal `{{` in a rule is written `\{{`) | `src/claude/rules/<name>.md`, linked into `.claude/rules/`; a repo-only rule renders to `.claude/rules/<name>.md` as a real file | ADR-109, ADR-119 |
| `build/scripts/binplace_manifest.py` | `templates/platforms/binplace.yaml` plus the plugin trees it names | `.claude/agents/<name>.md`, shipped `.claude/skills/<name>`, and `.agents/skills/<name>` (to `src/codex/skills`) and shipped `.claude/rules/<name>.md` as relative symlinks (`link: true` rows, `binplace_links.py`), `.claude/hooks/` (plus `.claude/hooks/hooks.json`), `.github/hooks/*.json` | ADR-109, ADR-119 |
| `build/scripts/binplace_manifest.py` (`instructions-github` row) | `src/copilot-cli/instructions/*.instructions.md` | `.github/instructions/` as relative symlinks; repo-only instructions there are real files from `generate_rules.py` | ADR-119 |
| `build/scripts/binplace_manifest.py` (`agents-github` row) | `src/copilot-cli/agents/*.agent.md` | `.github/agents/*.agent.md` as relative symlinks; no shipped Copilot agent may carry `model:` (inherit-only, PR #5040) | ADR-119 |
| `build/scripts/hook_templates.py` | `templates/hooks/` (14 executables, `dispatch_groups.json`, `hooks.json`) plus `templates/hooks/settings.tmpl` | `src/claude/hooks/<rel>`, `src/claude/hooks.json` (plugin root, not nested), and directly `.claude/settings.json` (no plugin-tree hop) | ADR-109 |
| `build/scripts/generate_hooks.py` with `build/scripts/generate_dispatcher.py` | `src/claude/hooks/` + `src/claude/hooks.json` (repointed from `.claude/hooks/` by ADR-109 B4; `hook_templates.compile_all` runs first) | `src/copilot-cli/hooks/` + `src/copilot-cli/hooks/hooks.json`, and through the binplace step to `.github/hooks/*.json` (first binplaced in B4) | REQ-003-007, ADR-068, ADR-109 |
| `build/scripts/build_all.py` (`_build_lib`, via `build/scripts/lib_mirror.py`) | `scripts/{hook_utilities,github_core,ai_review_common}/`, `scripts/hook_utilities/bootstrap.py`, `scripts/validation/validate_review_marker.py` | `src/claude/lib/`, `src/copilot-cli/lib/`, `src/claude/skills/review/scripts/`, `src/copilot-cli/skills/review/scripts/` (then linked into `.claude/lib/` by the `lib` row of `templates/platforms/binplace.yaml`, ADR-119 decision 14; the `skills-sidecar` rows have no install tree, since `.claude/skills/review` links to the plugin directory, ADR-119) | REQ-003-001, REQ-003-002, ADR-109 B5 |
| `build/generate_agent_catalog.py` (`agent-catalog` in `GENERATORS`) | `templates/agents/*.shared.md` | `docs/agent-catalog.md` | `build_all.py` |
| `build/scripts/generate_adr_index.py` (`adr-index` in `GENERATORS`) | `.project-toolkit/architecture/ADR-*.md` frontmatter | `.project-toolkit/architecture/README.md` | `build_all.py` |
| `build/scripts/generate_pr_quality_prompts.py` (not in `GENERATORS`; run by `run_drift_check_ci.py` and the lefthook dry run) | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | REQ-008-01 |

## Hand-maintained sibling copies (NOT generated)

These trees are NOT written by any generator. REQ-003-010 forbids generators from
writing under `.claude/`, except the template-owned skill files ADR-108 enumerates
(two rows above), agent files ADR-109 B1 enumerates (agent_templates.py and
binplace_manifest.py), rule files ADR-109 B2 enumerates (rule_templates.py and
binplace_manifest.py), and hooks-and-settings files ADR-109 B4 enumerates
(hook_templates.py and binplace_manifest.py): a `.claude/skills/<name>/SKILL.md`,
`.claude/agents/<name>.md`, `.claude/rules/<name>.md`, a file under
`.claude/hooks/` (14 executables, `hooks.json`, `dispatch_groups.json`), or `.claude/settings.json` whose
source template exists at run time is generated output, not hand-maintained,
and the exceptions are scoped to exactly those sets. The seven doc files
under `.claude/hooks/` (`AGENTS.md`, five `CLAUDE.md` files, one `README.md`)
are outside the hooks class and stay hand-maintained.
Every other file below is kept in sync by hand and guarded by `check_surface_parity.py`
(driven by `templates/platforms/surface-parity.yaml`), which fails CI when a sibling drifts from its source.

| Path | Role | Guard |
|------|------|-------|
| `.github/agents/security/references/*.md` | Byte copy of `src/claude/security/references/` | `check_surface_parity.py` (`STALE`, `MISSING`, `EXTRA`) |
| `src/copilot-cli/lib/*.py` (top-level modules) | Hand-maintained translation of the `.claude/lib/*.py` top-level modules (`translated`; `paths.py` is listed in `divergent` for the `.agents` root) | `check_surface_parity.py` (`STALE`, `MISSING`, `EXTRA`) |

`templates/platforms/surface-parity.yaml` is the machine-readable inventory of
every surface in this file and the ones it leaves out. Each row names the
surface path, its authority, its generator, the gate that validates it, and a
relation: `generated`, `binplaced`, `mirrored`, `translated`, or `independent`.
`build/scripts/check_surface_parity.py` reads it, and `build_all.py --check`
runs the same checks. A new output path in `binplace.yaml`, a platform YAML, or
`OWNED_PREFIXES` with no row fails as `UNMANIFESTED`; a tracked file under
`src/`, `.claude/`, or `.github/` that no row owns fails as `UNCLASSIFIED`.

ADR-109 B1 moved `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md`, and `src/claude/agents/<stem>.md` into generated output via the agent_templates.py and binplace_manifest.py generators above. ADR-109 B2 moved every `.claude/rules/<name>.md` file (28) the same way via rule_templates.py; `testing.md` is template-owned too, its GitHub Actions example written with the `\{{` escape. ADR-109 B3 gave skills the same two-hop shape: `skill_templates.compile_all` renders `src/claude/skills/<name>/SKILL.md`, and the binplace step copies it onto `.claude/skills/<name>/SKILL.md`; the manifest also gained a `prompts` row (`source: .claude/skills/review/references`, `compile: generate_pr_quality_prompts`, `plugin_tree: null`) that documents the twelve `pr-quality-gate-*.md` files without changing how they are generated. ADR-109 B4 moved the 16-file hooks class (14 executables, `hooks.json`, `dispatch_groups.json`) plus `.claude/settings.json` into generated output via hook_templates.py: `src/claude/hooks/` and `src/claude/hooks.json` render for the first time, `.github/hooks/*.json` is binplaced for the first time, and `.claude/settings.json` renders directly from `templates/hooks/settings.tmpl` with no plugin-tree hop, since it ships in no plugin.

## Equivalence predicates

ADR-107 section 4 requires every artifact class to declare an equivalence
predicate: the statement of what "the projection matches its source" means and
the gate that checks it. This table is that declaration, one row per class. It
covers every entry of `GENERATORS` in `build/scripts/build_all.py` (the Class
column uses the `GENERATORS` name), the generator that runs outside it, and the
hand-maintained trees.

- `derived`: the projection equals `transform(source)` recomputed by the
  generator. An identity transform is legal. Regenerate, then diff.
- `normalized`: the projection equals the source after a declared normalization.
  Normalize both sides, then diff.
- `none`: no predicate. Legal only as a recorded baseline with an owning issue
  and an expiry date. A `none` row whose expiry passes is a finding, not a
  renewal.

There is no `byte` value. Byte equality is `derived` with an identity transform.

| Class | Trees | Predicate | Gate | Issue | Expiry |
|-------|-------|-----------|------|-------|--------|
| `agents` | `src/claude/agents/`, `.claude/agents/`, `.github/agents/`, `src/copilot-cli/agents/`, `src/vs-code-agents/` | `derived` | `build/scripts/build_all.py` with `--check` (pre-PR gate Generated Artifact Staleness) | - | - |
| `agent-catalog` | `docs/agent-catalog.md` | `derived` | `build/scripts/build_all.py` with `--check` | - | - |
| `adr-index` | `.project-toolkit/architecture/README.md` | `derived` | `build/scripts/build_all.py` with `--check` | - | - |
| `lib` | `src/claude/lib/`, `src/copilot-cli/lib/`, `src/codex/lib/` packages, the `.claude/lib/` links, the `review` sidecar validator | `derived` | `build/scripts/build_all.py` with `--check` | - | - |
| `skills` | `src/claude/skills/`, `.claude/skills/`, `src/copilot-cli/skills/`, `src/codex/skills/` | `derived` | `build/scripts/build_all.py` with `--check` | - | - |
| `rules` | `src/claude/rules/`, `.claude/rules/`, `.github/instructions/`, `src/copilot-cli/instructions/` | `derived` | `build/scripts/build_all.py` with `--check` | - | - |
| `hooks` | `src/claude/hooks/`, `.claude/hooks/`, `.claude/settings.json`, `src/copilot-cli/hooks/`, `.github/hooks/` | `derived` | `build/scripts/build_all.py` with `--check` | - | - |
| `pr-quality-prompts` | `.github/prompts/pr-quality-gate-*.md` | `derived` | `build/scripts/run_drift_check_ci.py` (runs the generator with `--dry-run`) | - | - |
| `agent-sources` | `templates/agents/<stem>.shared.md`, `.claude.md.tmpl`, `.copilot.md.tmpl` | `normalized` | `build/scripts/check_agent_source_parity.py` (pre-PR gate Agent Source Parity) | - | - |
| `security-references` | `.github/agents/security/references/*.md` | `derived` | `build/scripts/check_surface_parity.py` (hand-maintained byte copy, identity transform) | - | - |
| `copilot-lib-modules` | `src/copilot-cli/lib/*.py` top-level modules | `derived` | `build/scripts/check_surface_parity.py` (identity transform; `paths.py` is the one `divergent` file the manifest excuses) | - | - |

ADR-107 expected a `none` baseline for three hand-maintained agent trees
(`.claude/agents/`, `.github/agents/`, `src/claude/agents/`). ADR-109 B1 made all
three generated output of the `agents` class, and issue #5688 added the
`agent-sources` predicate for the sources behind them. The table therefore
carries no `none` row today, and the baseline ceiling is zero.

A `none` row writes the owning issue as `#N` and the expiry as `YYYY-MM-DD`; a
`derived` or `normalized` row writes `-` in both cells and opens its Gate cell
with the repo-relative path of the script that checks it, in backticks.
`scripts/validation/check_equivalence_predicates.py` (pre-PR gate Equivalence
Predicates) parses this table and fails on an unknown predicate value, a gate
script that does not exist, a `none` row without an issue or an expiry, a
lapsed expiry, a duplicate class, a `GENERATORS` entry with no row, and any
change to the number of `none` rows that the baseline
`scripts/validation/equivalence_predicates_baseline.json` does not record. The
same baseline holds a floor on the number of rows, so a class row cannot be
deleted to dodge its expiry. Authored-in-place surfaces (relation `independent`
in `templates/platforms/surface-parity.yaml`) are sources with no projection and
carry no row.

## Agent source equivalence (normalized)

Each agent has three hand-written sources under `templates/agents/`:
`<stem>.shared.md`, `<stem>.claude.md.tmpl`, and `<stem>.copilot.md.tmpl`.
The generated trees are covered by regeneration. These three sources are
covered by the `normalized` predicate of ADR-107 section 4, enforced by
`build/scripts/check_agent_source_parity.py` (ADR-107 migration step M3,
issue #5688). It renders both templates and compares each against the shared
source. It runs as the pre-PR gate `Agent Source Parity` and, through
`tests/build_scripts/test_check_agent_source_parity.py::TestLiveRepository`, in
the required `Python Tests` run on every pull request.

| Pair | Compared | Section on one side only |
|------|----------|--------------------------|
| `claude-shared` | rendered Claude template against `<stem>.shared.md` | Skipped. `detect_agent_drift.py` owns the section inventory |
| `copilot-shared` | rendered Copilot template against `<stem>.shared.md` | Fails. Both feed the same platform family |

Tree-specific, dropped from comparison: every frontmatter key except
`description`, `argument-hint`, `role`, and the tool lists. That covers `name`,
`model`, `model_tier`, `isolation_required`, and `metadata` other than
`metadata.role` (the Claude spelling of `role`).

Shared, compared exactly: those three frontmatter keys, the preamble before the
first H2, the body of every H2 section both sides carry, and the order of
those shared sections (pin unit `order`). Before comparing,
the gate applies `detect_agent_drift.normalize_content` (MCP tool prefixes,
handoff invocation spelling, fence language tags, trailing whitespace) and then
ignores blank lines. Nothing else is excused. A repeated H2 name in one source
is a configuration error (exit 2), because a repeat would hide the earlier body.
The normalization never drops a
text line, reorders a step, or edits a number, so invariants 1 to 5, 7, and 8
of ADR-107 section 5 stay in the compared text: ordered steps, completion
criteria, evidence requirements, failure states, approval gates, idempotence and
rollback statements, and the exit-code contract. Invariants 1 to 5 and 7 are
prose. The gate checks that the prose is equal, not what it means.

Invariant 6, authorization and the abstract capability set, lives in the tool
lists, and only the platform spelling of a tool is excused. The gate reduces
each list to abstract capabilities with `build/scripts/agent_capabilities.py`
and compares those units:

| Pair | Template list | Shared-source list | Units |
|------|---------------|--------------------|-------|
| `claude-shared` | `tools` | `tools_copilot` | `capability:*` |
| `copilot-shared` | `tools_copilot` | `tools_copilot` | `capability:*` |
| `copilot-shared` | `tools_vscode` | `tools_vscode` | `capability-vscode:*` |

- Spellings that name one capability are equal: `Read` and `read`, `Grep` and
  `search`, `Bash` and `shell` and `execute`, `WebFetch` and `web`,
  `mcp__github__issue_read` and `github/issue_read`. The mapping table is
  `_BUILTIN` in that module.
- `$toolset:<name>` references expand through `templates/toolsets.yaml`, the
  platform variant first, as the generator does. An unknown toolset is a
  configuration error (exit 2).
- Units are one `declaration` unit (`restricted` or `unrestricted`), then one
  unit per family: `builtin`, `mcp:<server>`, and `unmapped`. A member with no
  tool list is `unrestricted`, because Claude Code gives such an agent every
  tool. Restricted against unrestricted is one divergence, the declaration.
- A name the module does not know stays a literal `unmapped` item. A wildcard
  such as `serena/*` is not an explicit `serena/<tool>` list. Neither can hide
  a difference.
- The Claude-only "Claude Code Tools" body section stays out of the comparison.

Divergence that predates the gate is pinned in
`.agents/governance/agent-source-divergence.json`. Each entry holds a digest of
both normalized sides. The gate fails when a pinned unit changes on either
side (re-record after review), when a pinned unit now agrees (delete the pin),
and when the file grows past `BASELINE_CEILING`. Regenerate with
`uv run python build/scripts/check_agent_source_parity.py --write-baseline` and
review the diff. To remove a pin, make the two sources agree, then re-run
`--write-baseline` (or delete the entry by hand). Agreement alone leaves a
`PIN-STALE` finding.

## Regenerating

`build/scripts/build_all.py` orchestrates the generators (skills, agents,
rules, hooks):

```bash
# Regenerate everything from canonical sources.
uv run python build/scripts/build_all.py

# Verify generated trees match sources without writing (CI drift gate).
uv run python build/scripts/build_all.py --check

# Surface parity only (same checks that build_all.py --check also runs).
uv run python build/scripts/check_surface_parity.py

# Agents only (also runnable standalone).
uv run python build/generate_agents.py

# PR-quality CI prompts only.
python3 build/scripts/generate_pr_quality_prompts.py

# Check template-owned SKILL.md files against templates/skills/ without
# writing (ADR-108). The Skill Template Drift pre-PR gate runs this.
uv run python build/scripts/generate_skills.py --validate
```

After editing a source listed above, run the matching regen command and commit
the regenerated output in the same PR. A plugin source change requires no
`plugin.json` edit: the manifests carry no `version` field, and adding one back
fails `build/scripts/validate_plugin_version_bump.py` (ADR-092, Issue #4080).

The Copilot hook generator retains per-matcher shim wrappers, then emits one
dispatcher registration per event when the platform enables dispatcher mode.
`build/scripts/generate_hooks_events.py` owns publication and cleanup:
dispatcher artifacts, stale generated matcher shims, and ownership-proven
orphan-event files are changed through `HookGenerationTransaction`. Unknown,
unsafe, and NO-REGEN files are preserved. Only empty orphan directories are
removed after the transaction commits.

## References

- ADR-002: agent model selection and platform emission.
- ADR-108: template-owned skill files under `.claude/skills/`; amends
  REQ-003-010 and ADR-107 property 1 for exactly that class.
- `templates/README.md`: template structure.
- `build/scripts/validate_install_parity.py`: hand-maintained sibling guard.
- `build/scripts/check_agent_source_parity.py`: agent source equivalence gate (issue #5688).
- `scripts/validation/check_equivalence_predicates.py`: predicate table gate (ADR-107 M1, issue #5686).
- `.claude/rules/canonical-source-mirror.md`: claims of parity must cite and
  quote the canonical source.
- Issue #1921: this inventory.
