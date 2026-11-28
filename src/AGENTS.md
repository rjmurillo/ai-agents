# src/

Both marketplace plugin sources: `claude/` for Claude Code, `copilot-cli/` for Copilot CLI (ADR-109 B6). `packages/ai-agents-cli/` (repo root) vendors `.claude/`, nothing from here.

## Matters

- ADR-109: `claude/{agents,skills,rules,hooks}` render from `templates/`. Dogfood `.claude/` links agents, skills, and rules (ADR-119). See `templates/AGENTS.md`.
- `.claude-plugin/marketplace.json` lists one Claude plugin, `project-toolkit` at `./src/claude`; `claude-agents` is retired (B6).
- `claude/skills/<name>/`: `SKILL.md` renders from its template; every other file is hand-maintained here; `.claude/skills/<name>` links here (ADR-119).

## Entry points

- Claude/Copilot agent: edit BOTH `templates/agents/<stem>.claude.md.tmpl` AND `<stem>.copilot.md.tmpl`; editing one skips the other's output.

## Where to look

| Path | Why |
|---|---|
| `claude/**` | Plugin tree for `.claude/`; see `src/claude/AGENTS.md` |
| `copilot-cli/instructions/` | Every `claude/rules/` file; all-internal rules stay in `.claude/rules/` (ADR-119) |
| `copilot-cli/hooks/` | From `claude/hooks/`; binplaced to `.github/hooks/*.json` |
| `copilot-cli/docs/`, both `.claude-plugin/` | Hand-maintained inside generated trees |

## Skip

- `claude/{agents,skills,rules,hooks}/`, `copilot-cli/{agents,skills,instructions,hooks}/`, `vs-code-agents/*.agent.md`: generated (`.agents/governance/GENERATOR-FILES.md`); `copilot-cli/THIRD-PARTY-NOTICES.TXT` too, via `scripts/generate_third_party_notices.py --check`, omitted from that inventory.
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

- `build_all.py` renders lib packages and bootstrap from `scripts/`. See `.claude/AGENTS.md` for lib edit locations.

## Architecture

- Render pipeline and gate semantics: `build/AGENTS.md`.

## Commands

```bash
uv run python build/scripts/build_all.py
uv run python build/scripts/build_all.py --check   # drift gate
uv run python build/generate_agents.py --validate
uv run python build/scripts/agent_templates.py --validate  # also rule_, hook_templates.py
uv run python build/scripts/generate_skills.py --validate
cd packages/ai-agents-cli && bun install --frozen-lockfile && bun run typecheck && bun test
```
