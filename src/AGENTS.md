# src/

Two of this repo's three plugin sources plus a Copilot bundle-target prototype; consumed by Claude Code and Copilot CLI plugin installs, and separately by the `packages/ai-agents-cli` npm CLI.

## Matters

- Two of the three plugin roots in this repo live here: `claude/` ships as the `claude-agents` plugin, `copilot-cli/` ships as the `project-toolkit` plugin for Copilot CLI (`.claude/` is the third, outside `src/`). See `.claude/rules/plugin-self-containment.md`.
- `copilot-cli/**` is entirely generated: it mirrors `.claude/{skills,hooks,lib,rules}` plus `templates/agents/*.shared.md`, via the seven generators `build/scripts/build_all.py` runs. Never hand-edit it.
- `vs-code-agents/*.agent.md` is generated from `templates/agents/*.shared.md` only; it has no `.claude/` counterpart.
- `claude/*.md` is hand-maintained, not generated; its own rules live in `src/claude/AGENTS.md`.
- The root-level `*.ts` files (`agent-registry-schema.ts`, `copilot-target-emitter.ts`, `types.ts`, `transforms/command-syntax-translator.ts`) are a Copilot bundle-target prototype. Nothing under `packages/ai-agents-cli/src/` imports them; only `tests/copilot-target-emitter.test.ts` and `tests/command-syntax-translator.test.ts`, one level up from this tree, do.

## Entry points

- `claude/<name>.md`: Claude agent source, edited directly.
- `uv run python build/scripts/build_all.py`: orchestrates every generator that writes into `copilot-cli/`.
- `uv run python build/generate_agents.py`: writes `copilot-cli/agents/` and `vs-code-agents/` from `templates/agents/`.
- `packages/ai-agents-cli/src/cli.ts`: the actual shipped CLI entry point (separate build, separate tests, not this tree).

## Where to look

| Path | Why |
|---|---|
| `claude/*.md` | Hand-maintained; `claude-agents` plugin source; rules in `src/claude/AGENTS.md` |
| `copilot-cli/**` | Generated mirror of `.claude/{skills,hooks,lib,rules}` and `templates/agents/`; `project-toolkit` plugin for Copilot CLI |
| `vs-code-agents/*.agent.md` | Generated from `templates/agents/` only, no `.claude/` input |
| `STYLE-GUIDE.md` | Prose standard every agent file (hand-maintained and generated) MUST follow |
| `*.ts`, `transforms/` | Copilot bundle-target prototype; tests live in repo-root `tests/*.test.ts` |
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

- Assuming the root `*.ts` files here feed `packages/ai-agents-cli`'s build is wrong; that package carries its own `types.ts`, `target/*.ts`, and `io/*.ts` under `packages/ai-agents-cli/src/`, with no import from this tree.
- Assuming repo-root `tests/*.test.ts` run in CI is wrong: `cli-smoke.yml`'s only `bun test` step sets `working-directory: packages/ai-agents-cli`, so the tests for this tree's `*.ts` files are not executed by any workflow today.
- A green `build_all.py --check` proves `copilot-cli/` and `vs-code-agents/` match their sources; it says nothing about whether hand-maintained `claude/` agrees with `templates/agents/` (see `src/claude/AGENTS.md` Dangerous assumptions).

## Dependencies

- `build/scripts/build_all.py` generators feeding this tree: `agents`, `skills`, `rules`, `lib`, `hooks` (agent-catalog and adr-index write elsewhere); each generator's source and output is listed in `.agents/governance/GENERATOR-FILES.md`.
- CI: `validate-generated-agents.yml` (agents), `validate-plugin-version-bump.yml` (`.claude/**`, `claude/**`, `copilot-cli/**`), `cli-smoke.yml` / `nightly-cli-smoke.yml` (`packages/ai-agents-cli` install smoke and unit tests).
- `packages/ai-agents-cli` publishes via `publish.yml`; it vendors a bundled copy of `.claude/`-style content into consumer repos, not anything under this tree.

## Architecture

- Three plugin roots ship independently (`.claude/`, `src/claude/`, `src/copilot-cli/`); each marketplace entry names exactly one source directory, and nothing above it reaches an installer.
- `copilot-cli/` is a double mirror for `lib` and `rules`: `scripts/sync_plugin_lib.py` must run before `build_all.py` to refresh `.claude/lib/` first, or `build_all.py` copies a stale `.claude/lib/` forward with no error; only `scripts/ci/check_plugin_lib_mirrors.py`, in CI, catches the stale mirror.
- The root-level `*.ts` files and `packages/ai-agents-cli/src/*.ts` are two independent TypeScript sources for a similar purpose (bundle emission toward a Copilot target), with no shared import between them.

## Commands

```bash
uv run python build/scripts/build_all.py                    # regenerate all generated trees
uv run python build/scripts/build_all.py --check             # CI drift gate, no write
uv run python build/generate_agents.py --validate             # agents-only regenerate + diff
cd packages/ai-agents-cli && bun install --frozen-lockfile && bun run typecheck && bun test
```
