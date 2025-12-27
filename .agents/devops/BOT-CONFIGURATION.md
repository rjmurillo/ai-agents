# Bot Configuration Guide

**Issue**: #326
**Date**: 2025-12-23
**Status**: Active

## Overview

This repository uses multiple AI-powered bots for PR review. This document explains what each bot does, how configurations were tuned to reduce noise, and how to verify effectiveness.

## Problem Statement

**Before Tuning** (PR #249):

- 97 total review comments (target: <20)
- ~5 duplicate comments per PR
- Bots reviewing generated files unnecessarily
- Low actionability rates for some bots

**After Tuning** (Target):

- <20 review comments per PR
- Minimal duplicates
- Generated files excluded
- High-confidence feedback only

## Bot Catalog

### cursor[bot]

**Purpose**: Deep static analysis and bug detection

**Actionability**: 95% (28/30 comments verified across 14 PRs)

**Configuration**: None available (GitHub Marketplace app)

**Verdict**: **KEEP AS-IS** - Highest signal-to-noise ratio

**What it does well**:

- Catches real bugs (type errors, null references)
- Identifies edge cases
- Detects security vulnerabilities

### CodeRabbit (coderabbitai[bot])

**Purpose**: Comprehensive code review with summaries

**Actionability**: 49% (163 comments analyzed)

**Configuration File**: `.coderabbit.yaml`

**Tuning Applied** (Issue #326):

1. **Profile**: Set to `chill` (reduces nitpicky feedback)
2. **Path Filters**: Exclude generated files and agent artifacts

   ```yaml
   path_filters:
     - "!.agents/sessions/**"
     - "!.agents/analysis/**"
     - "!.serena/memories/**"
     - "!**/*.generated.*"
     - "!**/bin/**"
     - "!**/obj/**"
   ```

3. **Noise Reduction**:
   - `collapse_walkthrough: true` - Collapse verbose summaries
   - `poem: false` - Disable decorative poetry
   - `related_issues: false` - Skip potentially related issues
   - `related_prs: false` - Skip potentially related PRs
4. **High-Confidence Instructions**: Added to path_instructions

   ```text
   Only comment when you have HIGH CONFIDENCE (>80%) that an issue exists.
   Be concise: one sentence per comment when possible.
   Focus on actionable feedback, not observations.
   If uncertain whether something is an issue, do not comment.
   ```

**Expected Impact**: 30-50% reduction in comment volume, focus on architectural issues

### Gemini Code Assist (gemini-code-assist[bot])

**Purpose**: Google AI-powered code analysis

**Actionability**: 24% (0/5 on PR #308, mostly style suggestions)

**Configuration File**: `.gemini/config.yaml`

**Tuning Applied** (Issue #326):

1. **Severity Threshold**: Raised from MEDIUM to HIGH
2. **Comment Limit**: Capped at 10 comments (was unlimited)
3. **Path Exclusions**: Already had comprehensive ignore patterns

   ```yaml
   ignore_patterns:
     - ".agents/**"
     - ".serena/memories/**"
     - ".serena/**"
     - "**/*.generated.*"
     - "**/bin/**"
     - "**/obj/**"
     - "**/artifacts/**"
   ```

**Expected Impact**: 50-70% reduction in comment volume, suppress style suggestions

### GitHub Copilot (github-copilot[bot])

**Purpose**: AI-powered review with context synthesis

**Actionability**: 21-34% (declining trend, 3/14 unique comments on PR #249)

**Configuration File**: `.github/copilot-code-review.md` (instruction-based)

**Tuning Applied** (Issue #326):

1. **High-Confidence Instruction**: Added review quality guidelines

   ```text
   Only comment when you have HIGH CONFIDENCE (>80%) that an issue exists.
   ```

2. **Focus Areas**: Explicit list of what to review vs. ignore
3. **Exclusions**: Generated files, session logs, documentation-only changes
4. **Conciseness**: "One sentence per comment when possible"

**Limitations**:

- No `max_review_comments` setting available
- No `comment_severity_threshold` setting available
- Relies on instruction-following (not hard limits)
- Configuration via `.github/copilot-code-review.md` and `.github/copilot-instructions.md`

**Expected Impact**: 30-50% reduction in comment volume via instruction adherence

**Note**: Copilot uses workflow integration (`.github/workflows/copilot-context-synthesis.yml`) rather than a standalone config file. Noise reduction relies on prompt engineering in instruction files.

## Configuration Files Summary

| Bot | Config File | Key Settings |
|-----|-------------|--------------|
| cursor[bot] | None (Marketplace app) | N/A |
| CodeRabbit | `.coderabbit.yaml` | profile, path_filters, noise reduction flags |
| Gemini | `.gemini/config.yaml` | severity threshold, max comments, ignore patterns |
| Copilot | `.github/copilot-code-review.md` | Instruction-based guidelines |

## Verification Strategy

### Immediate Verification

After this PR merges, monitor next 3 PRs for:

1. **Comment Volume**: Target <20 per PR (was 97 on PR #249)
2. **Duplicate Rate**: Target <2 per PR (was ~5)
3. **Generated File Comments**: Target 0 (bots should ignore `.agents/**`)

### Metrics to Track

| Metric | Before (PR #249) | Target | Measurement |
|--------|------------------|--------|-------------|
| Total comments | 97 | <20 | Count all bot comments |
| Duplicates | ~5 | <2 | Count same finding from multiple bots |
| Actionability (Copilot) | 21% | >50% | Addressed / Total |
| Actionability (Gemini) | 24% | >50% | Addressed / Total |
| Actionability (CodeRabbit) | 49% | >60% | Addressed / Total |
| cursor[bot] | 95% | Maintain | Keep high signal |
| Generated file comments | >0 | 0 | Comments on `.agents/**` |

### Long-Term Monitoring

Track per-PR metrics in session logs:

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

## Tuning Iteration Process

If noise persists after initial tuning:

1. **Analyze**: Identify specific noise patterns in next 3 PRs
2. **Categorize**: Duplicates, false positives, style suggestions, generated files
3. **Adjust**:
   - CodeRabbit: Add more path_filters or path_instructions with IGNORE
   - Gemini: Further raise severity threshold or lower max_review_comments
   - Copilot: Refine instructions with specific "Do NOT comment" examples
4. **Verify**: Monitor next 3 PRs for improvement
5. **Document**: Update this file with lessons learned

## Future Improvements

Potential optimizations not yet implemented:

1. **CodeRabbit**:
   - Add path_instructions with IGNORE for specific files
   - Use tone_instructions to further reduce verbosity
2. **Gemini**:
   - Test comment_severity_threshold: CRITICAL (if HIGH still too noisy)
   - Add more specific ignore_patterns if new generated file types appear
3. **Copilot**:
   - Monitor GitHub changelog for new configuration options
   - Test path-specific instructions (e.g., `*.instructions.md` files)
4. **All Bots**:
   - Coordinate review timing to reduce duplicate detection
   - Use ignore_title_keywords for WIP/draft PRs (CodeRabbit)

## References

- **Issue**: [#326 - Tune bot review configurations to reduce noise](https://github.com/rjmurillo/ai-agents/issues/326)
- **Analysis**: `.agents/analysis/085-velocity-bottleneck-analysis.md`
- **PR #249 Retrospective**: `.agents/retrospective/2025-12-22-PR249-review-comment-analysis.md` (if exists)
- **CodeRabbit Schema**: <https://coderabbit.ai/integrations/schema.v2.json>
- **Gemini Documentation**: <https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github>
- **Copilot Documentation**: <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/configure-automatic-review>

## Changelog

| Date | Change | Impact |
|------|--------|--------|
| 2025-12-23 | Initial bot configuration tuning (Issue #326) | Expected 50-70% comment reduction |

---

**Maintainer**: DevOps agent
**Last Updated**: 2025-12-23
**Next Review**: After 3 PRs merged post-tuning
