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
| `build/scripts/generate_rules.py` | `.claude/rules/*.md` | `.github/instructions/*.instructions.md`, `src/copilot-cli/instructions/*.instructions.md` | REQ-003-006 |
| `build/scripts/generate_skills.py` | `.claude/skills/<name>/` (SKILL.md read from `src/claude/skills/<name>/SKILL.md` when that skill has a template) | `src/copilot-cli/skills/<name>/` (except `review/scripts/validate_review_marker.py`, rendered from `scripts/validation/` by `lib_mirror.py`) | REQ-003-001 |
| `build/scripts/skill_templates.py` | `templates/skills/<name>.SKILL.md.tmpl` + `templates/skills/partials/*.mustache` | `src/claude/skills/<name>/SKILL.md` and through the binplace step to `.claude/skills/<name>/SKILL.md`, template-owned skills only | ADR-108, ADR-109 |
| `build/scripts/generate_skills.py` (`sync_claude_plugin_skill_support`) | `.claude/skills/<name>/` (every file except SKILL.md and the review sidecar validator; merge-resolver included, unlike the Copilot mirror row above) | `src/claude/skills/<name>/` (SKILL.md itself is never touched here; that is `skill_templates.py`'s target; `review/scripts/validate_review_marker.py` is skipped, rendered from `scripts/validation/` by `lib_mirror.py`) | ADR-109 B3 follow-up |
| `build/scripts/agent_templates.py` | `templates/agents/<stem>.claude.md.tmpl`, `<stem>.copilot.md.tmpl`, `templates/agents/partials/*.mustache` | `src/claude/agents/<stem>.md` and through `build/generate_agents.py` to `src/copilot-cli/agents/<stem>.agent.md` | ADR-109 |
| `build/scripts/rule_templates.py` | `templates/rules/<name>.md` (every rule; a literal `{{` in a rule is written `\{{`) | `src/claude/rules/<name>.md` and through the binplace step to `.claude/rules/<name>.md` | ADR-109 |
| `build/scripts/binplace_manifest.py` | `templates/platforms/binplace.yaml` plus the plugin trees it names | `.claude/agents/`, `.claude/rules/`, `.claude/skills/<name>/SKILL.md`, `.claude/hooks/` (plus `.claude/hooks/hooks.json`), `.github/hooks/*.json` | ADR-109 |
| `build/generate_agents.py` (`github` platform, `templates/platforms/github.yaml`) | `templates/agents/<stem>.copilot.md.tmpl` via `agent_templates.py` | `.github/agents/*.agent.md` (no `model:` field; GitHub rejects it, issue #4938) | ADR-109 |
| `build/scripts/hook_templates.py` | `templates/hooks/` (14 executables, `dispatch_groups.json`, `hooks.json`) plus `templates/hooks/settings.tmpl` | `src/claude/hooks/<rel>`, `src/claude/hooks.json` (plugin root, not nested), and directly `.claude/settings.json` (no plugin-tree hop) | ADR-109 |
| `build/scripts/generate_hooks.py` with `build/scripts/generate_dispatcher.py` | `src/claude/hooks/` + `src/claude/hooks.json` (repointed from `.claude/hooks/` by ADR-109 B4; `hook_templates.compile_all` runs first) | `src/copilot-cli/hooks/` + `src/copilot-cli/hooks/hooks.json`, and through the binplace step to `.github/hooks/*.json` (first binplaced in B4) | REQ-003-007, ADR-068, ADR-109 |
| `build/scripts/build_all.py` (`_build_lib`, via `build/scripts/lib_mirror.py`) | `scripts/{hook_utilities,github_core,ai_review_common}/`, `scripts/hook_utilities/bootstrap.py`, `scripts/validation/validate_review_marker.py` | `src/claude/lib/`, `src/copilot-cli/lib/`, `src/claude/skills/review/scripts/`, `src/copilot-cli/skills/review/scripts/` (then binplaced onto `.claude/lib/` and `.claude/skills/review/scripts/` per `templates/platforms/binplace.yaml`'s `lib-*` and `skills-sidecar` rows; the `skills-sidecar-copilot` row has no install tree) | REQ-003-001, REQ-003-002, ADR-109 B5 |
| `build/scripts/generate_pr_quality_prompts.py` | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | REQ-008-01 |

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
- `.claude/rules/canonical-source-mirror.md`: claims of parity must cite and
  quote the canonical source.
- Issue #1921: this inventory.
