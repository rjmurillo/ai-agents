# Skill: PR Retrospective Learning Extraction

## Statement

When a PR demonstrates best practices or novel solutions, extract atomic learnings with evidence for skill generation.

## Context

After merging a PR that implements patterns worth preserving (e.g., token optimizations, architectural improvements, workflow enhancements).

## Pattern

### Workflow

1. **Read PR artifacts**:
   - PR description and objectives
   - Commit history with messages
   - Changed files (before/after comparison)

2. **Identify distinct improvements**:
   - Each commit may contain one or more patterns
   - Look for: token savings, workflow improvements, architectural patterns, quality gates
   - Avoid bundling unrelated changes into single learning

3. **Extract evidence per pattern**:
   - Commit SHA
   - Before/after code snippets
   - Quantitative metrics (tokens saved, lines reduced, files affected)
   - Problem statement + solution

4. **Calculate impact metrics**:
   - Token savings (aggregate from multiple changes)
   - Validation count (starts at 1 for the PR)
   - Atomicity score (90%+ ideal)

5. **Generate atomic learning per pattern**:
   - One learning per distinct concept
   - Include: problem, before, after, pattern, evidence, atomicity

### Good Example

From Session 65 (PR #255):
- **6 distinct learnings** extracted from 8 commits
- Each learning: problem + before/after + pattern + evidence (commit SHA)
- Total impact: ~4,600 tokens saved
- Atomicity scores: 91-96%

### Bad Example

Single learning: "PR #255 improved GitHub skill" (vague, no evidence, not actionable)

## Evidence

**Session 65**: Extracted 6 learnings from PR #255
- Input: 8 commits, +1105/-548 lines
- Output: `.agents/analysis/pr-255-learnings.md` with 6 atomic patterns
- Impact: ~4,600 tokens documented
- Each learning includes commit SHA, before/after, pattern, atomicity score

## Atomicity

**Score**: 94%

**Justification**: Single concept (how to extract learnings from PRs). Minor compound: "extract atomic learnings with evidence" (two steps: extract + evidence), but these are inseparable for quality.

## Category

retrospective

## Tag

helpful

## Impact

**Rating**: 9/10

**Justification**: Enables systematic learning capture from successful PRs. Prevents knowledge loss. Feeds skill generation pipeline.

## Validation Count

1 (Session 65)

## Created

2025-12-22

## Activation Vocabulary

PR, retrospective, learning, extract, pattern, evidence, commit, before, after, token, impact, metric
