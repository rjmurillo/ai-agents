# Skill-Copilot-001: GitHub Copilot Supported Models Reference

**Statement**: Select Copilot model based on plan tier and multiplier cost.

**Context**: When using GitHub Copilot in any interface (Chat, CLI, Editor)

**Evidence**: GitHub docs 2025-12-23, verified via gh copilot --version

**Atomicity**: 95% | **Impact**: 8/10

## Plan Tiers and Premium Request Allowances

| Plan | Monthly Cost | Premium Requests | Per-User |
|------|--------------|------------------|----------|
| Free | $0 | 50 | Individual |
| Pro | $10 | 300 | Individual |
| Pro+ | $39 | 1,500 | Individual |
| Business | $19/user | 300 | Per seat |
| Enterprise | $39/user | 1,000 | Per seat |

## Model Multipliers

Premium requests consumed = base request x multiplier

| Multiplier | Cost Level | Example Models |
|------------|------------|----------------|
| 0x | Free | Base models (no premium consumption) |
| 0.25x-0.33x | Cheap | Efficient variants |
| 1x | Standard | Default models |
| 3x | Expensive | Claude Sonnet 4.5 |
| 10x | Premium | o1, o3-mini |

## Supported Models by Interface

### Copilot Chat (All Interfaces)

| Model | Multiplier | Notes |
|-------|------------|-------|
| GPT-4o | 1x | Default |
| Claude Sonnet 4 | 1x | Anthropic |
| Claude Sonnet 4.5 | 3x | Premium |
| Gemini 2.0 Flash | 0.25x | Cheap |
| o1 | 10x | OpenAI reasoning |
| o3-mini | 10x | OpenAI reasoning |

### Copilot CLI

| Model | Multiplier | Notes |
|-------|------------|-------|
| Claude Sonnet 4.5 | 3x | Default for CLI |

### Editor Completions

| Model | Multiplier | Notes |
|-------|------------|-------|
| GPT-4o mini | 0x | Free, default |
| Claude Sonnet 4 | 1x | Optional |

## Cost Optimization Patterns

### Pattern 1: Use Free Tier First

```text
# For simple completions, use default (0x multiplier)
# Only switch to premium for complex tasks
```

### Pattern 2: Gemini for Bulk Operations

```text
# Gemini 2.0 Flash at 0.25x is 4x more efficient
# Use for code review, documentation, bulk edits
```

### Pattern 3: Reserve o1/o3-mini for Reasoning

```text
# 10x multiplier = use sparingly
# Best for: architecture decisions, complex debugging
```

## Checking Current Plan

```bash
# Check authenticated user's Copilot access
gh auth status
gh copilot --version

# View subscription (requires API)
gh api user
```

## Related

- copilot-platform-priority (investment strategy)
- copilot-pr-review (false positive handling)
