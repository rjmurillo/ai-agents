# AI Reviewer Bot Evaluation

**Date**: 2025-12-29
**Issue**: #363
**Objective**: Evaluate reducing AI reviewer bot count from 4 to 2

## Current Configuration

| Bot | Status | Configuration | Comment Style |
|-----|--------|---------------|---------------|
| Gemini Code Assist | Active | `.gemini/config.yaml` | Code-level comments |
| CodeRabbit | Active | `.coderabbit.yaml` | PR discussion summaries |
| Copilot PR Reviewer | Active | GitHub App | Minimal activity |
| Cursor | Unknown | No config found | No activity detected |

## Activity Analysis (Last 11 PRs)

### Review Volume

| Bot | Reviews | Code Comments | PR Comments |
|-----|---------|---------------|-------------|
| gemini-code-assist[bot] | 9 | 36 | 2 |
| coderabbitai[bot] | 9 | 0 | 11 |
| copilot-pull-request-reviewer[bot] | 1 | 0 | 0 |
| cursor | 0 | 0 | 0 |

### Key Findings

1. **Gemini Code Assist**
   - Most active reviewer with 36 code-level comments
   - Focuses on style guide compliance and code quality
   - Configured with `comment_severity_threshold: HIGH` to reduce noise
   - **Value**: High - provides actionable code-level feedback

2. **CodeRabbit**
   - Provides PR summaries and walkthrough comments
   - Uses "chill" profile to reduce nitpicky feedback
   - Configured with path exclusions for agent artifacts
   - **Value**: Medium - useful summaries but overlaps with Gemini

3. **Copilot PR Reviewer**
   - Minimal activity (1 review across 11 PRs)
   - May be disabled or rate-limited
   - **Value**: Low - not actively contributing

4. **Cursor**
   - No configuration found in repository
   - Zero activity detected in recent PRs
   - **Value**: None - appears inactive or not installed

## Redundancy Analysis

### Overlap Between Bots

- Gemini and CodeRabbit both review the same files
- CodeRabbit provides summaries; Gemini provides line-level comments
- Different focus areas reduce pure duplication
- Issue #326 already implemented noise reduction for both

### Bot Response Loops

- Evidence from PR #308: 38 bot reviews vs 1 human review
- Bot responses to other bot comments create noise
- rjmurillo-bot responds to all reviewers (43 comments in sample)

## Recommendation

### Keep (2 bots)

1. **Gemini Code Assist** - Primary code reviewer
   - High comment volume with actionable feedback
   - Style guide enforcement
   - Already configured with noise reduction

2. **CodeRabbit** - Secondary/summary reviewer
   - PR walkthrough summaries are unique value
   - Path-specific instructions for agent prompts
   - Complements Gemini's line-level focus

### Disable or Remove (2 bots)

1. **Copilot PR Reviewer** - Disable
   - Nearly zero activity
   - Redundant with Gemini's code review
   - Recommendation: Disable via GitHub App settings

2. **Cursor** - Remove/verify status
   - No activity detected
   - No configuration present
   - Recommendation: Verify installation status; remove if installed

## Implementation Steps

1. [ ] Disable Copilot PR Reviewer in GitHub App settings
2. [ ] Verify Cursor status and remove if present
3. [ ] Monitor PR review quality for 2 weeks
4. [ ] Update this document with post-change metrics

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Bot comments per PR | ~50-100 | <30 |
| Unique value ratio | ~60% | >80% |
| Human review time | Unknown | Reduced |

## References

- Issue #326: Bot noise reduction configuration
- PR #249: Original 97-comment PR that triggered optimization
- `.coderabbit.yaml`: CodeRabbit configuration
- `.gemini/config.yaml`: Gemini configuration
