# build/

Generators plus drift and parity gates. Python only; invoke with `uv run python`.
Tests: `tests/build_scripts/`, `tests/test_generate_agents*.py`, `tests/test_detect_agent_drift.py`.
Rules firing here: `generated-artifacts.md`, `ci-scripts.md`, `canonical-source-mirror.md`.
Source and output inventory: `.agents/governance/GENERATOR-FILES.md`.

## Entry points

| Script | Source -> output | Notes |
|---|---|---|
| `scripts/build_all.py` | Runs `GENERATORS` in order: agents, agent-catalog, adr-index, skills, rules, lib, hooks | `--check` is the drift gate (CI, `pre_pr.py`). `--platform`, `--clean`. Asserts no writes under `.claude/` (REQ-003-010) |
| `generate_agents.py` | `templates/agents/*.shared.md` + `templates/platforms/*.yaml` + `templates/toolsets.yaml` -> `src/copilot-cli/agents/`, `src/vs-code-agents/` | `--validate` (CI), `--what-if` (dry run). Exit 0 ok, 1 mismatch |
| `generate_agent_catalog.py` | templates -> `docs/agent-catalog.md` | Pre-commit `generate-agents` job |
| `scripts/generate_rules.py` | `.claude/rules/*.md` -> `.github/instructions/`, `src/copilot-cli/instructions/` | Drops `priority:` from frontmatter |
| `scripts/generate_skills.py` | `.claude/skills/<n>/` -> `src/copilot-cli/skills/<n>/` | `copilot_body_translation.py` rewrites Claude syntax |
| `scripts/generate_hooks*.py`, `scripts/generate_dispatcher.py` | `.claude/hooks/` + `.claude/settings.json` -> `src/copilot-cli/hooks/` | Transactional (`generate_hooks_transaction.py`); dispatcher mode per platform yaml (ADR-068) |
| `scripts/generate_pr_quality_prompts.py` | `.claude/skills/review/references/<role>.md` -> `.github/prompts/pr-quality-gate-<role>.md` | Pre-push runs `--dry-run` |
| `scripts/generate_adr_index.py` | ADR frontmatter -> `.agents/architecture/README.md` | Deterministic; no timestamps |
| `scripts/regen_guard.py` | NO-REGEN sentinel detection | Files carrying the sentinel are preserved |

## Gates

| Script | Checks | Notes |
|---|---|---|
| `scripts/detect_agent_drift.py` | Similarity `src/claude` vs `src/vs-code-agents` (blocking), `.claude/agents` vs `.github/agents` (advisory) | 80% default. Exit 0 / 1 drift / 2 missing path. Does NOT read templates. `--fail-on-install-drift`, `--skip-install-comparison`, `--similarity-threshold`, `--output-format` (json, markdown) |
| `scripts/validate_install_parity.py` | Template + `.claude/agents` + `.github/agents` + `src/claude` moved together in the diff | Co-change only, not content. `AGENTS.md`, `CLAUDE.md` excluded |
| `scripts/check_agent_content_parity.py` | `.claude/agents/` matches `src/claude/` | Content gate |
| `scripts/validate_plugin_version_bump.py` | No `version` key in any `.claude-plugin/plugin.json` | ADR-092 |
| `scripts/validate_plugin_manifests.py`, `scripts/check_plugin_manifest_parity.py` | Manifest schema; manifests vs marketplace listing | |
| `scripts/validate_templates_schema.py` | `templates/platforms/*.yaml` schema (REQ-003-002) | |
| `scripts/validate_agent_matrix_refs.py` | Capability matrices name real agents | |
| `scripts/validate_planning_artifacts.py` | `.agents/planning/*.md` estimate divergence, orphan conditions, task coverage | `--feature-name`, `--fail-on-error`, `--fail-on-warning` |
| `scripts/validate_path_normalization.py` | No absolute home or drive paths in `**/*.md` | `--fail-on-violation` |
| `model_pin_manifest.py`, `model_pin_sweep_evidence.py` | ADR-080 pin sidecar | Only `haiku` or an evidenced `KEEP_PIN` yields `model:` in generated agents |
| `sync_slim_agents.py` | Propagates a slimmed `src/claude/` body to sibling copies | Hand-copy helper, not a generator |

## Rules

- Source change -> regen -> commit source and output in the same PR. Red `--check` means regen, never hand-edit output.
- Deferral in `build_all.py` must cite an OPEN issue; `scripts/validation/validate_no_orphaned_build_deferrals.py` fails on a closed one. Zero deferrals today.
- Sync before build: `uv run python scripts/sync_plugin_lib.py` (`scripts/{hook_utilities,github_core,ai_review_common}` -> `.claude/lib/`) BEFORE `build_all.py` (`.claude/lib/` -> `src/copilot-cli/lib/`). Reversed order exits 0 and ships a stale mirror; only `scripts/ci/check_plugin_lib_mirrors.py` in CI catches it.
- A generated artifact ships only with a runtime-contract test executed in its target harness.
