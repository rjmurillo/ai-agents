# templates/

Source of truth for Copilot CLI, VS Code, and Visual Studio agent mirrors only; read by `build/generate_agents.py` and by contributors changing shared agent behavior.

## Matters

- 31 `agents/*.shared.md` files are the whole input. `build/generate_agents.py` writes ONLY `src/copilot-cli/agents/` and `src/vs-code-agents/`.
- `src/claude/`, `.claude/agents/`, and `.github/agents/` are hand-maintained copies of the same agents. No generator writes them; a shared-behavior edit needs a matching hand edit there in the same change.
- `description` is required and drives agent routing. `name` is not a template field: it is derived from the filename, and re-added only for a platform whose config sets `includeNameField: true` (copilot-cli).
- `tools` / `tools_vscode` / `tools_copilot` MUST stay block-style YAML lists. Inline arrays (`['a','b']`) break Copilot CLI on CRLF line endings (issue #893).
- A `model:` pin appears in generated output only for the `haiku` tier or a validated ADR-080 `KEEP_PIN` manifest entry; `opus`, `sonnet`, or no `model_tier` all resolve to no pin.
- Regenerating and committing output is not optional: an uncommitted generator run after a template edit is a protocol failure (`.claude/rules/templates.md` MUST-1/2).

## Entry points

- `agents/<name>.shared.md`: edit here to change an agent's shared behavior.
- `platforms/{copilot-cli,vscode,visual-studio}.yaml`: per-platform output config.
- `toolsets.yaml`: named tool groups referenced via `$toolset:<name>`.
- `uv run python build/generate_agents.py`: the only supported way to produce output from a template edit.

## Where to look

| Path | Why |
|---|---|
| `agents/<name>.shared.md` | Platform-agnostic agent body plus frontmatter; the actual source of truth |
| `platforms/copilot-cli.yaml` | Output dir `src/copilot-cli/agents`, `includeNameField: true`, `handoffSyntax: /agent`, `dispatcher: true` for hooks |
| `platforms/vscode.yaml`, `visual-studio.yaml` | Both write `src/vs-code-agents`; `handoffSyntax: #runSubagent`, `includeNameField: false`; Visual Studio sets `toolsFrom: vscode` |
| `toolsets.yaml` | Tool group definitions; adding or removing a tool anywhere MUST update this file too |
| `README.md` | Human guide; states the ADR-036 procedure still runs and ADR-052 is accepted target state, not implemented |
| `.claude/rules/templates.md` | Binding MUST / SHOULD / MUST NOT for this tree |

## Skip

- `src/copilot-cli/agents/`, `src/vs-code-agents/`: generated output, not source. Edit the template and regenerate instead.
- `src/claude/`, `.claude/agents/`, `.github/agents/`: hand-maintained siblings, out of this tree; see `src/claude/AGENTS.md`.

## Constraints

- Cross-harness behavior: read `agent-harness-reference` first; hook, event, or generated-Copilot changes run through `ai-agents-portability-campaign`.
- Regenerate after every edit and commit both generated trees in the same PR (`templates.md` MUST-1/2).
- Adding or removing a tool from any template MUST update `toolsets.yaml` consistently (`templates.md` MUST-3).
- `model_tier` MUST comply with ADR-080; only `haiku` or a fresh manifest `KEEP_PIN` entry resolves to a `model:` pin (`templates.md` MUST-5).
- `platforms/*.yaml` schema is enforced by `build/scripts/validate_templates_schema.py`: `safe_load` only, no YAML anchors or aliases, `schemaVersion` semver check, path traversal rejection.
- Editing a shared agent also means editing `src/claude/<name>.md`, `.claude/agents/<name>.md`, and `.github/agents/<name>.agent.md` in the same change; `build/scripts/validate_install_parity.py` fails the PR when one sibling is missing from the diff.

## Dangerous assumptions

- "Parity gate passed" does not mean the hand-maintained copies agree with the template. `validate_install_parity.py` checks that files changed together in a diff; nothing compares their text.
- "Drift check passed" does not mean a template edit reached `src/claude` or `.claude/agents`. `detect_agent_drift.py` never reads template content, only template filenames (to pick which agents to compare). It scores 23 allowlisted sections (`SECTIONS_TO_COMPARE`). A heading present on only one side always fails, but a section outside that allowlist that exists on both sides is never compared, so its text can diverge freely.
- A `src/claude/`-only edit with no matching template edit is not caught by any gate: the co-change check does not require the template side.

## Dependencies

- Feeds `build/generate_agents.py`, one of the seven generators `build/scripts/build_all.py` runs as its `agents` step.
- CI: `validate-generated-agents.yml` runs `uv run python build/generate_agents.py --validate` (regenerate and diff, no write).
- Weekly `drift-detection.yml` (Mondays 09:00 UTC, plus manual dispatch) runs the drift scorer repo-wide and opens an issue on drift; it is an audit, not a PR merge gate.

## Architecture

- Two independent seams share one source: `build/generate_agents.py` is the generated seam (copilot-cli, vs-code-agents); the hand-maintained mirrors (`src/claude/`, `.claude/agents/`, `.github/agents/`) are a separate, manual seam kept in sync by convention and the co-change check, not by generation.
- `vscode.yaml` and `visual-studio.yaml` both target `src/vs-code-agents`; there is no separate Visual Studio output directory.

## Commands

```bash
uv run python build/generate_agents.py                     # regenerate copilot-cli + vs-code-agents
uv run python build/generate_agents.py --validate           # CI mode: regenerate and diff, no write
uv run python build/generate_agents.py --what-if             # dry run
uv run python build/scripts/validate_templates_schema.py     # schema-check platforms/*.yaml
uv run python build/scripts/detect_agent_drift.py --all      # score src/claude vs src/vs-code-agents (80% floor)
uv run python build/scripts/validate_install_parity.py --files <path>  # check the co-change requirement
```
