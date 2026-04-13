# Bot Configuration Noise Reduction (Issue #326)

## Problem

PR #249 accumulated 97 review comments (target: <20), with low actionability rates and duplicates.

## Solution

Tuned bot configurations to reduce noise by 50-70%:

### CodeRabbit (.coderabbit.yaml)

| Setting | Value | Impact |
|---------|-------|--------|
| `profile` | `chill` | Reduces nitpicky feedback |
| `path_filters` | Exclude `.agents/**`, `.serena/**`, generated files | No comments on agent artifacts |
| `collapse_walkthrough` | `true` | Collapse verbose summaries |
| `poem` | `false` | Disable decorative content |
| `related_issues/prs` | `false` | Skip potentially related items |
| Path instructions | High-confidence (>80%) requirement | Actionable feedback only |

### Gemini (.gemini/config.yaml)

| Setting | Before | After | Impact |
|---------|--------|-------|--------|
| `comment_severity_threshold` | MEDIUM | HIGH | Focus on critical issues |
| `max_review_comments` | -1 (unlimited) | 10 | Force prioritization |
| `ignore_patterns` | Already configured | N/A | Exclude `.agents/**`, `.serena/**` |

### Copilot (.github/copilot-code-review.md)

Added Review Quality Guidelines section:

- High-confidence instruction (>80% confidence required)
- Explicit focus areas: bugs, security, architecture violations
- Explicit exclusions: style, observations, speculation, documentation-only, generated files
- Conciseness: "One sentence per comment when possible"

**Limitation**: No hard limits available (instruction-based only)

## Key Decisions

1. **CodeRabbit Profile**: `chill` over `assertive` (analysis showed 66% noise ratio)
2. **Gemini Severity**: HIGH (was MEDIUM) to suppress style suggestions
3. **Gemini Limit**: 10 comments (actionability was only 24%)
4. **Path Exclusions**: Comprehensive coverage of generated files and agent artifacts

## Expected Metrics

| Metric | Before (PR #249) | Target | Change |
|--------|------------------|--------|--------|
| Total comments | 97 | <20 | -79% |
| Duplicates | ~5 | <2 | -60% |
| Generated file comments | >0 | 0 | -100% |
| Copilot actionability | 21-34% | >50% | +47-138% |
| Gemini actionability | 24% | >50% | +108% |
| CodeRabbit actionability | 49% | >60% | +22% |
| cursor[bot] actionability | 95% | Maintain | 0% |

## Verification Strategy

Monitor next 3 PRs for:

1. Comment volume (<20 per PR)
2. Duplicate rate (<2 per PR)
3. Generated file comments (0 expected)
4. Actionability rates by bot

Track in session logs using this template:

```markdown
## PR Review Metrics

| Bot | Comments | Actionable | Actionability % |
|-----|----------|------------|-----------------|
| cursor[bot] | X | Y | Z% |
| CodeRabbit | X | Y | Z% |
| Gemini | X | Y | Z% |
| Copilot | X | Y | Z% |
| **Total** | **X** | **Y** | **Z%** |

**Noise Indicators**:
- Duplicates: N
- Generated file comments: N
- Style-only comments: N
```

## Configuration Files

| Bot | Config File | Key Settings |
|-----|-------------|--------------|
| cursor[bot] | None (Marketplace app) | N/A |
| CodeRabbit | `.coderabbit.yaml` | profile, path_filters, noise flags |
| Gemini | `.gemini/config.yaml` | severity, max comments, ignore patterns |
| Copilot | `.github/copilot-code-review.md` | Instruction-based guidelines |

## Future Improvements

1. **CodeRabbit**: Add path_instructions with IGNORE for specific noisy files
2. **Gemini**: Test CRITICAL severity if HIGH still too noisy
3. **Copilot**: Monitor GitHub changelog for new config options
4. **All Bots**: Coordinate review timing to reduce duplicate detection

## Documentation

- **Issue**: #326
- **Commit**: 9f41f7a
- **Session**: `.agents/sessions/2025-12-23-session-87-bot-config-noise-reduction.md`
- **Guide**: `.agents/devops/BOT-CONFIGURATION.md` (comprehensive reference)
- **Analysis**: `.agents/analysis/085-velocity-bottleneck-analysis.md`

## References

- **CodeRabbit Schema**: https://coderabbit.ai/integrations/schema.v2.json
- **Gemini Docs**: https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github
- **Copilot Docs**: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/configure-automatic-review
- **Copilot Instructions Guide**: https://github.blog/ai-and-ml/unlocking-the-full-power-of-copilot-code-review-master-your-instructions-files/
