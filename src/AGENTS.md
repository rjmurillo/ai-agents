# src/

Two of the repo's three plugin sources; the `packages/ai-agents-cli` npm CLI is a separate tree at the repo root that vendors `.claude/`, nothing from here.

## Matters

- `claude/` ships as `claude-agents` (`.claude-plugin/marketplace.json`); `copilot-cli/` as `project-toolkit` via `.github/plugin/marketplace.json`; `.claude/` is the third root, outside `src/`, and reuses the name `project-toolkit` in the root marketplace.
- ADR-109 B1: all agent output trees here are template-generated, not hand-maintained (`templates/AGENTS.md`).

## Entry points

- Shared agent body: `templates/agents/<stem>.shared.md`: reaches `vs-code-agents/` and `docs/agent-catalog.md`, and is the copilot-cli/github fallback on a standalone `generate_agents.py` run. Its glob is also that generator's stem list: no `.shared.md` means no `copilot-cli/agents/`, `vs-code-agents/`, or `.github/agents/` file for the stem at all.
- Claude/Copilot agent: edit BOTH `<stem>.claude.md.tmpl` AND `<stem>.copilot.md.tmpl`; editing one skips the other's output.

## Where to look

| Path | Why |
|---|---|
| `claude/**` | Generated agents plus hand-maintained refs; see `src/claude/AGENTS.md` |
| `copilot-cli/**` | Generated from `.claude/{skills,hooks,lib,rules}` + `templates/agents/`; rules land in `instructions/` (23), not `rules/`; `THIRD-PARTY-NOTICES.TXT` from `scripts/generate_third_party_notices.py` (`--check` gate, not run by `build_all.py`, absent from `GENERATOR-FILES.md`); hand-maintained: `.claude-plugin/plugin.json`, `docs/` |
| `packages/ai-agents-cli/` (repo root, outside `src/`) | Shipped npm CLI: own source, own tests, bun toolchain (`cli-smoke.yml`) |

## Skip

- `copilot-cli/{agents,skills,instructions,lib,hooks}/` and `copilot-cli/THIRD-PARTY-NOTICES.TXT`, `vs-code-agents/*.agent.md`, `claude/agents/*.md`: generated, don't hand-edit (`.agents/governance/GENERATOR-FILES.md`, which omits the notices file).
- `STYLE-GUIDE.md`: zero references from any template or agent output, and outside all three plugin roots. Still live for humans via `.gemini/styleguide.md` and `.github/prompts/default-ai-review.md`; do not delete.

## Constraints

- Regenerate: `uv run python build/scripts/build_all.py`, verify `--check`, commit source and output together.
- Cross-harness work: read `agent-harness-reference` first, route the change through `ai-agents-portability-campaign`.

## Dangerous assumptions

- `claude/agents/` looks hand-maintained; ADR-109 B1 made it generated, then binplaced to `.claude/agents/`.
- `copilot-cli/docs/copilot-instructions.md` looks generated/ratcheted; it's hand-authored (ceiling binds `.github/copilot-instructions.md`).
- `build_all.py --check` green does not prove the lib sync ran (see Dependencies).
- `OWNED_PREFIXES` is the bare `src/` (`build_all.py:1061`), so ANY uncommitted change under `src/`, this file, `STYLE-GUIDE.md`, `claude/AGENTS.md` and `copilot-cli/docs/` included, reds `build_all.py --check` and pre_pr's `Generated Artifact Staleness` as `STALENESS DETECTED: uncommitted regen drift`. Regenerating does not clear it; commit.

## Dependencies

- Generators here: `agents`, `skills`, `rules`, `lib`, `hooks` (`.agents/governance/GENERATOR-FILES.md`).
- `copilot-cli/lib/`: run `scripts/sync_plugin_lib.py` before `build_all.py`; chain, order, and catchers in `build/AGENTS.md`.

## Architecture

- Full render pipeline: generator order, `.claude/` write exceptions (`binplace_manifest.claude_allowlist()`): `build/AGENTS.md`.

## Commands

```bash
uv run python scripts/sync_plugin_lib.py           # MUST precede build_all.py
uv run python build/scripts/build_all.py          # regenerate
uv run python build/scripts/build_all.py --check   # CI drift gate
uv run python build/generate_agents.py --validate    # copilot-cli/agents, vs-code-agents, .github/agents
uv run python build/scripts/agent_templates.py --validate  # claude/agents/ vs its templates
cd packages/ai-agents-cli && bun install --frozen-lockfile && bun run typecheck && bun test
```
