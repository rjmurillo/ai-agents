# src/

| Tree | Status | Consumer |
|---|---|---|
| `claude/*.md` | Hand-maintained; claude-agents plugin source. See `src/claude/AGENTS.md` | Claude Code marketplace install |
| `copilot-cli/**` | GENERATED mirror of `.claude/{skills,hooks,lib,rules}` and `templates/agents/` | Copilot CLI plugin |
| `vs-code-agents/*.agent.md` | GENERATED from `templates/agents/` | VS Code |
| `*.ts`, `transforms/`, `agent-registry-schema.ts` | Copilot target emitter (bundle -> `.github/copilot/...`); tests `tests/*.test.ts` via `bun test` | `packages/ai-agents-cli` |
| `STYLE-GUIDE.md` | Agent prose standards; MUST for every agent file | |

Regen: `uv run python build/scripts/build_all.py`; drift gate `--check`. Never edit generated trees.
`claude/` and `copilot-cli/` are separate plugin roots: no cross-references, no upstream-only paths
(`.agents/`, `build/`) without a `vendor-portability` declaration (`.claude/rules/plugin-self-containment.md`).
Cross-harness changes: `agent-harness-reference`, then `ai-agents-portability-campaign`, then regenerate.
