## Constraints

- Order: agents, agent-catalog, adr-index, skills, rules, lib, hooks, then binplace (`GENERATORS`); `lib` before `hooks`.
- Binplace follows every generator, copying each plugin tree onto its install tree (`.github/hooks/` from `src/copilot-cli/hooks/`); sole writer of `.claude/agents/`, `.claude/rules/`, `.claude/hooks/`, `.claude/lib/<pkg>/`, `.claude/lib/bootstrap.py`, `.claude/skills/<name>/SKILL.md`, `.claude/skills/review/scripts/validate_review_marker.py`, `.github/hooks/`. `.claude/settings.json` renders from `templates/hooks/settings.tmpl`, no plugin hop.
- Mirrors read `src/claude/` for rules, hooks and `SKILL.md`; lib renders from `scripts/` into both plugin trees; skill support files mirror from `.claude/skills/<name>/` into `src/claude/skills/` (`generate_skills.sync_claude_plugin_skill_support`, skills step).
- A literal `{{` in a rule template is written `\{{`.
- pre_pr rows: `Orphaned Build Deferrals`, `Generated Artifact Staleness`, four `<class> Template Drift` rows (Skill, Agent, Rule, Hook), `Agent Catalog Drift`, `Agent Drift Detection`, `Agent Content Parity (.claude/agents vs src/claude)`.
- `check_plugin_manifest_parity.py` fails a component count in any manifest description; CI only, no local pre_pr row.
- `detect_agent_drift.py` compares rendered trees only: `src/claude/agents` vs `src/vs-code-agents` blocks (`merge-resolver` advisory), `.claude/agents` vs `.github/agents` only under `--fail-on-install-drift`; similarity covers only the 23 `SECTIONS_TO_COMPARE` names, a missing H2 blocks regardless.
