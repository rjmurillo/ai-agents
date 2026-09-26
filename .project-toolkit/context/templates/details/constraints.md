## Constraints

- `validate_templates_schema.py` validates only a `platforms/*.yaml` carrying a top-level `provider:`, skipping `binplace.yaml`. `binplace_manifest.py` validates that one, requiring every `install_tree` under `.claude/` or `.github/` (`BinplaceConfigError`, exit 2).
- Cross-harness hook, event, or generated-Copilot change: read the `agent-harness-reference` skill, route through `ai-agents-portability-campaign`.
