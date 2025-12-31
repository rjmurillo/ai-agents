# Issue #363: AI Reviewer Bot Consolidation Analysis

## Findings Summary

**Analysis Date**: 2025-12-29
**Analysis Document**: `.agents/analysis/007-ai-reviewer-bot-consolidation.md`

## Bot Performance (Quantified)

| Bot | Signal Quality | False Positive Rate | Config Lines | Recent Activity |
|-----|----------------|---------------------|--------------|-----------------|
| cursor[bot] | 100% (28/28) | 0% | 0 | Not visible (last 5 PRs) |
| Copilot | 90% (17/19) | 10% | 790 | Active (AI workflows) |
| CodeRabbit | ~50% (tuned) | 50% | 56 | Active (3/5 recent PRs) |
| Gemini | 0% (0/5) | 100% | 0 | Active (5/5 recent PRs) |

## Recommendation: Option A (Minimal Configuration)

**Keep**: Copilot + cursor[bot] (if accessible)
**Remove**: Gemini (immediate), CodeRabbit (defer)

**Rationale**:

1. Gemini: 0% actionability = pure noise
2. cursor[bot]: 100% signal + zero config overhead (if still accessible)
3. Copilot: 90% signal + multi-model infrastructure
4. CodeRabbit: 50% signal not worth ongoing tuning burden

**Expected Impact**: 50-90% less PR review noise

## Configuration Locations

- cursor[bot]: .github/bot-authors.yml (listed), no local config (GitHub Marketplace app)
- Copilot: .github/actions/ai-review/action.yml (790 lines)
- CodeRabbit: .coderabbit.yaml (56 lines)
- Gemini: .github/workflows/pr-maintenance.yml (line 361, 400 - bot authors array)

## Implementation Steps

1. **Immediate**: Remove `gemini-code-assist[bot]` from pr-maintenance.yml bot authors array
2. **Verify**: Check cursor[bot] subscription status via GitHub Marketplace
3. **Decision**: CodeRabbit retention (user preference required)
4. **Optional**: Remove .coderabbit.yaml if CodeRabbit eliminated

## Historical Context

- Issue #326: CodeRabbit noise reduction (97 → <20 comments/PR target)
- Memory pr-review-006-reviewer-signal-quality: Signal quality baseline
- Memory cursor-bot-review-patterns: 100% actionability across 28 comments
- Memory copilot-pr-review: 90% actionability with false positive patterns
- Memory coderabbit-config-strategy: Tuning approach for noise reduction

## Unique Value Analysis

| Bot | Unique Capability | Overlap |
|-----|-------------------|---------|
| cursor[bot] | Bug detection (logic errors, null-safety, fail-safe logic) | None (unique) |
| Copilot | Edge cases, type safety, multi-model flexibility | Partial (cursor[bot]) |
| CodeRabbit | Style suggestions, architecture patterns | None (unique) |
| Gemini | None identified | N/A |

**Trade-off**: Removing CodeRabbit loses style/architecture suggestions but eliminates 50% false positive burden.
