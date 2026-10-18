## Where to look

| Path | Why |
|---|---|
| `workflows/*.yml` (56) | Hand-edited; schema and SHA pins by `validate_workflows.py` |
| `agents/*.agent.md` (30) | Links to the shipped `src/copilot-cli/agents/` |
| `agents/security/references/*.md` | Hand copy of `src/claude/security/references/`; edit both |
| `instructions/*.instructions.md` | Links, plus repo-only files from `generate_rules.py` |
| `hooks/` | `hooks.json` links to `src/copilot-cli/hooks/` and registers nothing. `memory-recall.json` is hand-authored: Copilot memory recall on `userPromptTransformed` (issue #4727) |
| `prompts/` (33) | 12 `pr-quality-gate-*.md` generated; 7 `pr-quality.*.prompt.md` hand-written, dot not hyphen |
| `agents/pr-comment-responder.prompt.md` | Only `.prompt.md` under `agents/`; hand-maintained |
