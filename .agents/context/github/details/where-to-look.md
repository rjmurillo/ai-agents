## Where to look

| Path | Why |
|---|---|
| `workflows/*.yml` (56) | Hand-edited; schema and SHA pins by `validate_workflows.py` |
| `agents/*.agent.md` (31) | Generated; do not hand-edit |
| `agents/security/references/*.md` | Hand copy of `src/claude/security/references/`; edit both |
| `instructions/*.instructions.md` | `generate_rules.py` from `src/claude/rules/` |
| `hooks/` | Binplaced from `src/copilot-cli/hooks/`; `hooks.json` registers nothing |
| `prompts/` (33) | 12 `pr-quality-gate-*.md` generated; 7 `pr-quality.*.prompt.md` hand-written, dot not hyphen |
| `agents/pr-comment-responder.prompt.md` | Only `.prompt.md` under `agents/`; hand-maintained |
