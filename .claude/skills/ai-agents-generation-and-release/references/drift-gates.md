<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: .project-toolkit/retrospective/2025-12-15-drift-detection-disaster.md -->

# Drift gates

Detail behind Phase 3. `generator_inventory.py gates` prints, for each gate below, the workflow job or lefthook job that runs it, and exits 1 when a gate has no wiring.

| Gate | Catches |
|------|---------|
| agent-template-drift | templates edited without regen, or the reverse |
| build-all-staleness | any canonical edit not mirrored to owned prefixes, lib trees included |
| lib-mirror-drift | `scripts/` package edited without regen |
| install-parity | plugin install layout broken |
| manifest-description-parity | plugin descriptions carry component counts that drifted |
| plugin-version-field | a manifest or marketplace entry carries `version` |
| semantic-agent-drift | hand-synced agent copies diverging in meaning |

The `gates` output also carries each gate's local command (field `local`). Notes the script cannot carry:

- `build_all.py --check` has no lefthook job. Only a comment at `lefthook.yml` names it. CI runs it as job `build-all-staleness` in `validate-generated-agents.yml`, so a local run before push is the only early signal. Run it.
- `detect_agent_drift.py` runs on a weekly cron (Monday 09:00 UTC) and by manual dispatch in `drift-detection.yml`. It is not a PR gate. Similarity threshold default is 80 (`default=80`), with a recorded baseline floor so a clean checkout does not fail. A green run does not prove two agent copies agree; see the `detect_agent_drift.py` scope notes in `claude-agents.md`.
- The version-field gate retired the version-parity half with ADR-092. Parity now checks description component counts only.

## Which side is canonical

A red gate shows the difference, not the direction. Ask which side is canonical before touching anything. The 2025-12-15 incident (`.project-toolkit/retrospective/2025-12-15-drift-detection-disaster.md`) happened because an agent edited the source to match the generated tree. The commit was reverted. The fix is always: edit canonical, rerun the generator, commit both.

An emergency bypass marker for the drift gate exists but needs a reason and approval. See `ai-agents-config-catalog`, and route the decision through `ai-agents-change-control`.

## Installed Copilot hook E2E

Run it in an isolated home. This executes the marketplace layout and generated hook scripts without changing live plugin state:

```bash
E2E_HOME="$(mktemp -d)"
HOME="$E2E_HOME" COPILOT_HOME="$E2E_HOME/.copilot" \
  copilot plugin marketplace add "$PWD"
HOME="$E2E_HOME" COPILOT_HOME="$E2E_HOME/.copilot" \
  copilot plugin install project-toolkit@ai-agents
HOME="$E2E_HOME" COPILOT_HOME="$E2E_HOME/.copilot" \
  RUN_INSTALLED_PLUGIN_HOOK_E2E=1 uv run pytest \
  tests/e2e/test_installed_plugin_hook_e2e.py -q
```

Do not run this setup in the live Copilot home. Copilot CLI 1.0.72-1 was observed removing the marketplace registration for `copilot plugin uninstall project-toolkit` while leaving the `_direct/project-toolkit` cache. The active session then lost its hook scripts and denied matching tools until the marketplace plugin was reinstalled.
