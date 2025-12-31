# Session 96: Issue #363 - AI Reviewer Bot Evaluation

**Date**: 2025-12-29
**Agent**: analyst
**Issue**: #363 - Evaluate reducing AI reviewer bot count from 4 to 1-2
**Branch**: chore/363-reduce-ai-reviewers

## Session Protocol Compliance

- [x] Serena initialization completed
- [x] Read HANDOFF.md
- [x] Read PROJECT-CONSTRAINTS.md
- [x] Read relevant memories: pr-review-006-reviewer-signal-quality
- [x] Session log created

## Objective

Analyze current AI reviewer bot usage and recommend consolidation strategy based on:
- Signal quality (actionable vs false positive rate)
- Unique value provided by each bot
- Configuration/maintenance overhead
- Cost per bot

## Research Plan

1. Search for AI reviewer configurations in `.github/` directory
2. Identify all configured bots: coderabbit, copilot, gemini-code-assist, cursor
3. Analyze existing memory on reviewer signal quality
4. Review configuration files for maintenance overhead
5. Search for related memories on bot performance
6. Document findings and recommendations

## Findings

### Current State

**Bots Configured**:

1. **cursor[bot]**: GitHub Marketplace app (no local config). Listed in .github/bot-authors.yml. 100% signal quality (28/28 comments). Not visible on last 5 PRs.
2. **Copilot**: 790-line composite action (.github/actions/ai-review/action.yml). 90% signal quality (17/19 comments). Used in AI workflows (not direct PR reviews).
3. **CodeRabbit**: 56-line config (.coderabbit.yaml). ~50% signal quality after tuning (Issue #326). Active on recent PRs (#545, #529, #502).
4. **Gemini**: Listed in pr-maintenance.yml bot authors. 0% signal quality (0/5 on PR 308). Active on all recent PRs.

**Signal Quality** (from memory pr-review-006-reviewer-signal-quality):

| Reviewer | Signal Rate | False Positive Rate | Comment Type Strength |
|----------|-------------|---------------------|----------------------|
| cursor[bot] | 100% (28/28) | 0% | Bug detection (logic errors, null-safety, fail-safe logic) |
| Copilot | 90% (17/19) | 10% | Edge cases, type safety |
| coderabbitai[bot] | ~50% (163 comments) | 50% | Style suggestions, architecture patterns |
| gemini-code-assist[bot] | 0% (0/5 on PR 308) | 100% (all noise) | No useful feedback |

**Configuration Overhead**:

- cursor[bot]: 0 lines (GitHub Marketplace app, zero-config)
- Copilot: 790 lines (composite action with retry logic, diagnostics, context building)
- CodeRabbit: 56 lines (YAML with tuning for noise reduction)
- Gemini: 0 lines (reuses Copilot infrastructure)
- **Total**: 846 lines of configuration

**Recent Activity** (last 5 PRs via GraphQL):

- cursor[bot]: Not active (possible subscription lapse or access revoked)
- Copilot: Active in AI workflows (not as PR reviewer)
- CodeRabbit: Active on 3/5 recent PRs
- Gemini: Active on 5/5 recent PRs

**Noise Reduction History**:

- Issue #326: CodeRabbit noise reduced from 97 comments (PR #249) to target <20 per PR
- Tuning: `profile: chill`, path_filters, path_instructions, disabled markdownlint
- Result: Signal improved from 34% to >50% (but still 50% false positive rate)

### Analysis Document

Created: `.agents/analysis/007-ai-reviewer-bot-consolidation.md`

## Decisions

**Recommendation**: Option A - Minimal Configuration

**Keep**: Copilot + cursor[bot] (if accessible)

**Remove**: Gemini (immediate - 0% signal), CodeRabbit (defer - 50% signal with maintenance burden)

**Rationale**:

1. Gemini provides 0% actionability - pure noise with no benefit
2. cursor[bot] has 100% signal quality with zero configuration overhead (if still accessible)
3. Copilot provides 90% signal quality with infrastructure that supports multiple models
4. CodeRabbit's 50% signal quality does not justify ongoing tuning maintenance

**User Impact**: 50-90% less noise in PR reviews. More time addressing real issues, less time dismissing false positives.

## Next Steps

1. **Immediate**: Remove Gemini from pr-maintenance.yml bot authors list
2. **Verify**: Check cursor[bot] GitHub Marketplace subscription status
3. **Decide**: CodeRabbit retention (user preference: keep 50% signal + tuning vs remove for simplicity)
4. **Document**: Update issue #363 with findings link
5. **Implement**: Create PR to remove Gemini configuration

## Session End

- [x] Analysis document created: .agents/analysis/007-ai-reviewer-bot-consolidation.md
- [x] Memory updated with findings: issue-363-ai-reviewer-consolidation
- [x] Markdown lint clean (0 errors)
- [x] Changes committed (commit: 643957b)
- [x] Issue #363 updated with findings (comment posted)

**Commit SHA**: 643957b
**Branch**: chore/363-reduce-ai-reviewers
