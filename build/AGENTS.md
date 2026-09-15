# build/

Generators and drift/parity gates for the agent/skill/rule/hook pipeline; sources are `templates/`, `.claude/{rules,hooks,skills}/`, `scripts/`, `.agents/architecture/`; `.claude/lib/` is `_build_lib`'s input, canonical for its top-level modules and a sync target for its three packages (Architecture); `.claude/agents/` is pure output, never hand-edited; CI runs `build_all.py --check`.

## Matters

- `build_all.py --check`: drift gate for the `OWNED_PREFIXES` trees (see Skip) plus the ADR-108 `.claude/skills/` compile (`_build_skills` threads `check` as `validate`); `.github/prompts/` has its own (Dependencies).
- `validate_install_parity.py`'s SHARED_AGENT and RULE groups are delegated to `build_all.py --check`, so `find_violations` can return no violation (its own docstring); its pre_pr row is gone, but `validate-generated-agents.yml` still runs it through `scripts/validation/run_install_parity_ci.py`, which can exit 2 on base-ref resolution alone. `check_agent_content_parity.py` is the live byte gate, pre_pr's `Agent Content Parity` row: `.claude/agents/` vs `src/claude/agents/`.
- REQ-003-010: no generator writes under `.claude/` except `binplace_manifest.claude_allowlist()`'s two classes (ADR-108 `SKILL.md`, ADR-109 `.claude/agents/<stem>.md`).
- Agent-tree ownership belongs to `templates/AGENTS.md`; none of the five output trees is hand-maintained (ADR-109 B1).
- `scripts/sync_plugin_lib.py` MUST run before `build_all.py` (Dangerous assumptions).

## Entry points

- `build_all.py` (regenerate/`--check`), `generate_agents.py`, `detect_agent_drift.py`: standalone (Commands).

## Where to look

| Path | Why |
|---|---|
| `.agents/governance/GENERATOR-FILES.md` | Source-to-output map |
| `build/scripts/build_all.py` | `GENERATORS`, flags, REQ-003-010, binplace |
| `build/scripts/agent_templates.py`, `binplace_manifest.py`, `build/generate_agents.py` | The two agent renderers plus the binplace copier; per-tree mapping in `templates/AGENTS.md` |
| `build/scripts/generate_hooks*.py`, `generate_dispatcher.py` | Hook/dispatcher generation, split by concern (body, emit, events, expand, shim, transaction) |
| `tests/build_scripts/`, `tests/test_generate_agents*.py`, `tests/test_detect_agent_drift.py` | Tests for this tree |

## Skip

- `build/__pycache__/`, `build/scripts/__pycache__/`: gitignored bytecode.
- `build/CLAUDE.md` (`@AGENTS.md`), `build/scripts/__init__.py`: nothing to read.
- `src/` (`copilot-cli/`, `claude/agents/`, `vs-code-agents/` only; `src/*.md`, both `.claude-plugin/plugin.json`, `src/copilot-cli/{THIRD-PARTY-NOTICES.TXT,docs/}` and `src/claude/{AGENTS.md,claude-instructions.template.md,security/references/}` are hand-maintained inside the prefix), `.github/instructions/`, `.github/agents/`, `.claude/agents/`, `docs/agent-catalog.md`, `.agents/architecture/README.md` (the literal `OWNED_PREFIXES`): generator OUTPUT.

## Constraints

- Generator order: agents, agent-catalog, adr-index, skills, rules, lib, hooks, binplace; `lib` before `hooks` (`build_all.py:560-564`).
- Binplace (`binplace.yaml`) copies `src/claude/agents` into `.claude/agents/` after every generator; sole writer of that tree.
- `detect_agent_drift.py` compares rendered trees, never template bodies: `src/claude/agents` vs `src/vs-code-agents` blocks except `merge-resolver` (`_ADVISORY_VENDORED_DRIFT`, content drift advisory unless a section is missing); `.claude/agents` vs `.github/agents` content drift is advisory unless `--fail-on-install-drift`, but a missing H2 blocks either way; similarity scores only the 23 H2 names in `SECTIONS_TO_COMPARE`, so content drift inside any other section scores nothing.
- A staleness deferral in `build_all.py` must cite an OPEN issue: pre_pr's `Orphaned Build Deferrals` gate (`scripts/validation/validate_no_orphaned_build_deferrals.py`) fails on a closed one. Zero deferrals today.
- `check_plugin_manifest_parity.py` fails any component count ("31 agents") in a description in `.claude-plugin/marketplace.json` or the three `plugin.json` manifests; CI only (`validate-generated-agents.yml`, `agent-drift-detection.yml`), no local gate.

