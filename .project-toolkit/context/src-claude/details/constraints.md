## Constraints

- Cross-harness change: read `agent-harness-reference` first, route through `ai-agents-portability-campaign`.
- `model:` needs an ADR-080 `KEEP_PIN` sidecar entry, or a bare alias (`sonnet`, `opus`, `haiku`) plus `model-rationale:` priced below the harness default through the platform `model_tiers` map (`check_model_pins.py`). Only `code-reviewer.md` qualifies.
- Those three agents read `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts` (`merge-resolver.md` still bare `${CLAUDE_PLUGIN_ROOT:-.claude}`; `plugin-self-containment.md` MUST 2 wants the nested form). Resolves against this plugin's own `skills/` now that support files mirror here (#5794); before that the fallback needed a second install.
