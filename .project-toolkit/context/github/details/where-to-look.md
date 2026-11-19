## Where to look

| Path | Why |
|---|---|
| `workflows/*.yml` (56) | Hand-edited; schema and SHA pins by `validate_workflows.py` |
| `agents/*.agent.md` (30) | Links to the shipped `src/copilot-cli/agents/` |
| `instructions/*.instructions.md` | Links, plus repo-only files from `generate_rules.py` |
| `hooks/` | `hooks.json` links to `src/copilot-cli/hooks/` and registers nothing. `memory-recall.json` is hand-authored: Copilot memory recall on `userPromptTransformed` (issue #4727) |
| `prompts/` (12) | Hand-written inputs to Actions workflows; no generated copies |
