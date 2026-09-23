# build/

Generators and drift gates for the agent/skill/rule/hook/settings pipeline. Sources: `templates/`, `scripts/{hook_utilities,github_core,ai_review_common}`, `.project-toolkit/architecture/`, and `.claude/skills/` files other than `SKILL.md`.

## Matters

- `build_all.py --check`: drift gate over `_effective_owned_prefixes` (`OWNED_PREFIXES` plus each `.claude/skills/<name>/SKILL.md`).
- Per-class render map (agents, rules, skills, hooks, settings, prompts): `templates/AGENTS.md`.
- REQ-003-010: generators write under `.claude/` only via `binplace_manifest.claude_allowlist()`: agents, rules, skill `SKILL.md`, `hooks/` plus `hooks.json`, `settings.json`, `lib/<pkg>/`, `lib/bootstrap.py`, the review sidecar; `NO-REGEN` paths (`regen_guard.py`) excluded.
- `validate_install_parity.py` reports no violation ever; `validate-generated-agents.yml` still runs it (exit 2 on base-ref alone); `check_agent_content_parity.py` is the live byte gate.
- Lib renders inside the same run (`lib_mirror.py`, ADR-109 B5); `scripts/sync_plugin_lib.py` is a deprecated shim, never a prerequisite.

## Entry points

- `build_all.py` (`--check`), `generate_agents.py`, `detect_agent_drift.py`.
- `generate_rules.py`, `generate_hooks.py`, `generate_skills.py`: standalone runs compile templates first, no stale mirror.

## Where to look

| Path | Why |
|---|---|
| `build/scripts/build_all.py` | `GENERATORS`, `OWNED_PREFIXES`, REQ-003-010, binplace |
| `templates/platforms/binplace.yaml` | Per-class plugin tree and install tree |
| `build/scripts/*_templates.py` | One template compiler per class |

## Skip

- Generator OUTPUT (`OWNED_PREFIXES`): `src/`, `.github/instructions/`, `.github/agents/`, `.github/hooks/`, `.claude/agents/`, `.claude/rules/`, `.claude/lib/`, `.claude/hooks/`, `.claude/settings.json`, `docs/agent-catalog.md`, `.project-toolkit/architecture/README.md`. Hand-maintained inside `src/`: `*.md`, `claude/AGENTS.md`, `claude/claude-instructions.template.md`, `claude/security/references/`, `copilot-cli/THIRD-PARTY-NOTICES.TXT`, `copilot-cli/docs/`, both `plugin.json`.

## Constraints

- Order: agents, agent-catalog, adr-index, skills, rules, lib, hooks, then binplace (`GENERATORS`); `lib` before `hooks`.
- Binplace follows every generator, copying each plugin tree onto its install tree (`.github/hooks/` from `src/copilot-cli/hooks/`); sole writer of `.claude/agents/`, `.claude/rules/`, `.claude/hooks/`, `.claude/lib/<pkg>/`, `.claude/lib/bootstrap.py`, `.claude/skills/<name>/SKILL.md`, `.claude/skills/review/scripts/validate_review_marker.py`, `.github/hooks/`. `.claude/settings.json` renders from `templates/hooks/settings.tmpl`, no plugin hop.
- Mirrors read `src/claude/` for rules, hooks and `SKILL.md`; lib renders from `scripts/` into both plugin trees; skill support files mirror from `.claude/skills/<name>/` into `src/claude/skills/` (`generate_skills.sync_claude_plugin_skill_support`, skills step).
- A literal `{{` in a rule template is written `\{{`.
- pre_pr rows: `Orphaned Build Deferrals`, `Generated Artifact Staleness`, four `<class> Template Drift` rows (Skill, Agent, Rule, Hook), `Agent Catalog Drift`, `Agent Drift Detection`, `Agent Content Parity (.claude/agents vs src/claude)`.
- `check_plugin_manifest_parity.py` fails a component count in any manifest description; CI only, no local pre_pr row.
- `detect_agent_drift.py` compares rendered trees only: `src/claude/agents` vs `src/vs-code-agents` blocks (`merge-resolver` advisory), `.claude/agents` vs `.github/agents` only under `--fail-on-install-drift`; similarity covers only the 23 `SECTIONS_TO_COMPARE` names, a missing H2 blocks regardless.

## Dangerous assumptions

- `scripts/sync_plugin_lib.py` looks like a required first step; it is a deprecated shim over `lib_mirror.py`, kept for one `validate-generated-agents.yml` step. `build_all.py` is the whole sequence; there is no order to get wrong.
- A red `--check` means the source changed, not that the output needs a hand-edit; exit 2 has five producers, only staleness clears by regenerating.
- Raising `--similarity-threshold` (default 80) to clear a red defeats the gate.
- `build/sync_slim_agents.py` is not a generator; `build_all.py` never calls it and `--write` copies rendered bodies backwards into `templates/agents/*.shared.md` and `.github/agents/`. Do not run it.

## Dependencies

- `generate_pr_quality_prompts.py`: `.claude/skills/review/references/<role>.md` -> `.github/prompts/pr-quality-gate-<role>.md`; `--dry-run` is the drift form (`run_drift_check_ci.py`); `binplace.yaml`'s `prompts` row only documents it.
- Lefthook regen jobs glob only `templates/agents/*.shared.md` and `templates/platforms/**`; a `.tmpl` or `partials/*.mustache` edit auto-regenerates nothing.

## Architecture

- Lib (B5): `lib_mirror.py` renders `scripts/{hook_utilities,github_core,ai_review_common}`, `hook_utilities/bootstrap.py`, and `validation/validate_review_marker.py` into `src/claude/lib/`, `src/copilot-cli/lib/`, and `src/claude/skills/review/scripts/`; binplace copies the claude side onto `.claude/lib/` and the review sidecar (`lib-*`, `skills-sidecar` rows). `.claude/lib/` top-level modules (`claude_hook_dispatch.py`, `paths.py`, siblings) have no `scripts/` source and stay hand-maintained there (`.claude/AGENTS.md`).

## Commands

```bash
uv run python build/scripts/build_all.py
uv run python build/scripts/build_all.py --check
# Agents only: --validate, --what-if.
uv run python build/generate_agents.py
uv run python build/scripts/detect_agent_drift.py
uv run python build/scripts/generate_pr_quality_prompts.py --dry-run
uv run python scripts/validation/pre_pr.py
```
