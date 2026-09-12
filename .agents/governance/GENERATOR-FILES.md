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
| `build/scripts/binplace_manifest.py` | `templates/platforms/binplace.yaml` plus the plugin trees it names | `.claude/agents/` | ADR-109 |
| `build/generate_agents.py` (`github` platform, `templates/platforms/github.yaml`) | `templates/agents/<stem>.copilot.md.tmpl` via `agent_templates.py` | `.github/agents/*.agent.md` (no `model:` field; GitHub rejects it, issue #4938) | ADR-109 |
| `build/scripts/generate_hooks.py` with `build/scripts/generate_dispatcher.py` | `.claude/hooks/` + `.claude/settings.json` | `src/copilot-cli/hooks/` + `src/copilot-cli/hooks/hooks.json` | REQ-003-007, ADR-068 |
| `build/scripts/build_all.py` (`_build_lib`) | `.claude/lib/` | `src/copilot-cli/lib/` | REQ-003-001, REQ-003-002 |
| `build/scripts/generate_pr_quality_prompts.py` | `.claude/skills/review/references/{role}.md` | `.github/prompts/pr-quality-gate-{role}.md` | REQ-008-01 |

## Hand-maintained sibling copies (NOT generated)

These trees are NOT written by any generator. REQ-003-010 forbids generators from
writing under `.claude/`, except the template-owned skill files ADR-108 enumerates
(two rows above) and agent files ADR-109 B1 enumerates (agent_templates.py and
binplace_manifest.py): a `.claude/skills/<name>/SKILL.md` or `.claude/agents/<name>.md`
whose source template exists at run time is generated output, not hand-maintained,
and the exceptions are scoped to exactly those sets. Every other file below is kept
in sync by hand and guarded by the install-parity validator, which fails CI when a
sibling drifts from its source.

| Path | Role | Guard |
|------|------|-------|
| (none currently; ADR-109 B1 retired agent and rule rows) | | |

ADR-109 B1 moved `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md`, and `src/claude/<name>.md` into generated output via the agent_templates.py and binplace_manifest.py generators above.

## Regenerating

`build/scripts/build_all.py` orchestrates the generators (skills, agents,
commands, rules, hooks):

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
