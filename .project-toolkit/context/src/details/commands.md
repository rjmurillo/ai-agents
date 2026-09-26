## Commands

```bash
uv run python build/scripts/build_all.py
uv run python build/scripts/build_all.py --check   # drift gate
uv run python build/generate_agents.py --validate
uv run python build/scripts/agent_templates.py --validate  # also rule_, hook_templates.py
uv run python build/scripts/generate_skills.py --validate
cd packages/ai-agents-cli && bun install --frozen-lockfile && bun run typecheck && bun test
```
