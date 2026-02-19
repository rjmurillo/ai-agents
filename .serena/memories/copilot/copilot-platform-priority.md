| Priority | Platform | Investment |
|----------|----------|------------|
| P0 | Claude Code | Full |
| P1 | VS Code | Active |
| P2 | Copilot CLI | Maintenance only |

**Copilot CLI Limitations**: No project-level MCP, no Plan Mode, 8k-32k context (vs 200k+), no semantic analysis

**RICE**: Claude ~20+ | VS Code ~10+ | Copilot CLI 0.8

**Decisions**: No Sync-McpConfig.ps1 support. No parity requirement. Maintenance only.

**Remove if**: >10% maintenance burden, zero requests in 90 days, no GitHub improvements in 6 months

## Related

- [copilot-cli-model-configuration](copilot-cli-model-configuration.md)
- [copilot-directive-relocation](copilot-directive-relocation.md)
- [copilot-follow-up-pr](copilot-follow-up-pr.md)
- [copilot-pr-review](copilot-pr-review.md)
- [copilot-supported-models](copilot-supported-models.md)
