# GitHub Copilot CLI Model Configuration

**Last Updated**: 2025-12-26
**Source**: PR #310 comment 2644791424
**Context**: Available models for GitHub Copilot CLI via different authentication tokens

## Authentication Contexts

### Bot User (`rjmurillo-bot` via BOT_PAT)

Available models:

| Model | Cost Multiplier | Slug |
|-------|-----------------|------|
| Claude Haiku 4.5 | 0.33x | `claude-haiku-4.5` |
| GPT-5-Mini | 0x (free tier) | `gpt-5-mini` |
| GPT-4.1 | 0x (free tier) | `gpt-4.1` |

### Human User (`rjmurillo` via COPILOT_GITHUB_TOKEN)

Available models:

| Model | Cost Multiplier | Slug |
|-------|-----------------|------|
| Claude Sonnet 4.5 | 1x | `claude-sonnet-4.5` |
| Claude Opus 4.5 (Preview) | 3x | `claude-opus-4.5` |
| Claude Haiku 4.5 | 0.33x | `claude-haiku-4.5` |
| Claude Sonnet 4 | 1x | `claude-sonnet-4` |
| GPT-5.1 | 1x | `gpt-5.1` |
| GPT-5.1-Codex-Mini | 0.33x | `gpt-5.1-codex-mini` |
| GPT-5.1-Codex-Max | 1x | `gpt-5.1-codex-max` |
| GPT-5.1-Codex | 1x | `gpt-5.1-codex` |
| GPT-5 | 1x | `gpt-5` |
| GPT-5-Mini | 0x (free tier) | `gpt-5-mini` |
| GPT-4.1 | 0x (free tier) | `gpt-4.1` |
| Gemini 3 Pro (Preview) | 1x | `gemini-3-pro` |

## Important Notes

1. **Model Name Format**: The format shown is "Model name (cost multiplier)"
   - Example: `Claude Opus 4.5 (Preview) (3x)` means the model costs 3x premium tokens

2. **Parameter Slugs**: The names passed to `.github/actions/ai-review/action.yml` parameter `copilot-model` are machine-readable slugs shown in the Slug column

3. **Documentation Reference**: [Supported AI Models In GitHub Copilot](https://docs.github.com/en/copilot/reference/ai-models/supported-models#supported-ai-models-in-copilot)

## Cross-References

- ADR-021: AI Review Model Routing Strategy (`.agents/architecture/ADR-021-model-routing-strategy.md`)
- AI Review Model Policy (`.agents/governance/AI-REVIEW-MODEL-POLICY.md`)

## Usage Guidance

When configuring workflows:

1. Use explicit `copilot-model` parameter per job (never rely on defaults)
2. Select model based on prompt type per ADR-021 routing matrix
3. Consider cost multipliers when choosing between equivalent-capability models
4. Bot user has limited model access - use human token for advanced models
