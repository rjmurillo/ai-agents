## Constraints

- Regenerate, verify `--check`, commit source and output together.
- Separate plugin roots: no cross-reference, no upstream-only path in shipped text.
- Neither `.claude-plugin/plugin.json` carries a `version` key (ADR-092).
- Cross-harness work: read `agent-harness-reference`, route through `ai-agents-portability-campaign`.
