# build/

Generators and drift gates for the agent/skill/rule/hook/settings pipeline. Sources: `templates/`, `scripts/{hook_utilities,github_core,ai_review_common}`, `.project-toolkit/architecture/`, and `src/claude/skills/` files other than `SKILL.md`.

## Matters

- `build_all.py --check`: drift gate over `_effective_owned_prefixes` (`OWNED_PREFIXES` plus each repo-local `SKILL.md`, repo-only rule, and real `.github/instructions/` file) and binplace links.
- Per-class render map (agents, rules, skills, hooks, settings, prompts): `templates/AGENTS.md`.
- REQ-003-010: generators write `.claude/` only via `binplace_manifest.claude_allowlist()`: agent and skill links, rules, repo-local `SKILL.md`, `hooks/` plus `hooks.json`, `settings.json`, `lib/<pkg>/`, `lib/bootstrap.py`; `NO-REGEN` paths (`regen_guard.py`) excluded.
- `validate_install_parity.py` reports no violation ever; `validate-generated-agents.yml` still runs it (exit 2 on base-ref alone); `check_agent_content_parity.py` is the live byte gate.
- Lib renders inside the same run (`lib_mirror.py`, ADR-109 B5); `scripts/sync_plugin_lib.py` is retired.

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

- Generator OUTPUT (`OWNED_PREFIXES`): `src/`, `.claude/lib/`, `.claude/hooks/`, `.claude/settings.json`, `docs/agent-catalog.md`, `.project-toolkit/architecture/README.md`. Hand-maintained inside `src/`: `*.md`, `claude/AGENTS.md`, `claude/claude-instructions.template.md`, `claude/security/references/`, `copilot-cli/THIRD-PARTY-NOTICES.TXT`, `copilot-cli/docs/`, both `plugin.json`.

## Constraints

- Order: agents, agent-catalog, adr-index, skills, rules, lib, hooks, then binplace (`GENERATORS`); `lib` before `hooks`.
- Binplace follows every generator, copying each plugin tree onto its install tree (`.github/hooks/` from `src/copilot-cli/hooks/`, except the hand-authored `.github/hooks/memory-recall.json`, which binplace leaves alone); `link: true` rows place symlinks instead (`binplace_links.py`, ADR-119), so linked trees are not owned. Sole writer of `.claude/agents/`, `.claude/skills/<name>` and shipped `.claude/rules/` links, `.claude/hooks/`, `.claude/lib/<pkg>/`, `.claude/lib/bootstrap.py`, `.github/agents/`, and `.github/hooks/` links. `.claude/settings.json` renders from `templates/hooks/settings.tmpl`, no plugin hop.
- Mirrors read `src/claude/` rules, hooks, skills; lib renders from `scripts/` into both plugin trees; skill support files are hand-maintained in `src/claude/skills/<name>/` (ADR-119).
- A literal `{{` in a rule template is written `\{{`.
- pre_pr rows: `Orphaned Build Deferrals`, `Generated Artifact Staleness`, four `<class> Template Drift` rows (Skill, Agent, Rule, Hook), `Agent Catalog Drift`, `Agent Drift Detection`, `Agent Content Parity (.claude/agents vs src/claude)`.
- `check_plugin_manifest_parity.py` fails a component count in any manifest description; CI only, no local pre_pr row.
- `detect_agent_drift.py` compares rendered trees only: `src/claude/agents` vs `src/vs-code-agents` blocks (`merge-resolver` advisory), `.claude/agents` vs `.github/agents` only under `--fail-on-install-drift`; similarity covers only the 23 `SECTIONS_TO_COMPARE` names, a missing H2 blocks regardless.

## Dangerous assumptions

- Older docs mention `scripts/sync_plugin_lib.py` as a first step. It is retired (issue #5790). `build_all.py` is the whole sequence; there is no order to get wrong.
- A red `--check` means the source changed, not that the output needs a hand-edit; exit 2 has five producers, only staleness clears by regenerating.
- Raising `--similarity-threshold` (default 80) to clear a red defeats the gate.
- `build/sync_slim_agents.py` is not a generator; `build_all.py` never calls it and `--write` copies rendered bodies backwards into `templates/agents/*.shared.md` and `src/copilot-cli/agents/`. Do not run it.

## Dependencies

- `generate_pr_quality_prompts.py`: `.claude/skills/review/references/<role>.md` -> `.github/prompts/pr-quality-gate-<role>.md`; `--dry-run` is the drift form (`run_drift_check_ci.py`); `binplace.yaml`'s `prompts` row only documents it.
- Lefthook regen jobs glob only `templates/agents/*.shared.md` and `templates/platforms/**`; a `.tmpl` or `partials/*.mustache` edit auto-regenerates nothing.

## Architecture

- Lib (B5): `lib_mirror.py` renders `scripts/{hook_utilities,github_core,ai_review_common}`, `hook_utilities/bootstrap.py`, and `validation/validate_review_marker.py` (only canonical copy) into `src/{claude,copilot-cli}/lib/` and each tree's `skills/review/scripts/`; binplace copies the claude side onto `.claude/lib/` and the review sidecar (`lib-*`, `skills-sidecar` rows). `build_all.py --check` exits 2 on drift. `.claude/lib/` top-level modules have no `scripts/` source; they stay hand-maintained (`.claude/AGENTS.md`).

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
