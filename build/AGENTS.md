# build/

Generators, mirror-sync helpers, and drift/parity gates for the agent, skill,
rule, and hook pipeline. Consumed by contributors editing a canonical source
(`.claude/`, `templates/`, `src/claude/`) and by CI (`build_all.py --check`,
the parity validators). Python only, invoked with `uv run python`.

## Matters

- `build/scripts/build_all.py --check` is the drift gate every PR must pass. Red means regenerate, never hand-edit the output tree.
- REQ-003-010: no generator may write under `.claude/`. `build_all.py` asserts this after every run by snapshotting `.claude/` before and diffing after.
- Three trees are hand-maintained siblings, not generator output: `src/claude/<name>.md`, `.claude/agents/<name>.md`, `.github/agents/<name>.agent.md`. Editing one means editing all three plus `templates/agents/<name>.shared.md`; nothing regenerates them for you.
- `scripts/sync_plugin_lib.py` (top-level `scripts/`, not `build/`) MUST run before `build/scripts/build_all.py`. Reversed order exits 0 on both and ships a stale `src/copilot-cli/lib/`; only `scripts/ci/check_plugin_lib_mirrors.py` in CI catches it.
- No plugin manifest carries a `version` key (ADR-092). A source change needs no manifest bump; adding one back fails `build/scripts/validate_plugin_version_bump.py`.

## Entry points

| Command | Effect |
|---|---|
| `uv run python build/scripts/build_all.py` | Regenerate everything from canonical sources |
| `uv run python build/scripts/build_all.py --check` | CI drift gate; no writes |
| `uv run python build/generate_agents.py` | Agents only, standalone |
| `uv run python build/scripts/detect_agent_drift.py` | Similarity gate, standalone |

## Where to look

| Path | Why |
|---|---|
| `.agents/governance/GENERATOR-FILES.md` | Canonical source-to-output inventory; edit the source it names, never the output |
| `build/scripts/build_all.py` | Orchestrator: `GENERATORS` list, CLI flags, the REQ-003-010 guard |
| `build/generate_agents.py` | Agent template renderer; `--validate`, `--what-if` |
| `build/scripts/detect_agent_drift.py` | Similarity gate; all CLI flags and exit codes |
| `build/scripts/generate_hooks*.py`, `build/scripts/generate_dispatcher.py` | Hook/dispatcher generation, split by concern (body, emit, events, expand, shim, transaction) |
| `build/sync_slim_agents.py`, `build/sync_slim_agents_reconcile.py` | Hand-copy propagation helper for `src/claude/` slimmed bodies; not a generator, not run by `build_all.py` |
| `build/model_pin_manifest.py`, `build/model_pin_sweep_evidence.py` | ADR-080 model-pin sidecar resolution and evidence validation |
| `tests/build_scripts/` | Test suite for `build/scripts/*.py` |
| `tests/test_generate_agents*.py`, `tests/test_detect_agent_drift.py` | Test suite for the two top-level `build/*.py` modules |

## Skip

- `build/__pycache__/` and `build/scripts/__pycache__/`: gitignored bytecode, never a source.
- `build/CLAUDE.md` (one line, `@AGENTS.md`) and `build/scripts/__init__.py` (empty package marker): nothing to read.
- Any file under `src/copilot-cli/`, `.github/instructions/`, `docs/agent-catalog.md`, `.agents/architecture/README.md`: these are generator OUTPUT. Edit the source `GENERATOR-FILES.md` names instead.

## Constraints

