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
| `build/scripts/generate_skills.py` | `.claude/skills/<name>/` | `src/copilot-cli/skills/<name>/` | REQ-003-001 |
| `build/scripts/generate_skills.py` (compile step, `build/scripts/skill_templates.py`) | `templates/skills/<name>.SKILL.md.tmpl` + `templates/skills/partials/*.mustache` | `.claude/skills/<name>/SKILL.md`, template-owned skills only | ADR-108 |
| `build/scripts/agent_templates.py` | `templates/agents/<stem>.claude.md.tmpl`, `<stem>.copilot.md.tmpl`, `templates/agents/partials/*.mustache` | `src/claude/agents/<stem>.md` and through `build/generate_agents.py` to `src/copilot-cli/agents/<stem>.agent.md` | ADR-109 |
| `build/scripts/rule_templates.py` | `templates/rules/<name>.md` (every rule; a literal `{{` in a rule is written `\{{`) | `src/claude/rules/<name>.md` and through the binplace step to `.claude/rules/<name>.md` | ADR-109 |
| `build/scripts/binplace_manifest.py` | `templates/platforms/binplace.yaml` plus the plugin trees it names | `.claude/agents/`, `.claude/rules/`, `.claude/hooks/` (plus `.claude/hooks/hooks.json`), `.github/hooks/*.json` | ADR-109 |
| `build/generate_agents.py` (`github` platform, `templates/platforms/github.yaml`) | `templates/agents/<stem>.copilot.md.tmpl` via `agent_templates.py` | `.github/agents/*.agent.md` (no `model:` field; GitHub rejects it, issue #4938) | ADR-109 |
| `build/scripts/hook_templates.py` | `templates/hooks/` (13 executables, `dispatch_groups.json`, `PreToolUse/markdownlint-safe-config.yaml`, `hooks.json`) plus `templates/hooks/settings.tmpl` | `src/claude/hooks/<rel>`, `src/claude/hooks.json` (plugin root, not nested), and directly `.claude/settings.json` (no plugin-tree hop) | ADR-109 |
| `build/scripts/generate_hooks.py` with `build/scripts/generate_dispatcher.py` | `src/claude/hooks/` + `src/claude/hooks.json` (repointed from `.claude/hooks/` by ADR-109 B4; `hook_templates.compile_all` runs first) | `src/copilot-cli/hooks/` + `src/copilot-cli/hooks/hooks.json`, and through the binplace step to `.github/hooks/*.json` (first binplaced in B4) | REQ-003-007, ADR-068, ADR-109 |
| `build/scripts/build_all.py` (`_build_lib`) | `.claude/lib/` | `src/copilot-cli/lib/` | REQ-003-001, REQ-003-002 |
| `build/scripts/generate_pr_quality_prompts.py` | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | REQ-008-01 |

## Hand-maintained sibling copies (NOT generated)

These trees are NOT written by any generator. REQ-003-010 forbids generators from
writing under `.claude/`, except the template-owned skill files ADR-108 enumerates
(two rows above), agent files ADR-109 B1 enumerates (agent_templates.py and
binplace_manifest.py), rule files ADR-109 B2 enumerates (rule_templates.py and
binplace_manifest.py), and hooks-and-settings files ADR-109 B4 enumerates
(hook_templates.py and binplace_manifest.py): a `.claude/skills/<name>/SKILL.md`,
`.claude/agents/<name>.md`, `.claude/rules/<name>.md`, a file under
`.claude/hooks/` (13 executables, `hooks.json`, `dispatch_groups.json`,
`PreToolUse/markdownlint-safe-config.yaml`), or `.claude/settings.json` whose
source template exists at run time is generated output, not hand-maintained,
and the exceptions are scoped to exactly those sets. The seven doc files
under `.claude/hooks/` (`AGENTS.md`, five `CLAUDE.md` files, one `README.md`)
are outside the hooks class and stay hand-maintained.
Every other file below is kept in sync by hand and guarded by the install-parity
validator, which fails CI when a sibling drifts from its source.

| Path | Role | Guard |
|------|------|-------|

ADR-109 B1 moved `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md`, and `src/claude/<name>.md` into generated output via the agent_templates.py and binplace_manifest.py generators above. ADR-109 B2 moved every `.claude/rules/<name>.md` file (28) the same way via rule_templates.py; `testing.md` is template-owned too, its GitHub Actions example written with the `\{{` escape. ADR-109 B4 moved the 16-file hooks class (13 executables, `hooks.json`, `dispatch_groups.json`, `PreToolUse/markdownlint-safe-config.yaml`) plus `.claude/settings.json` into generated output via hook_templates.py: `src/claude/hooks/` and `src/claude/hooks.json` render for the first time, `.github/hooks/*.json` is binplaced for the first time, and `.claude/settings.json` renders directly from `templates/hooks/settings.tmpl` with no plugin-tree hop, since it ships in no plugin.

## Regenerating

`build/scripts/build_all.py` orchestrates the generators (skills, agents,
rules, hooks):

```bash
# Regenerate everything from canonical sources.
uv run python build/scripts/build_all.py

# Verify generated trees match sources without writing (CI drift gate).
uv run python build/scripts/build_all.py --check

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
- `.claude/rules/canonical-source-mirror.md`: claims of parity must cite and
  quote the canonical source.
- Issue #1921: this inventory.