## Dangerous assumptions

- "Gate script lives next to what it checks" is false for lib: `sync_plugin_lib.py` sits outside `build/`; in the wrong order both scripts exit 0 and ship a stale `src/copilot-cli/lib/`. Order is binding (`.claude/rules/generated-artifacts.md`, "Generator order: sync before build"); catchers are pre_pr's `Generated Artifact Staleness` (`scripts/validation/check_generated_staleness.py`, both `--check`s in order) and CI's `scripts/ci/check_plugin_lib_mirrors.py`.
- "`--check` failing means hand-edit the output" is backwards: the source changed; hand-edits are overwritten next regen. Exit 2 has five producers (docstring) and only staleness is cleared by regenerating.
- Raising `detect_agent_drift.py`'s `--similarity-threshold` (default 80) to clear a red defeats the gate; same shape as `ci-scripts.md` MUST NOT 4 on count baselines.
- `build/sync_slim_agents.py` is not a generator and `build_all.py` never calls it. Its docstring still calls `src/claude/agents/` hand-authored and "never a destination"; ADR-109 B1 made it generated, so `--write` now copies rendered bodies backwards into `templates/agents/*.shared.md` and `.github/agents/` (`DESTINATIONS`, `sync_slim_agents.py:142-155`). Do not run it.

## Dependencies

- Feeds `.github/prompts/pr-quality-gate-<role>.md` from `.claude/skills/review/references/<role>.md` (`generate_pr_quality_prompts.py`; `--dry-run` is the pre-push and CI drift form, wrapped for the workflow by `run_drift_check_ci.py`); `.github/instructions/`, `src/copilot-cli/instructions/` via `generate_rules.py`.
- Lefthook's regen globs (`templates/agents/*.shared.md`, `templates/platforms/**`) fire three pre-commit jobs: `generate-agents` (`scripts/validation/git_hook_policy.py` shells `generate_agents.py`), `generate-agent-catalog` (`generate_agent_catalog.py`), `stage-generated-agents`. A `.claude.md.tmpl`/`.copilot.md.tmpl`/`partials/*.mustache` edit matches none of them, so no auto-regen (ADR-109 B1). Backstops: pre_pr's `Agent Template Drift` (`agent_templates.py --validate`) and `Generated Artifact Staleness` (`build_all.py --check`).

## Architecture

- Plugin lib, two-hop chain: `scripts/{hook_utilities,github_core,ai_review_common}` -> `sync_plugin_lib.py` `SYNC_PAIRS` (rewrites absolute `scripts.X` imports to relative) -> `.claude/lib/` -> `build_all.py`'s `_build_lib` -> `src/copilot-cli/lib/`. `SYNC_FILE_PAIRS` copies `hook_utilities/bootstrap.py` and `scripts/validation/validate_review_marker.py` byte for byte, no rewrite (source MUST be import-self-contained), to `.claude/lib/bootstrap.py` and `.claude/skills/review/scripts/`; the latter reaches `src/copilot-cli/skills/` through the skills generator, not `_build_lib`.
- Hook generation keeps per-matcher shims, emits one dispatcher registration per event when enabled (ADR-068), via `HookGenerationTransaction`; `NO-REGEN` files (`regen_guard.py`) untouched.

## Commands

```bash
# Regenerate everything.
uv run python build/scripts/build_all.py
# CI drift gate, no writes.
uv run python build/scripts/build_all.py --check
# Agents only (also --validate, --what-if).
uv run python build/generate_agents.py
# Before build_all.py touches lib/hooks.
uv run python scripts/sync_plugin_lib.py
# Drift gate, standalone.
uv run python build/scripts/detect_agent_drift.py
# PR-quality prompt drift.
uv run python build/scripts/generate_pr_quality_prompts.py --dry-run
# Pre-PR gate chain.
uv run python scripts/validation/pre_pr.py
```
