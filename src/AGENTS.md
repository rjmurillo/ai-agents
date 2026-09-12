# src/

Two of this repo's three plugin sources; consumed by Claude Code and Copilot CLI plugin installs, and separately by the `packages/ai-agents-cli` npm CLI.

## Matters

- Two of the three plugin roots in this repo live here: `claude/` ships as the `claude-agents` plugin, `copilot-cli/` ships as the `project-toolkit` plugin for Copilot CLI (`.claude/` is the third, outside `src/`). See `.claude/rules/plugin-self-containment.md`.
- `copilot-cli/**` is entirely generated: it mirrors `.claude/{skills,hooks,lib,rules}` plus agents from `templates/agents/`, via generators `build/scripts/build_all.py` runs. Never hand-edit it.
- `vs-code-agents/*.agent.md` is generated from `templates/agents/` only; it has no `.claude/` counterpart.
- `claude/agents/*.md` is generated from `templates/agents/<stem>.claude.md.tmpl` by `build/scripts/agent_templates.py` per ADR-109. `claude-instructions.template.md` is hand-maintained. Rules live in `src/claude/AGENTS.md`.

## Entry points

- `templates/agents/<stem>.claude.md.tmpl`: Edit agent templates here.
- `uv run python build/scripts/build_all.py`: orchestrates every generator that writes into `claude/agents/`, `copilot-cli/`, and other trees.
- `packages/ai-agents-cli/src/cli.ts`: the actual shipped CLI entry point (separate build, separate tests, not this tree).

## Where to look

| Path | Why |
|---|---|
| `claude/agents/*.md` | Generated from `templates/agents/` by `build/scripts/agent_templates.py`; `claude-agents` plugin source; rules in `src/claude/AGENTS.md` |
| `claude/claude-instructions.template.md` | Hand-maintained preamble template |
| `copilot-cli/**` | Generated mirror of `.claude/{skills,hooks,lib,rules}` and `templates/agents/`; `project-toolkit` plugin for Copilot CLI |
| `vs-code-agents/*.agent.md` | Generated from `templates/agents/` only, no `.claude/` input |
| `STYLE-GUIDE.md` | Prose standard every agent file (hand-maintained and generated) MUST follow |
| `packages/ai-agents-cli/` | The shipped `@rjmurillo/ai-agents` npm CLI: its own source, its own tests |

## Skip

- `copilot-cli/**`, `vs-code-agents/*.agent.md`: generated. Edit the upstream source and regenerate (`.agents/governance/GENERATOR-FILES.md`).
- `copilot-cli/docs/copilot-instructions.md`: a byte-budget-ratcheted generated copy; edit the Copilot instructions source, not this file.

## Constraints

- `claude/` and `copilot-cli/` are separate plugin roots: no cross-references between them, and no upstream-only path (`.agents/`, `build/`, `scripts/`) named in either without a `vendor-portability` declaration (`plugin-self-containment.md`).
- Neither plugin's `.claude-plugin/plugin.json` may carry a `version` field; `build/scripts/validate_plugin_version_bump.py` fails if one appears (ADR-092, `plugin-version-bump.md`).
- Regenerate with `uv run python build/scripts/build_all.py`, verify with `--check`, and commit source plus generated output together; never hand-edit a generated tree.
- Cross-harness behavior (hook routing, event handling, generated Copilot agent changes): read `agent-harness-reference` first, then route the change through `ai-agents-portability-campaign`.

## Dangerous assumptions

- A green `build_all.py --check` proves all generated trees match their sources.

## Dependencies

- `build/scripts/build_all.py` generators feeding this tree: `agents`, `skills`, `rules`, `lib`, `hooks` (agent-catalog and adr-index write elsewhere); each generator's source and output is listed in `.agents/governance/GENERATOR-FILES.md`.
- CI: `validate-generated-agents.yml` (agents), `validate-plugin-version-bump.yml` (`.claude/**`, `claude/**`, `copilot-cli/**`), `cli-smoke.yml` / `nightly-cli-smoke.yml` (`packages/ai-agents-cli` install smoke and unit tests).
- `packages/ai-agents-cli` publishes via `publish.yml`; it vendors a bundled copy of `.claude/`-style content into consumer repos, not anything under this tree.

## Architecture

- Three plugin roots ship independently (`.claude/`, `src/claude/`, `src/copilot-cli/`); each marketplace entry names exactly one source directory, and nothing above it reaches an installer.
- `copilot-cli/` is a double mirror for `lib` and `rules`: `scripts/sync_plugin_lib.py` must run before `build_all.py` to refresh `.claude/lib/` first, or `build_all.py` copies a stale `.claude/lib/` forward with no error; only `scripts/ci/check_plugin_lib_mirrors.py`, in CI, catches the stale mirror.

## Commands

```bash
uv run python build/scripts/build_all.py                    # regenerate all generated trees
uv run python build/scripts/build_all.py --check             # CI drift gate, no write
uv run python build/generate_agents.py --validate             # agents-only regenerate + diff
cd packages/ai-agents-cli && bun install --frozen-lockfile && bun run typecheck && bun test
```
