# templates/

Source of truth for Copilot CLI and VS Code agents only. `agents/*.shared.md` (31) ->
`uv run python build/generate_agents.py` -> `src/copilot-cli/agents/`, `src/vs-code-agents/`.
Claude agents (`src/claude/`, `.claude/agents/`) and `.github/agents/` are hand-maintained; the
generator never writes them. Rule: `.claude/rules/templates.md`. Human guide: `templates/README.md`.

| File | Role |
|---|---|
| `agents/<name>.shared.md` | Platform-agnostic agent body + frontmatter |
| `platforms/copilot-cli.yaml`, `vscode.yaml`, `visual-studio.yaml` | Output dir, extension, `includeNameField`, `handoffSyntax` (`/agent` vs `#runSubagent`), `model_tiers`, dispatcher flag. Schema-gated by `build/scripts/validate_templates_schema.py` |
| `toolsets.yaml` | Named tool groups; `$toolset:<name>` expands in `tools*` lists. Adding or removing tools MUST update it |

## Frontmatter

`role`, `description` (required; drives routing), `argument-hint`, `tools` or `tools_vscode` / `tools_copilot`
(block-style YAML lists only; inline arrays break Copilot CLI on CRLF), optional `model_tier`.
No `name` field: derived from filename. `model:` in output appears only for an ADR-080 `KEEP_PIN`
manifest entry or the `haiku` tier; `opus`, `sonnet`, or absent resolve to no pin.

Required sections: Core Identity, Activation Profile, Core Mission, Key Responsibilities,
Constraints, Memory Protocol, Handoff Options.

## Change protocol

1. Shared behavior: edit `agents/<name>.shared.md` AND `src/claude/<name>.md` AND `.claude/agents/<name>.md` AND `.github/agents/<name>.agent.md`. `validate_install_parity.py` fails when one sibling is missing from the diff; nothing checks their text agrees.
2. `uv run python build/generate_agents.py`; inspect both generated copies; commit sources + outputs together.
3. `uv run python build/generate_agents.py --validate` is what CI runs (`validate-generated-agents.yml`).
4. `build/scripts/detect_agent_drift.py` scores `src/claude` vs `src/vs-code-agents` (80%); green is not proof the template edit reached the hand copies.

Before platform-specific behavior: read `agent-harness-reference`; cross-harness changes go through `ai-agents-portability-campaign`.
