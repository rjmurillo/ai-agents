## Constraints

- Order: agents, agent-catalog, adr-index, skills, rules, lib, hooks, then binplace (`GENERATORS`); `lib` before `hooks`.
- Binplace follows every generator, copying each plugin tree onto its install tree (`.github/hooks/` from `src/copilot-cli/hooks/`, except the hand-authored `.github/hooks/memory-recall.json`, which binplace leaves alone); `link: true` rows place symlinks instead (`binplace_links.py`, ADR-119), so linked trees are not owned. Sole writer of `.claude/agents/`, `.claude/skills/<name>` and shipped `.claude/rules/` links, `.claude/hooks/`, the `.claude/lib/` links (`lib` row; the hand-maintained modules stay real), `.github/agents/`, and `.github/hooks/` links. `.claude/settings.json` renders from `templates/hooks/settings.tmpl`, no plugin hop.
- Mirrors read `src/claude/` rules, hooks, skills; lib renders from `scripts/` into both plugin trees; skill support files are hand-maintained in `src/claude/skills/<name>/` (ADR-119).
- A literal `{{` in a rule template is written `\{{`.
- pre_pr rows: `Orphaned Build Deferrals`, `Generated Artifact Staleness`, four `<class> Template Drift` rows (Skill, Agent, Rule, Hook), `Agent Catalog Drift`, `Agent Drift Detection`, `Agent Content Parity (.claude/agents vs src/claude)`.
- `check_plugin_manifest_parity.py` fails a component count in any manifest description; CI only, no local pre_pr row.
- `detect_agent_drift.py` compares rendered trees only: `src/claude/agents` vs `src/vs-code-agents` blocks (`merge-resolver` advisory), `.claude/agents` vs `.github/agents` only under `--fail-on-install-drift`; similarity covers only the 23 `SECTIONS_TO_COMPARE` names, a missing H2 blocks regardless.