- `build_all.py` runs generators in a fixed order (agents, agent-catalog, adr-index, skills, rules, lib, hooks); `lib` MUST land before `hooks` because the hook manifest expects the lib mirror already in place (`build/scripts/build_all.py:491-496`).
- A deferral inside `build_all.py` must cite an OPEN issue; `scripts/validation/validate_no_orphaned_build_deferrals.py` fails on a closed one. Zero deferrals on the tracked tree today.
- `build/scripts/detect_agent_drift.py` does not read `templates/agents/*.shared.md`; it compares only the rendered output trees (`src/claude` vs `src/vs-code-agents`, blocking; `.claude/agents` vs `.github/agents`, advisory unless `--fail-on-install-drift`). A generator bug in template rendering is invisible to it.
- `build/scripts/validate_install_parity.py` checks co-change only (did the sibling paths move together in the diff), not content equality; `AGENTS.md`/`CLAUDE.md` names are excluded from every parity group.
- `build/scripts/check_agent_content_parity.py` is the content gate `validate_install_parity.py` does not provide: byte-for-byte `.claude/agents/` vs `src/claude/`.
- Regenerating with a mismatched sync order (see Matters) is a silent failure: both scripts exit 0.

## Dangerous assumptions

- "The gate script lives next to what it checks" is false for the lib mirror: the source sync (`scripts/sync_plugin_lib.py`) sits outside `build/`, one directory up, and nothing in `build/` calls it.
- "`--check` failing means hand-edit the diff to match" is backwards: `--check` failing means the SOURCE changed and the output is stale. Hand-editing output is overwritten on the next real regen and never reviewed against source intent.
- "`src/claude/` is generated like `src/copilot-cli/agents/`" is false. It is hand-maintained; `GENERATOR-FILES.md` calls this out explicitly because it was misclassified once (Issue #2882).
- "Fixing drift means raising the similarity threshold" is a gate defeat, not a fix (mirrors `.claude/rules/ci-scripts.md` MUST NOT 4 on count ratchets); the fix is regenerating or hand-syncing the sibling.

## Dependencies

- Feeds `.claude/skills/review/references/<role>.md` -> `.github/prompts/pr-quality-gate-<role>.md` via `build/scripts/generate_pr_quality_prompts.py`; pre-push runs `--dry-run`, and `build/scripts/run_drift_check_ci.py` wraps the same `--dry-run` for the `validate-generated-agents.yml` workflow step (ADR-006: logic stays in the module, not the YAML).
- Feeds `.github/instructions/` and `src/copilot-cli/instructions/` via `build/scripts/generate_rules.py`, which drops the `priority:` frontmatter key on the way out.
- Two lefthook pre-commit jobs fire on `templates/agents/*.shared.md` / `templates/platforms/**` changes: `generate-agents` (regenerates agent output) and the separately named `generate-agent-catalog` (runs `build/generate_agent_catalog.py` directly).
- Consumed by `scripts/validation/pre_pr.py`, the canonical pre-PR runner, which chains the drift and parity gates in this tree.

## Architecture

- Plugin lib is a two-hop mirror chain, not a single copy: `scripts/{hook_utilities,github_core,ai_review_common}` -> (`scripts/sync_plugin_lib.py`) -> `.claude/lib/` -> (`build/scripts/build_all.py`, `_build_lib`) -> `src/copilot-cli/lib/`. Neither script calls the other.
- Hook generation retains per-matcher shim wrappers, then additionally emits one dispatcher registration per event when the target platform config enables dispatcher mode (ADR-068). Publication and cleanup of dispatcher artifacts, stale shims, and orphaned event files run through `HookGenerationTransaction`; files carrying a `NO-REGEN` sentinel (`build/scripts/regen_guard.py`) are preserved untouched.

## Commands

```bash
# Regenerate everything from canonical sources.
uv run python build/scripts/build_all.py
# CI drift gate: verify generated trees match sources, no writes.
uv run python build/scripts/build_all.py --check
# Agents only, standalone (also supports --validate, --what-if).
uv run python build/generate_agents.py
# Sync the plugin lib mirror BEFORE build_all.py touches lib/hooks.
uv run python scripts/sync_plugin_lib.py
# Drift similarity gate, standalone.
uv run python build/scripts/detect_agent_drift.py
# PR-quality prompt drift check (what pre-push runs).
uv run python build/scripts/generate_pr_quality_prompts.py --dry-run
# Full pre-PR gate chain (run before every push).
uv run python scripts/validation/pre_pr.py
```
