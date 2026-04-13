# Prompt Engineering: merge-conflict-analysis.md

## Location

`.github/prompts/merge-conflict-analysis.md`

## Applied Patterns (2025-12-26)

### 1. Input Format Specification

Added explicit section describing what the prompt receives:
- Blocked files JSON array
- Conflict markers with `<<<<<<<`, `=======`, `>>>>>>>` markers  
- Commit history for both branches

### 2. Pre-Work Context Analysis

Added: "Analyze commit messages to determine intent (bugfix, feature, refactor) before choosing a resolution strategy."

### 3. Format Strictness

Changed from verbose instructions to strict directive:
- "Output ONLY a JSON object. No markdown, no explanation, no preamble."

### 4. Contrastive Examples

Added CORRECT and INCORRECT examples:

```markdown
<example type="CORRECT">
{"resolutions":[{"file":"src/config.ts","strategy":"theirs","reasoning":"..."}],"verdict":"PASS"}
</example>

<example type="INCORRECT">
Based on my analysis of the merge conflicts, here is the resolution:
```json
{"resolutions":[...]}
```
</example>
```

### 5. Category-Based Generalization (Intent Classification)

Added table mapping commit types to priorities:
- Bugfix, Security: Highest priority
- Refactor, Feature: Medium priority
- Style: Lowest priority

### 6. CRITICAL_FAIL Criteria

Made explicit when to fail:
- Conflicting semantic changes
- Ambiguous intent
- Security implications requiring human review

## Input Context

Built by `.github/workflows/pr-maintenance.yml` lines 172-224:
1. Checkout PR branch and attempt merge
2. Extract conflict markers from blocked files
3. Get recent commits for both branches
4. Format as markdown context for AI

## Iteration Status

- PRs #301, #353: Auto-resolve working (expanded patterns)
- PR #255: Still requires AI fallback (workflow files, CLAUDE.md, tests)
