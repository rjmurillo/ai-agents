# Skill-Memory-Size-001: Decomposition Thresholds

**Date**: 2025-12-22
**Issue**: #239
**Subject**: `skills-github-cli` memory file

## Problem Statement

The `skills-github-cli` memory has grown beyond maintainable size:

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Characters | 38,000+ | <10,000 | [FAIL] |
| Skills | 40+ | <15 | [FAIL] |
| Categories | 15+ | <5 | [FAIL] |
| Token Cost | ~9,500 tokens | <2,500 | [FAIL] |

## Root Cause

The memory was created as a comprehensive reference document rather than a collection of atomic skills. Over time, new skills were appended without considering decomposition.

## Impact

1. **Token Waste**: Every read of this memory costs ~9,500 tokens even when only 1-2 skills are needed
2. **Maintenance Friction**: Updates require navigating a 2000-line file
3. **Skill Discovery**: Finding relevant skills requires scrolling or searching
4. **Atomicity Violation**: Mixing unrelated domains (PRs, Releases, Extensions) in one file

## Decomposition Plan

### Target Structure

```text
.serena/memories/
├── skills-gh-pr.md           # PR operations (4 skills)
├── skills-gh-issues.md       # Issue operations (3 skills)
├── skills-gh-runs.md         # Workflow runs (2 skills)
├── skills-gh-releases.md     # Release management (2 skills)
├── skills-gh-api.md          # API, GraphQL, JSON (4 skills)
├── skills-gh-repo.md         # Repository settings (4 skills)
├── skills-gh-security.md     # Secrets, rulesets (5 skills)
├── skills-gh-projects.md     # Projects v2 (2 skills)
├── skills-gh-extensions.md   # Extensions (10+ skills)
├── skills-gh-copilot.md      # Copilot patterns (1 skill)
└── skills-gh-anti-patterns.md # Common pitfalls (9 entries)
```

### Token Efficiency Gains

| Scenario | Current | After Decomposition | Savings |
|----------|---------|---------------------|---------|
| PR review task | 9,500 tokens | 1,200 tokens | 87% |
| Issue triage | 9,500 tokens | 900 tokens | 91% |
| Release creation | 9,500 tokens | 800 tokens | 92% |
| API debugging | 9,500 tokens | 1,500 tokens | 84% |

### Implementation Steps

1. Create new focused memory files
2. Extract relevant skills to each file
3. Add cross-reference headers
4. Archive original file (don't delete - history)
5. Update agent prompts referencing old file
6. Validate with `mcp__serena__list_memories`

## Pattern: Memory Size Guidelines

**New skill**: `Skill-Memory-Size-001`

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Max characters | 10,000 | ~2,500 tokens |
| Max skills per file | 15 | Focused domain |
| Max categories | 3-5 | Single responsibility |
| Max sections | 10 | Navigability |

When a memory exceeds these thresholds, decompose into focused files.

## Evidence

- Issue [#239](https://github.com/rjmurillo/ai-agents/issues/239) created to track this work
- PR [#235](https://github.com/rjmurillo/ai-agents/pull/235) skillbook update added `Skill-GH-API-002` to already-large file
- Token cost measured at ~9,500 for full memory read

## Next Actions

1. Assign issue #239 to milestone
2. Execute decomposition (2-3 hours)
3. Update this analysis with results
