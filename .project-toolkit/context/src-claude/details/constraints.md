## Constraints

- Cross-harness change: read `agent-harness-reference` first. In the ai-agents repository, route through `ai-agents-portability-campaign`.
- `model:` needs an ADR-080 `KEEP_PIN` sidecar entry, or a bare alias (`sonnet`, `opus`, `haiku`) plus `model-rationale:` priced below the harness default through the platform `model_tiers` map (`check_model_pins.py`). None qualifies; no Copilot agent may pin, since `.github/agents` links to it.
- An agent that runs a skill script uses the ADR-121 locator that `build/scripts/plugin_run_launcher.py` renders (`plugin-self-containment.md` MUST 2). Resolves against this plugin's own `skills/`, where support files live (#5794); before that the fallback needed a second install.
