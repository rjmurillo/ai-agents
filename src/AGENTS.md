# src/

Two of the three plugin roots; `packages/ai-agents-cli/` (repo root) vendors `.claude/`, nothing from here.

## Matters

- ADR-109 B1 to B4: `claude/{agents,skills,rules,hooks}` and `claude/hooks.json` render from `templates/`, then binplace byte for byte into `.claude/`. Render map: `templates/AGENTS.md`.
- `claude/skills/<name>/` holds `SKILL.md` only; scripts, references, tests stay under `.claude/skills/<name>/`.

## Entry points

- Claude/Copilot agent: edit BOTH `templates/agents/<stem>.claude.md.tmpl` AND `<stem>.copilot.md.tmpl`; editing one skips the other's output.

## Where to look

| Path | Why |
|---|---|
| `claude/**` | Plugin tree for `.claude/`; see `src/claude/AGENTS.md` |
| `copilot-cli/instructions/` | 22 of 28 `claude/rules/`, all-internal-scope dropped; no `copilot-cli/rules/` |
| `copilot-cli/hooks/` | From `claude/hooks/`; binplaced to `.github/hooks/*.json` |
| `copilot-cli/docs/`, both `.claude-plugin/` | Hand-maintained inside generated trees |

## Skip

- `claude/{agents,skills,rules,hooks}/`, `copilot-cli/{agents,skills,instructions,lib,hooks}/`, `vs-code-agents/*.agent.md`: generated (`.agents/governance/GENERATOR-FILES.md`); `copilot-cli/THIRD-PARTY-NOTICES.TXT` too, via `scripts/generate_third_party_notices.py --check`, omitted from that inventory.
- `STYLE-GUIDE.md`: orphan by design, bot-linked via `.gemini/styleguide.md`. Do not delete.

## Constraints

- Regenerate, verify `--check`, commit source and output together.
- Separate plugin roots: no cross-reference, no upstream-only path in shipped text.
- Neither `.claude-plugin/plugin.json` carries a `version` key (ADR-092).
- Cross-harness work: read `agent-harness-reference`, route through `ai-agents-portability-campaign`.

## Dangerous assumptions

- `copilot-cli/docs/copilot-instructions.md` looks generated; hand-authored, no byte ratchet (that binds `.github/copilot-instructions.md`).
- `OWNED_PREFIXES` carries a bare `src/`: any uncommitted change here, this file included, reds `build_all.py --check` and pre-PR `Generated Artifact Staleness`. Commit, do not just regenerate.

## Dependencies

- `copilot-cli/lib/`: run `scripts/sync_plugin_lib.py` first; catchers in `build/AGENTS.md`.

## Architecture

- Render pipeline and gate semantics: `build/AGENTS.md`.

## Commands

```bash
uv run python scripts/sync_plugin_lib.py           # MUST precede build_all.py
uv run python build/scripts/build_all.py
uv run python build/scripts/build_all.py --check   # drift gate
uv run python build/generate_agents.py --validate
uv run python build/scripts/agent_templates.py --validate  # also rule_, hook_templates.py
uv run python build/scripts/generate_skills.py --validate
cd packages/ai-agents-cli && bun install --frozen-lockfile && bun run typecheck && bun test
```
